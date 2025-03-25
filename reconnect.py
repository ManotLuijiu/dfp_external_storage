#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
DFP External Storage - Reconnection Tool

This script helps reconnect to cloud files after reinstalling the DFP External Storage app.
It uses the report generated during uninstallation to restore connections.

Usage:
    bench --site [site-name] execute dfp_external_storage/reconnect.py [csv_report_path]

Options:
    --yes       : Skip confirmation prompts
    --auto      : Run in automatic mode (for installation hook)
    --dry-run   : Only report actions without making changes

Example:
    bench --site mysite.localhost execute dfp_external_storage/reconnect.py \
        private/files/dfp_external_storage_reports/external_files_report_20240324_120000.csv
"""

import frappe
import os
import csv
import argparse
import sys
from datetime import datetime
import json

# Global variables
log_file = None


def log(message, console_only=False):
    """Write messages to both console and log file"""
    print(message)
    if log_file and not console_only:
        log_file.write(f"{message}\n")
        log_file.flush()


def find_latest_report():
    """Find the most recent report file"""
    reports_dir = os.path.join(
        frappe.get_site_path(), "private", "files", "dfp_external_storage_reports"
    )
    if not os.path.exists(reports_dir):
        return None

    report_files = [
        f for f in os.listdir(reports_dir) if f.startswith("external_files_report_")
    ]
    report_files.sort(reverse=True)  # Most recent first

    if not report_files:
        return None

    return os.path.join(reports_dir, report_files[0])


def check_for_disconnected_files():
    """Check if there are files that might be disconnected from cloud storage"""
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


def recreate_storage_configurations(report_data):
    """Recreate storage configurations from report data"""
    log("Recreating storage configurations...")

    storage_configs = {}
    storage_types = {}

    for file_data in report_data:
        storage_name = file_data["Storage Name"]
        storage_type = file_data["Storage Type"]

        storage_types[storage_name] = storage_type

        if storage_name in storage_configs:
            continue

        # Check if config already exists in database
        if frappe.db.exists("DFP External Storage", storage_name):
            storage_configs[storage_name] = frappe.get_doc(
                "DFP External Storage", storage_name
            )
            continue

        # Create a placeholder configuration
        storage_config = frappe.new_doc("DFP External Storage")
        storage_config.title = f"{storage_type} Configuration (Reconnected)"
        storage_config.type = storage_type
        storage_config.enabled = 1

        if storage_type in ["AWS S3", "S3 Compatible"]:
            storage_config.endpoint = "RECONNECT_NEEDED"
            storage_config.bucket_name = "RECONNECT_NEEDED"
            storage_config.region = "auto"
            storage_config.access_key = "RECONNECT_NEEDED"
            storage_config.secret_key = "RECONNECT_NEEDED"
        elif storage_type == "Google Drive":
            storage_config.google_client_id = "RECONNECT_NEEDED"
            storage_config.google_client_secret = "RECONNECT_NEEDED"
            storage_config.google_folder_id = "RECONNECT_NEEDED"
        elif storage_type == "OneDrive":
            storage_config.onedrive_client_id = "RECONNECT_NEEDED"
            storage_config.onedrive_client_secret = "RECONNECT_NEEDED"
            storage_config.onedrive_folder_id = "RECONNECT_NEEDED"
        elif storage_type == "Dropbox":
            storage_config.dropbox_app_key = "RECONNECT_NEEDED"
            storage_config.dropbox_app_secret = "RECONNECT_NEEDED"
            storage_config.dropbox_folder_path = "/RECONNECT_NEEDED"

        if not args.dry_run:
            storage_config.insert(ignore_permissions=True)
            storage_configs[storage_name] = storage_config
            log(f"Created placeholder configuration for {storage_type}: {storage_name}")
        else:
            log(
                f"Would create placeholder configuration for {storage_type}: {storage_name}"
            )

    if not args.dry_run:
        frappe.db.commit()

    log(f"Created/found {len(storage_configs)} storage configurations")
    return storage_configs, storage_types


def reconnect_files(report_data, storage_configs, storage_types):
    """Reconnect file records to cloud storage"""
    log(f"Reconnecting {len(report_data)} files to cloud storage...")

    # Import here to avoid circular imports
    try:
        from dfp_external_storage.dfp_external_storage.doctype.dfp_external_storage.dfp_external_storage import (
            DFP_EXTERNAL_STORAGE_URL_SEGMENT_FOR_FILE_LOAD,
        )
    except ImportError:
        DFP_EXTERNAL_STORAGE_URL_SEGMENT_FOR_FILE_LOAD = "file"  # Default value

    updated_count = 0
    skipped_count = 0
    error_count = 0

    # Group files by 100 to avoid processing too many at once
    batch_size = 100
    total_batches = (len(report_data) + batch_size - 1) // batch_size

    for batch_idx in range(total_batches):
        start_idx = batch_idx * batch_size
        end_idx = min(start_idx + batch_size, len(report_data))
        batch = report_data[start_idx:end_idx]

        log(f"Processing batch {batch_idx + 1}/{total_batches} ({len(batch)} files)")

        for file_data in batch:
            try:
                file_id = file_data["File ID"]

                # Check if file still exists
                if not frappe.db.exists("File", file_id):
                    log(f"File {file_id} not found, skipping")
                    skipped_count += 1
                    continue

                # Get file document
                file_doc = frappe.get_doc("File", file_id)

                # Check if already connected
                if (
                    file_doc.dfp_external_storage
                    and file_doc.dfp_external_storage_s3_key
                ):
                    skipped_count += 1
                    continue

                # Get storage type
                storage_name = file_data["Storage Name"]

                if args.dry_run:
                    log(f"Would reconnect file {file_id} to {storage_name}")
                    updated_count += 1
                    continue

                # Update file document
                file_doc.dfp_external_storage = storage_name
                file_doc.dfp_external_storage_s3_key = file_data["External Path"]

                # Update file URL
                file_doc.file_url = f"/{DFP_EXTERNAL_STORAGE_URL_SEGMENT_FOR_FILE_LOAD}/{file_doc.name}/{file_doc.file_name}"

                # Save document
                file_doc.db_update()
                updated_count += 1

            except Exception as e:
                log(f"Error reconnecting file {file_data['File ID']}: {str(e)}")
                error_count += 1

        if not args.dry_run:
            frappe.db.commit()

    return updated_count, skipped_count, error_count


def parse_report(report_path):
    """Parse the report CSV file"""
    report_data = []

    with open(report_path, "r") as f:
        reader = csv.DictReader(f)
        for row in reader:
            report_data.append(row)

    return report_data


def save_reconnection_info(storage_types):
    """Save reconnection information to a file for later notification"""
    info = {
        "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "storage_types": storage_types,
    }

    # Create directory if it doesn't exist
    info_dir = os.path.join(
        frappe.get_site_path(), "private", "files", "dfp_external_storage_info"
    )
    if not os.path.exists(info_dir):
        os.makedirs(info_dir)

    # Save info file
    info_path = os.path.join(info_dir, "reconnection_info.json")
    with open(info_path, "w") as f:
        json.dump(info, f, indent=2)

    return info_path


def setup_logging():
    """Set up logging to file"""
    global log_file

    # Create logs directory if it doesn't exist
    logs_dir = os.path.join(frappe.get_site_path(), "logs")
    if not os.path.exists(logs_dir):
        os.makedirs(logs_dir)

    # Create log file
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    log_path = os.path.join(logs_dir, f"dfp_external_storage_reconnect_{timestamp}.log")

    log_file = open(log_path, "w")
    return log_path


def main():
    """Main function for reconnection tool"""
    log("\n========== DFP External Storage Reconnection Tool ==========\n")

    # If running in auto mode during installation, first check if we need to reconnect
    if args.auto:
        disconnected_count = check_for_disconnected_files()
        if disconnected_count == 0:
            log("No disconnected files found. Skipping reconnection.")
            return

        log(f"Found {disconnected_count} potentially disconnected files.")

    # Find report file
    report_path = args.report_path
    if not report_path:
        report_path = find_latest_report()

    if not report_path or not os.path.exists(report_path):
        log(
            "Error: No report file found. Please specify the path to the report CSV file."
        )
        return

    log(f"Using report file: {report_path}")

    # Parse report
    try:
        report_data = parse_report(report_path)
        log(f"Found {len(report_data)} files in the report")
    except Exception as e:
        log(f"Error parsing report file: {str(e)}")
        return

    # Confirm action if not in auto mode
    if not args.yes and not args.auto:
        response = (
            input(
                "This will attempt to reconnect file records to cloud storage. Continue? (y/n) [n]: "
            )
            .lower()
            .strip()
        )
        if not response or response[0] != "y":
            log("Operation cancelled.")
            return

    # Recreate storage configurations
    storage_configs, storage_types = recreate_storage_configurations(report_data)

    # Reconnect files
    updated_count, skipped_count, error_count = reconnect_files(
        report_data, storage_configs, storage_types
    )

    log("\nReconnection complete!")
    log(f"- {updated_count} files reconnected")
    log(f"- {skipped_count} files skipped (already connected or not found)")
    log(f"- {error_count} errors")

    # Save reconnection info for later notification
    if not args.dry_run:
        info_path = save_reconnection_info(storage_types)
        log(f"Reconnection info saved to: {info_path}")

    # Show notification in auto mode
    if args.auto and updated_count > 0:
        frappe.msgprint(
            f"Reconnected {updated_count} files to cloud storage. <br><br>"
            f"Please update your storage configurations with the proper credentials.<br>"
            f"See the DFP External Storage list to configure your connections."
        )
    elif not args.auto:
        log("\nImportant: You need to configure your storage connections properly!")
        log("The tool created placeholder configurations that need your credentials.")
        log("Please go to DFP External Storage list and update the configurations.")


if __name__ == "__main__":
    # Parse arguments
    parser = argparse.ArgumentParser(
        description="DFP External Storage Reconnection Tool"
    )
    parser.add_argument("report_path", nargs="?", help="Path to the report CSV file")
    parser.add_argument(
        "--yes", "-y", action="store_true", help="Skip confirmation prompt"
    )
    parser.add_argument(
        "--auto",
        "-a",
        action="store_true",
        help="Run in automatic mode (for installation hook)",
    )
    parser.add_argument(
        "--dry-run", "-d", action="store_true", help="Only show what would be done"
    )

    args = parser.parse_args()

    # Set up logging
    log_path = setup_logging()

    try:
        main()
    except Exception as e:
        log(f"An error occurred: {str(e)}")
        import traceback

        traceback.print_exc()

    if log_file:
        log_file.close()
