# Copyright (c) 2015, Frappe Technologies Pvt. Ltd. and Contributors
# License: MIT. See LICENSE

import frappe
from frappe import _


@frappe.whitelist()
def diagnose_storage_connection(storage_name=None):
    """API endpoint to diagnose S3 storage connection"""
    try:
        if not storage_name:
            storage_name = frappe.get_route()[1]  # Get from URL if not provided

        if not storage_name:
            frappe.throw(_("Storage name is required"))

        doc = frappe.get_doc("DFP External Storage", storage_name)

        # Check configuration
        issues = doc.diagnose_storage_config()
        if issues:
            frappe.msgprint(
                _("Configuration issues found: {}").format(", ".join(issues)),
                indicator="red",
            )
            return False

        # Verify connection
        if doc.verify_connection():
            frappe.msgprint(_("Connection successful"), indicator="green")
            return True
        else:
            frappe.msgprint(_("Connection failed"), indicator="red")
            return False

    except Exception as e:
        frappe.log_error(f"Storage diagnosis failed: {str(e)}")
        frappe.throw(_("Failed to diagnose storage connection: {}").format(str(e)))


@frappe.whitelist()
def get_info(storage=None, template=None, file_type=None) -> list[dict]:
    files = []

    frappe.logger().info(
        f"S3 bucket list - get_info called with storage={storage}, template={template}, file_type={file_type}"
    )

    # Get current site name for filtering
    current_site = frappe.local.site
    frappe.logger().info(f"Current site: {current_site}")

    document = "DFP External Storage"

    dfp_external_storage_doc = None
    if storage:
        dfp_external_storage_doc = frappe.get_doc(document, storage)
    else:
        last_id = frappe.get_all(
            document, filters={"enabled": 1}, order_by="modified desc", limit=1
        )
        if last_id:
            dfp_external_storage_doc = frappe.get_doc(
                document, last_id[0].name if last_id else None
            )

    if dfp_external_storage_doc:
        try:
            # dfp_external_storage_doc.remote_files_list(template, file_type)
            objects = dfp_external_storage_doc.remote_files_list()
            for file in objects:
                file_data = {}
                # Check if file is a dictionary or an object
                if isinstance(file, dict):
                    key = file.get("Key", "")

                    # Only include files from the current site
                    if not key.startswith(current_site + "/") and not key.startswith(
                        "Home/"
                    ):
                        continue

                    file_data = {
                        "etag": file.get("ETag", ""),
                        "is_dir": False,
                        "last_modified": file.get("LastModified", ""),
                        "metadata": file.get("Metadata", {}),
                        "name": key,
                        "size": file.get("Size", 0),
                        "storage_class": file.get("StorageClass", ""),
                    }
                else:
                    # Try to access as object attributes
                    try:
                        object_name = getattr(file, "object_name", "")
                        # Only include files from the current site
                        if not object_name.startswith(
                            current_site + "/"
                        ) and not object_name.startswith("Home/"):
                            continue

                        file_data = {
                            "etag": getattr(file, "etag", ""),
                            "is_dir": getattr(file, "is_dir", False),
                            "last_modified": getattr(file, "last_modified", ""),
                            "metadata": getattr(file, "metadata", {}),
                            "name": object_name,
                            "size": getattr(file, "size", 0),
                            "storage_class": getattr(file, "storage_class", ""),
                        }
                    except Exception as e:
                        frappe.log_error(f"Error processing S3 object: {str(e)}")
                        continue

                if file_data:
                    files.append(file_data)
        except Exception as e:
            frappe.log_error(f"Error listing S3 bucket contents: {str(e)}")

    return files
