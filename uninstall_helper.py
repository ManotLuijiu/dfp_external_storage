#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
DFP External Storage - Uninstall Helper

This script helps safely uninstall the DFP External Storage app by providing
options to handle externally stored files. It can:
1. Move all files back to local storage before uninstalling
2. Generate a report of all externally stored files
3. Proceed with uninstallation while keeping files in cloud storage

Usage:
    bench --site [site-name] execute dfp_external_storage/uninstall.py [--dry-run] [--move-all]

Options:
    --dry-run    : Only report what would be done, don't actually move files or uninstall
    --move-all   : Automatically move all files to local storage without prompting
    --keep-all   : Keep all files in cloud storage and proceed with uninstall
    --report-only: Just generate a report of externally stored files without uninstalling

Example:
    bench --site mysite.localhost execute dfp_external_storage/uninstall.py
"""

import frappe
import os
import argparse
import sys
import time
from datetime import datetime
from tqdm import tqdm

# Setup argument parsing for command-line options
parser = argparse.ArgumentParser(description="DFP External Storage Uninstall Helper")
parser.add_argument(
    "--dry-run", action="store_true", help="Report only, do not make any changes"
)
parser.add_argument(
    "--move-all",
    action="store_true",
    help="Move all files to local storage without prompting",
)
parser.add_argument(
    "--keep-all",
    action="store_true",
    help="Keep all files in cloud and proceed with uninstall",
)
parser.add_argument(
    "--report-only", action="store_true", help="Generate a report without uninstalling"
)

# Global variables
log_file = None


def log(message, console_only=False):
    """Write messages to both console and log file"""
    print(message)
    if log_file and not console_only:
        log_file.write(f"{message}\n")
        log_file.flush()


def get_external_file_count():
    """Get the count of files stored in external storage"""
    count = frappe.db.count("File", {"dfp_external_storage": ["!=", ""]})
    return count


def get_external_storage_info():
    """Get information about external storage configurations"""
    storage_info = {}

    # Get list of all external storage configurations
    external_storages = frappe.get_all(
        "DFP External Storage",
        fields=["name", "type", "title", "bucket_name", "enabled"],
    )

    for storage in external_storages:
        # Count files in this storage
        file_count = frappe.db.count("File", {"dfp_external_storage": storage.name})
        storage_info[storage.name] = {
            "name": storage.name,
            "type": storage.type,
            "title": storage.title,
            "bucket_name": (
                storage.bucket_name if hasattr(storage, "bucket_name") else None
            ),
            "enabled": storage.enabled,
            "file_count": file_count,
        }

    return storage_info


def get_storage_type_counts():
    """Get count of files by storage type"""
    result = frappe.db.sql(
        """
        SELECT des.type, COUNT(*) as count
        FROM `tabFile` f
        JOIN `tabDFP External Storage` des ON f.dfp_external_storage = des.name
        WHERE f.dfp_external_storage != ""
        GROUP BY des.type
    """,
        as_dict=True,
    )

    counts = {r.type: r.count for r in result}
    return counts


def generate_file_report():
    """Generate a detailed report of all externally stored files"""
    log("Generating report of externally stored files...")

    # Create reports directory if it doesn't exist
    reports_dir = os.path.join(
        frappe.get_site_path(), "private", "files", "dfp_external_storage_reports"
    )
    if not os.path.exists(reports_dir):
        os.makedirs(reports_dir)

    # Create report file
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
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

    log(f"Report generated: {report_path}")
    return report_path


def confirm_action(message, default=False):
    """Ask user for confirmation"""
    if args.dry_run:
        return False

    if args.move_all:
        return True

    if args.keep_all:
        return False

    try:
        response = (
            input(f"{message} (y/n) [{'y' if default else 'n'}]: ").lower().strip()
        )
        if not response:
            return default
        return response[0] == "y"
    except KeyboardInterrupt:
        log("\nOperation cancelled by user.")
        sys.exit(1)


def move_files_to_local_storage(storage_filter=None):
    """Move files from external storage back to local storage"""
    if args.dry_run:
        log("DRY RUN: Would move files to local storage")
        return

    # Build filter for files
    filters = {"dfp_external_storage": ["!=", ""]}
    if storage_filter:
        filters["dfp_external_storage"] = storage_filter

    # Get count for progress bar
    file_count = frappe.db.count("File", filters)

    if file_count == 0:
        log("No files to move.")
        return

    log(f"Moving {file_count} files to local storage. This may take some time...")

    # Get files in batches to avoid memory issues
    batch_size = 10
    offset = 0
    moved_count = 0
    error_count = 0

    progress_bar = tqdm(total=file_count, unit="files")

    while True:
        files = frappe.get_all(
            "File", filters=filters, fields=["name"], limit=batch_size, start=offset
        )

        if not files:
            break

        for file_dict in files:
            try:
                # Get the file document
                file_doc = frappe.get_doc("File", file_dict.name)

                if hasattr(file_doc, "download_to_local_and_remove_remote"):
                    # Move file to local storage
                    file_doc.download_to_local_and_remove_remote()
                    moved_count += 1
                else:
                    log(
                        f"Error: File {file_doc.name} doesn't have the required methods. Skipping."
                    )
                    error_count += 1
            except Exception as e:
                log(f"Error moving file {file_dict.name}: {str(e)}")
                error_count += 1

            progress_bar.update(1)

        offset += batch_size

        # Commit transaction every batch
        frappe.db.commit()

    progress_bar.close()

    log(
        f"Moved {moved_count} files to local storage successfully. {error_count} errors occurred."
    )
    return moved_count, error_count


def uninstall_app():
    """Uninstall the DFP External Storage app"""
    if args.dry_run or args.report_only:
        log("Would uninstall the DFP External Storage app now")
        return

    log("Uninstalling DFP External Storage app...")

    # Execute bench command to uninstall
    site_name = frappe.local.site
    os.system(
        f"cd {frappe.get_app_path('frappe')[:-7]} && bench --site {site_name} uninstall-app dfp_external_storage --yes"
    )

    log("DFP External Storage has been uninstalled")


def setup_logging():
    """Set up logging to file"""
    global log_file

    # Create logs directory if it doesn't exist
    logs_dir = os.path.join(frappe.get_site_path(), "logs")
    if not os.path.exists(logs_dir):
        os.makedirs(logs_dir)

    # Create log file
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    log_path = os.path.join(logs_dir, f"dfp_external_storage_uninstall_{timestamp}.log")

    log_file = open(log_path, "w")
    return log_path


def main():
    """Main function for uninstall helper"""
    print("\n========== DFP External Storage Uninstall Helper ==========\n")

    # Set up logging
    log_path = setup_logging()
    log(f"Logging to: {log_path}")

    # Get count of externally stored files
    file_count = get_external_file_count()
    log(f"Found {file_count} files stored in external storage")

    if file_count == 0:
        log("No files stored in external storage. Safe to uninstall.")

        if args.report_only:
            return

        if confirm_action("Proceed with uninstallation?", default=True):
            uninstall_app()
        return

    # Get storage information
    storage_info = get_external_storage_info()
    log(f"Found {len(storage_info)} external storage configurations:")

    for storage in storage_info.values():
        log(
            f"  - {storage['title']} ({storage['type']}): {storage['file_count']} files"
        )

    # Generate file counts by storage type
    type_counts = get_storage_type_counts()
    log("\nFile counts by storage type:")
    for storage_type, count in type_counts.items():
        log(f"  - {storage_type}: {count} files")

    # Generate report
    report_path = generate_file_report()

    # If report only, exit here
    if args.report_only:
        log("\nReport generation complete. Exiting without uninstallation.")
        return

    # Warn user about consequences
    log("\n⚠️  WARNING ⚠️")
    log("Uninstalling DFP External Storage will affect how files are accessed.")
    log("If you keep files in cloud storage:")
    log("- File links in your system will be broken")
    log("- You won't be able to access files through Frappe/ERPNext")
    log("- The files will remain in their respective cloud storage services")

    # Ask user what to do
    print("\nPlease choose an option:")
    print("1. Move all files back to local storage before uninstalling")
    print("2. Keep files in cloud storage and proceed with uninstall")
    print("3. Cancel uninstallation")

    if args.move_all:
        choice = "1"
    elif args.keep_all:
        choice = "2"
    elif args.dry_run:
        choice = "3"
    else:
        choice = input("\nEnter your choice (1-3): ")

    if choice == "1":
        log("\nMoving all files back to local storage...")
        moved_count, error_count = move_files_to_local_storage()

        if error_count > 0:
            log(f"\n⚠️ {error_count} errors occurred during file migration.")
            log(f"Please check the log file at {log_path} for details.")

            if not confirm_action(
                "Some errors occurred. Continue with uninstallation anyway?",
                default=False,
            ):
                log("Uninstallation cancelled.")
                return

        if confirm_action(
            "All files have been moved to local storage. Proceed with uninstallation?",
            default=True,
        ):
            uninstall_app()

    elif choice == "2":
        log("\nKeeping files in cloud storage...")
        if confirm_action(
            "Are you sure you want to keep files in cloud storage? File access will be broken after uninstallation.",
            default=False,
        ):
            uninstall_app()
        else:
            log("Uninstallation cancelled.")

    else:
        log("\nUninstallation cancelled.")

    if log_file:
        log_file.close()


if __name__ == "__main__":
    # Parse command line arguments
    args = parser.parse_args()

    # Import tqdm if not available
    try:
        from tqdm import tqdm
    except ImportError:
        try:
            import pip

            print("Installing required package: tqdm")
            pip.main(["install", "tqdm"])
            from tqdm import tqdm
        except:
            # Define a simple tqdm replacement if installation fails
            class SimpleTqdm:
                def __init__(self, total, unit):
                    self.total = total
                    self.current = 0
                    self.unit = unit
                    print(f"Processing {total} {unit}...")

                def update(self, n):
                    self.current += n
                    if self.current % 10 == 0:
                        print(f"Processed {self.current}/{self.total} {self.unit}")

                def close(self):
                    print(
                        f"Completed processing {self.current}/{self.total} {self.unit}"
                    )

            tqdm = SimpleTqdm

    try:
        main()
    except Exception as e:
        print(f"An error occurred: {str(e)}")
        import traceback

        traceback.print_exc()
