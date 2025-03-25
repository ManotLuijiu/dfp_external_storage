"""
DFP External Storage - Installation Hooks
This module contains hooks for app installation and update
"""

import frappe
import os
import sys
import subprocess
from frappe import _
from frappe.utils import now_datetime


def after_install():
    """Run after app is installed"""
    # Check if this is a reinstallation
    check_reconnect_needed()


def after_sync():
    """Run after migrations are executed during app update"""
    # Check for reconnection needs during update too
    check_reconnect_needed()


def check_reconnect_needed():
    """Check if we need to run the reconnection tool"""
    # Skip during bench migrate --new-site
    if "new-site" in sys.argv:
        return

    # Check for reports directory
    reports_dir = os.path.join(
        frappe.get_site_path(), "private", "files", "dfp_external_storage_reports"
    )
    if not os.path.exists(reports_dir):
        return

    # Check for report files
    report_files = [
        f for f in os.listdir(reports_dir) if f.startswith("external_files_report_")
    ]
    if not report_files:
        return

    # Find the most recent report
    report_files.sort(reverse=True)  # Most recent first
    latest_report = os.path.join(reports_dir, report_files[0])

    # Check for disconnected files
    disconnected_files = check_for_disconnected_files()
    if disconnected_files == 0:
        return

    # We found a report and disconnected files, offer reconnection
    show_reconnection_message(latest_report, disconnected_files)

    # Try to automatically reconnect if in non-interactive mode
    if frappe.flags.in_install or frappe.flags.in_patch:
        try_auto_reconnect(latest_report)


def check_for_disconnected_files():
    """Check for files that might be disconnected from cloud storage"""
    # Check if the file table exists (it might not during fresh install)
    if not frappe.db.table_exists("tabFile"):
        return 0

    # Check if the dfp_external_storage column exists (it might not during fresh install)
    try:
        # Check if there are files with pattern /file/[hash]/[filename] but no dfp_external_storage field
        count = frappe.db.sql(
            """
            SELECT COUNT(*) as count
            FROM `tabFile`
            WHERE file_url LIKE '/file/%/%'
            AND (dfp_external_storage IS NULL OR dfp_external_storage = '')
        """
        )[0][0]

        return count
    except Exception:
        # Column doesn't exist yet
        return 0


def show_reconnection_message(report_path, file_count):
    """Show message about reconnection possibility"""
    msg = _(
        """
        <h4>DFP External Storage Reinstalled</h4>
        <p>It appears that DFP External Storage was previously installed and had cloud files configured.</p>
        <p>We found a report of your external files and {0} files that might need reconnection.</p>
        <p>You can run the reconnection tool to restore access to your cloud files:</p>
        <pre>bench --site {1} execute dfp_external_storage/reconnect.py "{2}"</pre>
        <p>This will create placeholder storage configurations and reconnect your files.</p>
        <p><strong>Note:</strong> You will need to update the storage configurations with your actual credentials.</p>
    """
    ).format(file_count, frappe.local.site, report_path)

    frappe.msgprint(
        msg,
        title=_("Cloud Storage Reconnection Available"),
        indicator="blue",
        is_minimizable=True,
    )


def try_auto_reconnect(report_path):
    """Try to run auto reconnection in a separate process"""
    try:
        # Run reconnection tool in auto mode
        site_name = frappe.local.site
        bench_path = frappe.utils.get_bench_path()

        cmd = [
            "python",
            "-m",
            "frappe.utils.bench_helper",
            "frappe",
            "--site",
            site_name,
            "execute",
            "dfp_external_storage.reconnect.run_auto_reconnect",
            report_path,
        ]

        # Run in background
        subprocess.Popen(
            cmd, cwd=bench_path, stdout=subprocess.PIPE, stderr=subprocess.PIPE
        )
    except Exception as e:
        frappe.log_error(f"Error running auto reconnection: {str(e)}")


# Helper function to be executed by scheduler
@frappe.whitelist()
def run_auto_reconnect(report_path=None):
    """Run reconnection tool in auto mode"""
    # This function is called via the scheduler or command line
    try:
        if not report_path:
            # Find the most recent report
            reports_dir = os.path.join(
                frappe.get_site_path(),
                "private",
                "files",
                "dfp_external_storage_reports",
            )
            if not os.path.exists(reports_dir):
                return

            report_files = [
                f
                for f in os.listdir(reports_dir)
                if f.startswith("external_files_report_")
            ]
            if not report_files:
                return

            report_files.sort(reverse=True)  # Most recent first
            report_path = os.path.join(reports_dir, report_files[0])

        # Import the reconnection tool and run it
        from dfp_external_storage.reconnect import main as reconnect_main

        # Setup args
        class Args:
            pass

        args = Args()
        args.report_path = report_path
        args.yes = True
        args.auto = True
        args.dry_run = False

        # Run reconnection
        reconnect_main()

        # Add a message to the info center
        frappe.publish_realtime(
            event="eval_js",
            message="frappe.show_alert({message: 'Cloud storage reconnection completed. Please check the storage configurations.', indicator: 'green'}, 15);",
        )
    except Exception as e:
        frappe.log_error(f"Auto reconnection failed: {str(e)}")
