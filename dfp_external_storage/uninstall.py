"""
DFP External Storage - Uninstall Script
This script runs automatically when uninstalling the app, and checks
for external files that might be affected by the uninstallation.
"""

import frappe
import os
from frappe import _
from frappe.utils import now_datetime


def before_uninstall():
    """Run before the app is uninstalled"""
    pass
    # # Check if there are external files
    # file_count = frappe.db.count("File", {"dfp_external_storage": ["!=", ""]})

    # if file_count > 0:
    #     # Generate a report of external files
    #     generate_report()

    #     # Show a warning message to the user
    #     frappe.throw(_(
    #         """
    #         WARNING: You have {0} files stored in external storage.

    #         Uninstalling this app will break the connection to these files.
    #         The files will remain in cloud storage but won't be accessible through Frappe.

    #         Please run our uninstall helper first to properly handle these files:

    #         bench --site {1} execute dfp_external_storage/uninstall_helper.py

    #         If you prefer to keep the files in cloud storage, use the --keep-all flag:
    #         bench --site {1} execute dfp_external_storage/uninstall_helper.py --keep-all

    #         A report of your external files has been generated in the site's private files.
    #         """
    #     ).format(file_count, frappe.local.site), title=_("External Files Found"))


def generate_report():
    """Generate a report of externally stored files"""
    # Create reports directory if it doesn't exist
    reports_dir = os.path.join(
        frappe.get_site_path(), "private", "files", "dfp_external_storage_reports"
    )
    if not os.path.exists(reports_dir):
        os.makedirs(reports_dir)

    # Create report file
    timestamp = now_datetime().strftime("%Y%m%d_%H%M%S")
    report_path = os.path.join(reports_dir, f"external_files_report_{timestamp}.csv")

    with open(report_path, "w") as report_file:
        # Write header
        report_file.write(
            "File ID,File Name,Storage Type,Storage Name,External Path,File Size,Is Private,Content Hash\n"
        )

        # Get all external files with storage information
        files = frappe.db.sql(
            """
            SELECT 
                f.name, f.file_name, f.dfp_external_storage, 
                f.dfp_external_storage_s3_key, f.file_size,
                f.is_private, f.content_hash, des.type as storage_type
            FROM `tabFile` f
            JOIN `tabDFP External Storage` des ON f.dfp_external_storage = des.name
            WHERE f.dfp_external_storage != ""
        """,
            as_dict=True,
        )

        # Write file details
        for f in files:
            report_file.write(
                f'"{f.name}","{f.file_name}","{f.storage_type}","{f.dfp_external_storage}",'
            )
            report_file.write(
                f'"{f.dfp_external_storage_s3_key}",{f.file_size},{1 if f.is_private else 0},"{f.content_hash}"\n'
            )

    frappe.msgprint(_("External files report generated at: {0}").format(report_path))
    return report_path
