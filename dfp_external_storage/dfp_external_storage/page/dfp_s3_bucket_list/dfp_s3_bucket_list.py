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
        # dfp_external_storage_doc.remote_files_list(template, file_type)
        objects = dfp_external_storage_doc.remote_files_list()
        for file in objects:
            files.append(
                {
                    "etag": file.etag,
                    "is_dir": file.is_dir,
                    "last_modified": file.last_modified,
                    "metadata": file.metadata,
                    "name": file.object_name,
                    "size": file.size,
                    "storage_class": file.storage_class,
                }
            )

    return files
