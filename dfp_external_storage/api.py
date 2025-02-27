import frappe
from frappe import _


@frappe.whitelist()
def get_media_library():
    """Get S3 file library"""
    files = frappe.get_all(
        "File",
        filters={"is_folder": 0, "dfp.external_storage": ("is", "set")},
        fields=[
            "name",
            "file_name",
            "file_url",
            "is_private",
            "dfp_external_storage",
            "dfp_external_storage_s3_key",
        ],
    )

    return files


@frappe.whitelist()
def get_presigned_url(file_id):
    """Get secure presigned URL for a file with proper expiration"""
    try:
        file_doc = frappe.get_doc("File", file_id)
        if (
            not file_doc.dfp_external_storage
            or not file_doc.dfp_external_storage_s3_key
        ):
            return {"success": False, "message": "File not stored in S3"}
        storage_doc = frappe.get_doc(
            "DFP External Storage", file_doc.dfp_external_storage
        )

        # Check if presigned URLs are enabled
        if not storage_doc.presigned_urls:
            return {"success": False, "message": "Could not generate presigned URL"}
        # Get presigned URL with proper expiration
        presigned_url = file_doc.dfp_presigned_url_get()
        if not presigned_url:
            return {"success": False, "message": "Could not generate presigned URL"}

        return {
            "success": True,
            "presigned_url": presigned_url,
            "file_name": file_doc.file_name,
            "expiration_seconds": storage_doc.setting_presigned_url_expiration,
        }
    except Exception as e:
        frappe.log_error(f"Error generating presigned URL: {str(e)}")
        return {"success": False, "message": str(e)}


@frappe.whitelist()
def bulk_offload_files(storage_name=None, folder=None, limit=100):
    """Bulk offload files to S3"""
    if not storage_name:
        return {"success": False, "message": "Storage name is required"}

    filters = {"is_folder": 0, "dfp_external_storage": ("is", "not set")}
    if folder:
        filters["folder"] = folder

    files = frappe.get_all("File", filters=filters, fields=["name"], limit=limit)

    success_count = 0
    failed_count = 0
    for file_data in files:
        try:
            file_doc = frappe.get_doc("File", file_data.name)
            file_doc.dfp_external_storage = storage_name
            file_doc.save()
            success_count += 1
        except Exception as e:
            frappe.log_error(f"Bulk offload failed for file {file_data.name}: {str(e)}")
            failed_count += 1

    return {
        "success": True,
        "message": f"Processed {len(files)} files: {success_count} successful, {failed_count} failed",
        "successful": success_count,
        "failed": failed_count,
    }
