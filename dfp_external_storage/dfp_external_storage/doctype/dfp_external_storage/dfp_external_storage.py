import os
import re
import io
import sys
import logging
import mimetypes
import typing as t
from datetime import timedelta
from werkzeug.wrappers import Response
from werkzeug.wsgi import wrap_file
from functools import cached_property
from minio import Minio
import frappe
from frappe import _
from frappe.core.doctype.file.file import File
from frappe.core.doctype.file.file import URL_PREFIXES
from frappe.model.document import Document
from frappe.utils.password import get_decrypted_password

sys.path.append("/home/frappe/moo-bench/apps/dfp_external_storage")

GoogleDriveConnection = None
OneDriveConnection = None
DropboxConnection = None


def _import_extension_modules():
    """Attempt to import extension modules if they exist"""
    global GoogleDriveConnection, OneDriveConnection, DropboxConnection

    try:
        from dfp_external_storage.gdrive_integration import (
            GoogleDriveConnection as GDrive,
        )

        GoogleDriveConnection = GDrive
    except ImportError:
        pass

    try:
        from dfp_external_storage.onedrive_integration import (
            OneDriveConnection as OneDrive,
        )

        OneDriveConnection = OneDrive
    except ImportError:
        pass

    try:
        from dfp_external_storage.dropbox_integration import (
            DropboxConnection as Dropbox,
        )

        DropboxConnection = Dropbox
    except ImportError:
        pass


# Try to import extension modules at startup
_import_extension_modules()

logging.basicConfig(level=logging.DEBUG)

DFP_EXTERNAL_STORAGE_PUBLIC_CACHE_PREFIX = "external_storage_public_file:"

# http://[host:port]/<file>/[File:name]/[File:file_name]
# http://myhost.localhost:8000/file/c7baa5b2ff/my-image.png
DFP_EXTERNAL_STORAGE_URL_SEGMENT_FOR_FILE_LOAD = "file"


DFP_EXTERNAL_STORAGE_CONNECTION_FIELDS = [
    "type",
    "endpoint",
    "secure",
    "bucket_name",
    "region",
    "access_key",
    "secret_key",
]
DFP_EXTERNAL_STORAGE_CRITICAL_FIELDS = [
    "type",
    "endpoint",
    "secure",
    "bucket_name",
    "region",
    "access_key",
    "secret_key",
    "folders",
]


class DFPExternalStorageOneDriveFile:
    """OneDrive implementation for DFP External Storage File"""

    def __init__(self, file_doc):
        self.file_doc = file_doc
        self.file_name = file_doc.file_name
        self.content_hash = file_doc.content_hash
        self.storage_doc = file_doc.dfp_external_storage_doc
        self.client = self._get_onedrive_client()

    def _get_onedrive_client(self):
        """Initialize OneDrive client"""
        try:
            storage_doc = self.storage_doc
            client_id = storage_doc.onedrive_client_id
            client_secret = get_decrypted_password(
                "DFP External Storage", storage_doc.name, "onedrive_client_secret"
            )
            refresh_token = get_decrypted_password(
                "DFP External Storage", storage_doc.name, "onedrive_refresh_token"
            )
            tenant = storage_doc.onedrive_tenant or "common"

            return OneDriveConnection(
                client_id=client_id,
                client_secret=client_secret,
                tenant=tenant,
                refresh_token=refresh_token,
            )
        except Exception as e:
            frappe.log_error(f"Failed to initialize OneDrive client: {str(e)}")
            return None

    def upload_file(self, local_file=None):
        """
        Upload file to OneDrive

        Args:
            local_file (str): Local file path

        Returns:
            bool: True if upload successful
        """
        try:
            # Check if already uploaded
            if self.file_doc.dfp_external_storage_s3_key:
                return False

            # Determine file path
            is_public = "/public" if not self.file_doc.is_private else ""
            if not local_file:
                local_file = f"./{frappe.local.site}{is_public}{self.file_doc.file_url}"

            # Check if file exists
            if not os.path.exists(local_file):
                frappe.throw(_("Local file not found: {0}").format(local_file))

            # Determine content type
            content_type, _ = mimetypes.guess_type(self.file_name)
            if not content_type:
                content_type = "application/octet-stream"

            # Upload file
            with open(local_file, "rb") as f:
                # Upload to OneDrive
                result = self.client.put_object(
                    folder_id=self.storage_doc.onedrive_folder_id,
                    file_name=self.file_name,
                    data=f,
                    metadata={"Content-Type": content_type},
                )

                # Update file document with OneDrive file ID
                self.file_doc.dfp_external_storage_s3_key = result.get("id")
                self.file_doc.dfp_external_storage = self.storage_doc.name

                # Update file_url to use our custom URL pattern
                from dfp_external_storage.dfp_external_storage.doctype.dfp_external_storage.dfp_external_storage import (
                    DFP_EXTERNAL_STORAGE_URL_SEGMENT_FOR_FILE_LOAD,
                )

                self.file_doc.file_url = f"/{DFP_EXTERNAL_STORAGE_URL_SEGMENT_FOR_FILE_LOAD}/{self.file_doc.name}/{self.file_name}"

                # Remove local file
                os.remove(local_file)
                return True

        except Exception as e:
            error_msg = _("Error saving file to OneDrive: {0}").format(str(e))
            frappe.log_error(f"{error_msg}: {self.file_name}")

            # Reset S3 fields for new file
            if not self.file_doc.get_doc_before_save():
                error_extra = _("File saved in local filesystem.")
                frappe.log_error(f"{error_msg} {error_extra}: {self.file_name}")
                self.file_doc.dfp_external_storage_s3_key = ""
                self.file_doc.dfp_external_storage = ""
                # Keep original file_url
            else:
                frappe.throw(error_msg)

            return False

    def delete_file(self):
        """Delete file from OneDrive"""
        if not self.file_doc.dfp_external_storage_s3_key:
            return False

        # Check if other files use the same key
        files_using_key = frappe.get_all(
            "File",
            filters={
                "dfp_external_storage_s3_key": self.file_doc.dfp_external_storage_s3_key,
                "dfp_external_storage": self.file_doc.dfp_external_storage,
            },
        )

        if len(files_using_key) > 1:
            # Other files are using this OneDrive file, don't delete
            return False

        # Delete from OneDrive
        try:
            self.client.remove_object(
                folder_id=None,  # Not needed for OneDrive
                file_id=self.file_doc.dfp_external_storage_s3_key,
            )
            return True
        except Exception as e:
            error_msg = _("Error deleting file from OneDrive.")
            frappe.log_error(f"{error_msg}: {self.file_name}", message=str(e))
            frappe.throw(f"{error_msg} {str(e)}")
            return False

    def download_file(self):
        """Download file from OneDrive"""
        try:
            file_content = self.client.get_object(
                folder_id=None,  # Not needed for OneDrive
                file_id=self.file_doc.dfp_external_storage_s3_key,
            )
            return file_content.read()
        except Exception as e:
            error_msg = _("Error downloading file from OneDrive")
            frappe.log_error(title=f"{error_msg}: {self.file_name}")
            frappe.throw(error_msg)
            return b""

    def stream_file(self):
        """Stream file from OneDrive"""
        try:
            from werkzeug.wsgi import wrap_file

            file_content = self.client.get_object(
                folder_id=None,  # Not needed for OneDrive
                file_id=self.file_doc.dfp_external_storage_s3_key,
            )

            # Wrap the file content for streaming
            return wrap_file(
                environ=frappe.local.request.environ,
                file=file_content,
                buffer_size=self.storage_doc.setting_stream_buffer_size,
            )
        except Exception as e:
            frappe.log_error(f"OneDrive streaming error: {str(e)}")
            frappe.throw(_("Failed to stream file from OneDrive"))

    def download_to_local_and_remove_remote(self):
        """Download file from OneDrive and remove the remote file"""
        try:
            # Get file content
            file_content = self.client.get_object(
                folder_id=None,  # Not needed for OneDrive
                file_id=self.file_doc.dfp_external_storage_s3_key,
            )

            # Save content
            self.file_doc._content = file_content.read()

            # Clear storage info
            file_id = self.file_doc.dfp_external_storage_s3_key
            self.file_doc.dfp_external_storage_s3_key = ""
            self.file_doc.dfp_external_storage = ""

            # Save to filesystem
            self.file_doc.save_file_on_filesystem()

            # Delete from OneDrive
            self.client.remove_object(
                folder_id=None, file_id=file_id  # Not needed for OneDrive
            )

            return True
        except Exception as e:
            error_msg = _("Error downloading and removing file from OneDrive.")
            frappe.log_error(title=f"{error_msg}: {self.file_name}")
            frappe.throw(error_msg)
            return False

    def get_presigned_url(self):
        """Get a presigned URL for the file"""
        try:
            if not self.storage_doc.presigned_urls:
                return None

            # Check mimetype restrictions
            if (
                self.storage_doc.presigned_mimetypes_starting
                and self.file_doc.dfp_mime_type_guess_by_file_name
            ):
                presigned_mimetypes_starting = [
                    i.strip()
                    for i in self.storage_doc.presigned_mimetypes_starting.split("\n")
                    if i.strip()
                ]

                if not any(
                    self.file_doc.dfp_mime_type_guess_by_file_name.startswith(i)
                    for i in presigned_mimetypes_starting
                ):
                    return None

            # Get presigned URL
            return self.client.presigned_get_object(
                folder_id=None,  # Not needed for OneDrive
                file_id=self.file_doc.dfp_external_storage_s3_key,
                expires=self.storage_doc.setting_presigned_url_expiration,
            )
        except Exception as e:
            frappe.log_error(f"Error generating OneDrive presigned URL: {str(e)}")
            return None


class DFPExternalStorageGoogleDriveFile:
    """Google Drive implementation for DFP External Storage File"""

    def __init__(self, file_doc):
        self.file_doc = file_doc
        self.file_name = file_doc.file_name
        self.content_hash = file_doc.content_hash
        self.storage_doc = file_doc.dfp_external_storage_doc
        self.client = self._get_google_drive_client()

    def _get_google_drive_client(self):
        """Initialize Google Drive client"""
        try:
            storage_doc = self.storage_doc
            client_id = storage_doc.google_client_id
            client_secret = get_decrypted_password(
                "DFP External Storage", storage_doc.name, "google_client_secret"
            )
            refresh_token = get_decrypted_password(
                "DFP External Storage", storage_doc.name, "google_refresh_token"
            )

            return GoogleDriveConnection(
                client_id=client_id,
                client_secret=client_secret,
                refresh_token=refresh_token,
            )

        except Exception as e:
            frappe.log_error(f"Failed to initialize Google Drive client: {str(e)}")
            return None

    def upload_file(self, local_file=None):
        """
        Upload file to Google Drive

        Args:
            local_file (str): Local file path

        Returns:
            bool: True if upload successful
        """
        try:
            # Check if already uploaded
            if self.file_doc.dfp_external_storage_s3_key:
                return False

            # Determine file path
            is_public = "/public" if not self.file_doc.is_private else ""
            if not local_file:
                local_file = f"./{frappe.local.site}{is_public}{self.file_doc.file_url}"

            # Check if file exists
            if not os.path.exists(local_file):
                frappe.throw(_("Local file not found: {0}").format(local_file))

            # Determine content type
            content_type, _ = mimetypes.guess_type(self.file_name)
            if not content_type:
                content_type = "application/octet-stream"

            # Upload file
            with open(local_file, "rb") as f:
                file_size = os.path.getsize(local_file)

                # Upload to Google Drive
                result = self.client.put_object(
                    folder_id=self.storage_doc.google_folder_id,
                    file_name=self.file_name,
                    data=f,
                    metadata={"Content-Type": content_type},
                )

                # Update file document with Google Drive file ID
                self.file_doc.dfp_external_storage_s3_key = result.get("id")
                self.file_doc.dfp_external_storage = self.storage_doc.name
                self.file_doc.file_url = f"/{DFP_EXTERNAL_STORAGE_URL_SEGMENT_FOR_FILE_LOAD}/{self.file_doc.name}/{self.file_name}"

                # Remove local file
                os.remove(local_file)
                return True

        except Exception as e:
            error_msg = _("Error saving file to Google Drive: {0}").format(str(e))
            frappe.log_error(f"{error_msg}: {self.file_name}")

            # Reset S3 fields for new file
            if not self.file_doc.get_doc_before_save():
                error_extra = _("File saved in local filesystem.")
                frappe.log_error(f"{error_msg} {error_extra}: {self.file_name}")
                self.file_doc.dfp_external_storage_s3_key = ""
                self.file_doc.dfp_external_storage = ""
                # Keep original file_url
            else:
                frappe.throw(error_msg)

            return False

    def delete_file(self):
        """Delete file from Google Drive"""
        """Delete file from Google Drive"""
        if not self.file_doc.dfp_external_storage_s3_key:
            return False

        # Check if other files use the same key
        files_using_key = frappe.get_all(
            "File",
            filters={
                "dfp_external_storage_s3_key": self.file_doc.dfp_external_storage_s3_key,
                "dfp_external_storage": self.file_doc.dfp_external_storage,
            },
        )

        if len(files_using_key) > 1:
            # Other files are using this Drive file, don't delete
            return False

        # Delete from Google Drive
        try:
            self.client.remove_object(
                folder_id=self.storage_doc.google_folder_id,
                file_id=self.file_doc.dfp_external_storage_s3_key,
            )
            return True
        except Exception as e:
            error_msg = _("Error deleting file from Google Drive.")
            frappe.log_error(f"{error_msg}: {self.file_name}", message=str(e))
            frappe.throw(f"{error_msg} {str(e)}")
            return False

    def download_file(self):
        """Download file from Google Drive"""
        try:
            file_content = self.client.get_object(
                folder_id=self.storage_doc.google_folder_id,
                file_id=self.file_doc.dfp_external_storage_s3_key,
            )
            return file_content.read()
        except Exception as e:
            error_msg = _("Error downloading file from Google Drive")
            frappe.log_error(title=f"{error_msg}: {self.file_name}")
            frappe.throw(error_msg)
            return b""

    def stream_file(self):
        """Stream file from Google Drive"""
        try:
            file_content = self.client.get_object(
                folder_id=self.storage_doc.google_folder_id,
                file_id=self.file_doc.dfp_external_storage_s3_key,
            )

            # Wrap the file content for streaming
            return wrap_file(
                environ=frappe.local.request.environ,
                file=file_content,
                buffer_size=self.storage_doc.setting_stream_buffer_size,
            )
        except Exception as e:
            frappe.log_error(f"Google Drive streaming error: {str(e)}")
            frappe.throw(_("Failed to stream file from Google Drive"))

    def download_to_local_and_remove_remote(self):
        """Download file from Google Drive and remove the remote file"""
        try:
            # Get file content
            file_content = self.client.get_object(
                folder_id=self.storage_doc.google_folder_id,
                file_id=self.file_doc.dfp_external_storage_s3_key,
            )

            # Save content
            self.file_doc._content = file_content.read()

            # Clear storage info
            self.file_doc.dfp_external_storage_s3_key = ""
            self.file_doc.dfp_external_storage = ""

            # Save to filesystem
            self.file_doc.save_file_on_filesystem()

            # Delete from Google Drive
            self.client.remove_object(
                folder_id=self.storage_doc.google_folder_id,
                file_id=self.file_doc.dfp_external_storage_s3_key,
            )

            return True
        except Exception as e:
            error_msg = _("Error downloading and removing file from Google Drive.")
            frappe.log_error(title=f"{error_msg}: {self.file_name}")
            frappe.throw(error_msg)
            return False

    def get_presigned_url(self):
        """Get a presigned URL for the file"""
        try:
            if not self.storage_doc.presigned_urls:
                return None

            # Check mimetype restrictions
            if (
                self.storage_doc.presigned_mimetypes_starting
                and self.file_doc.dfp_mime_type_guess_by_file_name
            ):
                presigned_mimetypes_starting = [
                    i.strip()
                    for i in self.storage_doc.presigned_mimetypes_starting.split("\n")
                    if i.strip()
                ]

                if not any(
                    self.file_doc.dfp_mime_type_guess_by_file_name.startswith(i)
                    for i in presigned_mimetypes_starting
                ):
                    return None

            # Get presigned URL
            return self.client.presigned_get_object(
                folder_id=self.storage_doc.google_folder_id,
                file_id=self.file_doc.dfp_external_storage_s3_key,
                expires=self.storage_doc.setting_presigned_url_expiration,
            )
        except Exception as e:
            frappe.log_error(f"Error generating Google Drive presigned URL: {str(e)}")
            return None


class S3FileProxy:
    """
    File-like object to provide chunked access to S3 objects without loading the entire file in memory.

    Args:
        readFn (callable): Function that accepts offset and size parameters and returns data
        object_size (int): The total size of the object in bytes
    """

    def __init__(self, readFn, object_size):
        self.readFn = readFn
        self.object_size = object_size
        self.offset = 0

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_value, traceback):
        pass

    def seek(self, offset, whence=0):
        """
        Change the current position in the file.

        Args:
            offset (int): The offset relative to the whence parameter
            whence (int): The reference position (SEEK_SET, SEEK_CUR, or SEEK_END)
        """
        if whence == io.SEEK_SET:
            self.offset = offset
        elif whence == io.SEEK_CUR:
            self.offset = self.offset + offset
        elif whence == io.SEEK_END:
            self.offset = self.object_size + offset

    def seekable(self):
        """
        Indicate that this object supports seek operations.

        Returns:
            bool: Always True for this implementation
        """
        return True

    def tell(self):
        """
        Return the current position in the file.

        Returns:
            int: Current file position
        """
        return self.offset

    def read(self, size=0):
        """
        Read up to size bytes from the object and return them.

        Args:
            size (int): Number of bytes to read. If 0, reads to end of file.

        Returns:
            bytes: The data read from the file
        """
        content = self.readFn(self.offset, size)
        self.offset = self.offset + len(content)
        return content


# Define handler classes outside the main function to avoid circular imports
# Create references to external handlers
def get_google_drive_handler(file_doc):
    """
    Get a Google Drive file handler for the given file document.

    Args:
        file_doc: File document instance

    Returns:
        object: Google Drive handler or None if not available
    """
    try:
        import importlib

        gdrive_module = importlib.import_module(
            "dfp_external_storage.gdrive_integration"
        )
        handler_class = getattr(
            gdrive_module, "DFPExternalStorageGoogleDriveFile", None
        )

        if handler_class:
            return handler_class(file_doc)
        return None
    except (ImportError, AttributeError):
        frappe.log_error("Google Drive integration not available")
        return None


def get_onedrive_handler(file_doc):
    """
    Get a OneDrive file handler for the given file document.

    Args:
        file_doc: File document instance

    Returns:
        object: OneDrive handler or None if not available
    """
    try:
        import importlib

        onedrive_module = importlib.import_module(
            "dfp_external_storage.onedrive_integration"
        )
        handler_class = getattr(onedrive_module, "DFPExternalStorageOneDriveFile", None)

        if handler_class:
            return handler_class(file_doc)
        return None
    except (ImportError, AttributeError):
        frappe.log_error("OneDrive integration not available")
        return None


def get_dropbox_handler(file_doc):
    """
    Get a Dropbox file handler for the given file document.

    Args:
        file_doc: File document instance

    Returns:
        object: Dropbox handler or None if not available
    """
    try:
        import importlib

        dropbox_module = importlib.import_module(
            "dfp_external_storage.dropbox_integration"
        )
        handler_class = getattr(dropbox_module, "DFPExternalStorageDropboxFile", None)

        if handler_class:
            return handler_class(file_doc)
        return None
    except (ImportError, AttributeError):
        frappe.log_error("Dropbox integration not available")
        return None


def handle_storage_type(file_doc):
    """
    Handle different storage types and return the appropriate handler

    Args:
        file_doc: DFPExternalStorageFile instance

    Returns:
        object: Storage handler instance
    """
    if not file_doc.dfp_external_storage_doc:
        return None

    storage_type = file_doc.dfp_external_storage_doc.type

    if storage_type == "Google Drive":
        return get_google_drive_handler(file_doc)
    elif storage_type == "OneDrive":
        return get_onedrive_handler(file_doc)
    elif storage_type == "Dropbox":
        return get_dropbox_handler(file_doc)

    return None  # Default S3 handlers will be used


class DFPExternalStorage(Document):
    """
    DocType for managing external storage connections for Frappe/ERPNext files.
    Supports S3, Google Drive, OneDrive, and Dropbox integrations.
    """

    def validate(self):
        """Validate document before save"""

        def has_changed(doc_a: Document, doc_b: Document, fields: list):
            for param in fields:
                value_a = getattr(doc_a, param)
                value_b = getattr(doc_b, param)
                if type(value_a) == list:
                    if not [i.name for i in value_a] == [i.name for i in value_b]:
                        return True
                elif value_a != value_b:
                    return True
            return False

        if self.stream_buffer_size < 8192:
            frappe.msgprint(_("Stream buffer size must be at least of 8192 bytes."))
            self.stream_buffer_size = 8192

        # Recheck S3 connection if needed
        previous = self.get_doc_before_save()
        if previous:
            if self.files_within and has_changed(
                self, previous, DFP_EXTERNAL_STORAGE_CRITICAL_FIELDS
            ):
                frappe.msgprint(
                    _(
                        "There are {} files using this bucket. The field you just updated is critical, be careful!"
                    ).format(self.files_within)
                )

        # Only validate S3/Minio connections here
        if (self.type in ["AWS S3", "S3 Compatible"]) and (
            not previous
            or has_changed(self, previous, DFP_EXTERNAL_STORAGE_CONNECTION_FIELDS)
        ):
            self.validate_bucket()

    def diagnose_storage_config(self):
        """
        Diagnostic method to check storage configuration

        Returns:
            list: List of configuration issues found
        """
        issues = []

        # Different validation depending on storage type
        if self.type in ["AWS S3", "S3 Compatible"]:
            if not self.endpoint:
                issues.append("Missing endpoint")
            if not self.bucket_name:
                issues.append("Missing bucket name")
            if not self.access_key:
                issues.append("Missing access key")
            if not self.secret_key:
                issues.append("Missing secret key")
        elif self.type == "Google Drive":
            if not self.google_client_id:
                issues.append("Missing Google client ID")
            if not self.google_client_secret:
                issues.append("Missing Google client secret")
            if not self.google_folder_id:
                issues.append("Missing Google folder ID")
        elif self.type == "OneDrive":
            if not self.onedrive_client_id:
                issues.append("Missing OneDrive client ID")
            if not self.onedrive_client_secret:
                issues.append("Missing OneDrive client secret")
            if not self.onedrive_folder_id:
                issues.append("Missing OneDrive folder ID")
        elif self.type == "Dropbox":
            if not self.dropbox_app_key:
                issues.append("Missing Dropbox app key")
            if not self.dropbox_app_secret:
                issues.append("Missing Dropbox app secret")
            if not self.dropbox_folder_path:
                issues.append("Missing Dropbox folder path")

        return issues

    def verify_connection(self):
        """
        Verify connection settings for the external storage

        Returns:
            bool: True if connection is successful, False otherwise
        """
        try:
            # First check configuration
            issues = self.diagnose_storage_config()
            if issues:
                frappe.msgprint(
                    _("Storage configuration issues found: {}").format(
                        ", ".join(issues)
                    ),
                    indicator="red",
                )
                return False

            # Then test connection based on storage type
            if self.type == "AWS S3":
                response = self.client.client.list_buckets()
                frappe.msgprint(
                    _("Successfully connected to AWS S3"), indicator="green"
                )
                return True
            elif self.type == "S3 Compatible":
                response = self.client.client.list_buckets()
                frappe.msgprint(
                    _("Successfully connected to S3 compatible storage"),
                    indicator="green",
                )
                return True
            elif self.type == "Google Drive":
                # Call Google Drive test method
                # This would be implemented in the gdrive_integration module
                from dfp_external_storage.gdrive_integration import test_connection

                result = test_connection(self)
                if result.get("success"):
                    frappe.msgprint(
                        _("Successfully connected to Google Drive"), indicator="green"
                    )
                    return True
                else:
                    frappe.msgprint(
                        _("Failed to connect to Google Drive: {}").format(
                            result.get("message")
                        ),
                        indicator="red",
                    )
                    return False
            elif self.type == "OneDrive":
                # Call OneDrive test method
                from dfp_external_storage.onedrive_integration import test_connection

                result = test_connection(self)
                if result.get("success"):
                    frappe.msgprint(
                        _("Successfully connected to OneDrive"), indicator="green"
                    )
                    return True
                else:
                    frappe.msgprint(
                        _("Failed to connect to OneDrive: {}").format(
                            result.get("message")
                        ),
                        indicator="red",
                    )
                    return False
            elif self.type == "Dropbox":
                # Call Dropbox test method
                from dfp_external_storage.dropbox_integration import test_connection

                result = test_connection(self)
                if result.get("success"):
                    frappe.msgprint(
                        _("Successfully connected to Dropbox"), indicator="green"
                    )
                    return True
                else:
                    frappe.msgprint(
                        _("Failed to connect to Dropbox: {}").format(
                            result.get("message")
                        ),
                        indicator="red",
                    )
                    return False
            else:
                frappe.msgprint(
                    _("Unsupported storage type: {}").format(self.type), indicator="red"
                )
                return False
        except Exception as e:
            frappe.log_error(f"Connection verification failed: {str(e)}")
            frappe.msgprint(
                _("Failed to verify connection: {}").format(str(e)), indicator="red"
            )
            return False

    def validate_bucket(self):
        """
        Enhanced bucket validation with configuration and connection checks

        Returns:
            bool: True if bucket is valid, False otherwise
        """
        # Skip for non-S3 storage types
        if self.type not in ["AWS S3", "S3 Compatible"]:
            return True

        # First verify configuration and connection
        if not self.verify_connection():
            return False

        # Then proceed with existing bucket validation
        if self.client:
            return self.client.validate_bucket(self.bucket_name)

        return False

    def on_trash(self):
        """Validate before deletion"""
        if self.files_within:
            frappe.throw(
                _("Can not be deleted. There are {} files using this bucket.").format(
                    self.files_within
                )
            )

    @cached_property
    def setting_stream_buffer_size(self):
        """Get configured stream buffer size, with fallback to minimum"""
        return self.stream_buffer_size if self.stream_buffer_size >= 8192 else 8192

    @cached_property
    def setting_cache_files_smaller_than(self):
        "Default: 5Mb"
        return (
            self.cache_files_smaller_than
            if self.cache_files_smaller_than >= 0
            else 5000000
        )

    @cached_property
    def setting_cache_expiration_secs(self):
        "Default: 1 day"
        return (
            self.cache_expiration_secs
            if self.cache_expiration_secs >= 0
            else 60 * 60 * 24
        )

    @cached_property
    def setting_presigned_url_expiration(self):
        "Default: 3 hours"
        return (
            self.presigned_url_expiration
            if self.presigned_url_expiration > 0
            else 60 * 60 * 3
        )

    @cached_property
    def files_within(self):
        """Count files using this storage"""
        return frappe.db.count("File", filters={"dfp_external_storage": self.name})

    # Adding by Manot L.
    @cached_property
    def cdn_url(self):
        """Get CloudFront URL if configured"""
        if (
            hasattr(self, "cloudfront_enabled")
            and self.cloudfront_enabled
            and hasattr(self, "cloudfront_domain")
            and self.cloudfront_domain
        ):
            return f"https://{self.cloudfront_domain.strip('/')}/"
        return None

    def get_cdn_url(self, object_key):
        """
        Generate CloudFront URL for an object

        Args:
            object_key (str): S3 object key

        Returns:
            str: CDN URL or None if not configured
        """
        if not self.cdn_url:
            return None
        return f"{self.cdn_url}{object_key}"

    @cached_property
    def client(self):
        """
        Initialize appropriate client based on storage type

        Returns:
            object: Storage client instance or None if initialization fails
        """
        # Return None for non-S3 storage types
        if self.type not in ["AWS S3", "S3 Compatible"]:
            return None

        try:
            if not all(
                [self.endpoint, self.access_key, self.region, self.secure is not None]
            ):
                missing_fields = []
                if not self.endpoint:
                    missing_fields.append("endpoint")
                if not self.access_key:
                    missing_fields.append("access_key")
                if not self.region:
                    missing_fields.append("region")
                error_msg = f"Missing required S3 configuration parameters: {', '.join(missing_fields)}"
                frappe.logger().error(error_msg)
                frappe.log_error(error_msg)
                return None

            # Get the secret key
            if self.is_new() and self.secret_key:
                key_secret = self.secret_key
            else:
                key_secret = get_decrypted_password(
                    "DFP External Storage", self.name, "secret_key"
                )
            if not key_secret:
                frappe.logger().error("Failed to get secret key")
                frappe.log_error("Failed to get secret key")
                return None

            # Create appropriate client based on storage type
            if self.type == "AWS S3":
                try:
                    import boto3

                    return AWSS3Connection(
                        access_key=self.access_key,
                        secret_key=key_secret,
                        region=self.region,
                    )
                except Exception as aws_error:
                    frappe.logger().error(
                        f"AWS S3 client initialization failed: {str(aws_error)}"
                    )
                    raise
            else:  # S3 Compatible
                try:
                    return MinioConnection(
                        endpoint=self.endpoint,
                        access_key=self.access_key,
                        secret_key=key_secret,
                        region=self.region,
                        secure=self.secure,
                    )
                except Exception as minio_error:
                    frappe.logger().error(
                        f"MinIO client initialization failed: {str(minio_error)}"
                    )
                    raise
        except Exception as e:
            frappe.logger().error(f"Failed to initialize S3 client: {str(e)}")
            frappe.log_error(f"Failed to initialize S3 client: {str(e)}")
            return None

    def remote_files_list(self):
        """
        List objects in the remote storage

        Returns:
            list: List of objects in the remote storage
        """
        # For S3 storage types, use the client
        if self.type in ["AWS S3", "S3 Compatible"] and self.client:
            return self.client.list_objects(self.bucket_name, recursive=True)

        # For other storage types, implement in their respective modules
        elif self.type == "Google Drive":
            try:
                from dfp_external_storage.gdrive_integration import list_files

                return list_files(self)
            except ImportError:
                frappe.log_error("Google Drive integration not available")
                return []

        elif self.type == "OneDrive":
            try:
                from dfp_external_storage.onedrive_integration import list_files

                return list_files(self)
            except ImportError:
                frappe.log_error("OneDrive integration not available")
                return []

        elif self.type == "Dropbox":
            try:
                from dfp_external_storage.dropbox_integration import list_files

                return list_files(self)
            except ImportError:
                frappe.log_error("Dropbox integration not available")
                return []

        return []


class AWSS3Connection:
    """AWS S3 connection handler"""

    def __init__(self, access_key: str, secret_key: str, region: str):
        """
        Initialize AWS S3 connection

        Args:
            access_key (str): AWS access key ID
            secret_key (str): AWS secret access key
            region (str): AWS region name
        """
        import boto3

        self.client = boto3.client(
            "s3",
            aws_access_key_id=access_key,
            aws_secret_access_key=secret_key,
            region_name=region,
        )

    def validate_bucket(self, bucket_name: str):
        """
        Validate if bucket exists and is accessible

        Args:
            bucket_name (str): Name of the bucket to validate

        Returns:
            bool: True if bucket exists and is accessible

        Raises:
            frappe.Exception: If bucket validation fails
        """
        try:
            self.client.head_bucket(Bucket=bucket_name)
            frappe.msgprint(
                _("Great! Bucket is accessible ;)"), indicator="green", alert=True
            )
            return True
        except Exception as e:
            frappe.throw(_("Error when looking for bucket: {}".format(str(e))))
            return False

    def remove_object(self, bucket_name: str, object_name: str):
        """
        Remove object from bucket

        Args:
            bucket_name (str): Name of the bucket
            object_name (str): Name of the object to remove

        Returns:
            object: Response from AWS S3 API
        """
        return self.client.delete_object(Bucket=bucket_name, Key=object_name)

    def stat_object(self, bucket_name: str, object_name: str):
        """
        Get object metadata

        Args:
            bucket_name (str): Name of the bucket
            object_name (str): Name of the object

        Returns:
            object: Object metadata
        """
        return self.client.head_object(Bucket=bucket_name, Key=object_name)

    def get_object(
        self, bucket_name: str, object_name: str, offset: int = 0, length: int = 0
    ):
        """
        Get object content

        Args:
            bucket_name (str): Name of the bucket
            object_name (str): Name of the object
            offset (int): Start byte position
            length (int): Number of bytes to retrieve

        Returns:
            object: Object content
        """
        range_header = f"bytes={offset}-{offset+length-1}" if length else None
        kwargs = {"Bucket": bucket_name, "Key": object_name}
        if range_header:
            kwargs["Range"] = range_header
        return self.client.get_object(**kwargs)["Body"]

    def fget_object(self, bucket_name: str, object_name: str, file_path: str):
        """
        Download object to file

        Args:
            bucket_name (str): Name of the bucket
            object_name (str): Name of the object
            file_path (str): Path to save the file

        Returns:
            object: Response from AWS S3 API
        """
        return self.client.download_file(bucket_name, object_name, file_path)

    def put_object(
        self,
        bucket_name: str,
        object_name: str,
        data,
        metadata: dict = None,
        length: int = -1,
    ):
        """
        Upload object to bucket

        Args:
            bucket_name (str): Name of the bucket
            object_name (str): Name of the object
            data: File-like object or bytes
            metadata (dict): Object metadata
            length (int): Content length

        Returns:
            object: Response from AWS S3 API
        """
        return self.client.upload_fileobj(data, bucket_name, object_name)

    def list_objects(self, bucket_name: str, recursive: bool = True):
        """
        List objects in bucket

        Args:
            bucket_name (str): Name of the bucket
            recursive (bool): List recursively

        Returns:
            list: List of objects in bucket
        """
        paginator = self.client.get_paginator("list_objects_v2")
        for page in paginator.paginate(Bucket=bucket_name):
            for obj in page.get("Contents", []):
                yield obj


class MinioConnection:
    """MinIO/S3 compatible connection handler"""

    def __init__(
        self, endpoint: str, access_key: str, secret_key: str, region: str, secure: bool
    ):
        """
        Initialize MinIO connection

        Args:
            endpoint (str): MinIO endpoint
            access_key (str): Access key
            secret_key (str): Secret key
            region (str): Region name
            secure (bool): Use secure connection
        """
        self.client = Minio(
            endpoint=endpoint,
            access_key=access_key,
            secret_key=secret_key,
            region=region,
            secure=secure,
        )

    def validate_bucket(self, bucket_name: str):
        """
        Validate if bucket exists and is accessible

        Args:
            bucket_name (str): Name of the bucket to validate

        Returns:
            bool: True if bucket exists and is accessible

        Raises:
            frappe.Exception: If bucket validation fails
        """

        try:
            if self.client.bucket_exists(bucket_name):
                frappe.msgprint(
                    _("Great! Bucket is accesible ;)"), indicator="green", alert=True
                )
                return True
            else:
                frappe.throw(_("Bucket not found"))
        except Exception as e:
            if hasattr(e, "message"):
                frappe.throw(_("Error when looking for bucket: {}".format(e.message)))
            elif hasattr(e, "reason"):
                frappe.throw(str(e))
        return False

    def remove_object(self, bucket_name: str, object_name: str):
        """
        Minio params:
        :param bucket_name: Name of the bucket.
        :param object_name: Object name in the bucket.
        :param version_id: Version ID of the object.

        Remove object from bucket

        Args:
            bucket_name (str): Name of the bucket
            object_name (str): Name of the object to remove

        Returns:
            object: Response from MinIO API
        """
        return self.client.remove_object(
            bucket_name=bucket_name, object_name=object_name
        )

    def stat_object(self, bucket_name: str, object_name: str):
        """
        Minio params:
        :param bucket_name: Name of the bucket.
        :param object_name: Object name in the bucket.
        :param version_id: Version ID of the object.

        Get object metadata

        Args:
            bucket_name (str): Name of the bucket
            object_name (str): Name of the object

        Returns:
            object: Object metadata
        """
        return self.client.stat_object(bucket_name=bucket_name, object_name=object_name)

    def get_object(
        self, bucket_name: str, object_name: str, offset: int = 0, length: int = 0
    ):
        """
        Minio params:
        :param bucket_name: Name of the bucket.
        :param object_name: Object name in the bucket.
        :param offset: Start byte position of object data.
        :param length: Number of bytes of object data from offset.
        :param request_headers: Any additional headers to be added with GET request.
        :param ssec: Server-side encryption customer key.
        :param version_id: Version-ID of the object.
        :param extra_query_params: Extra query parameters for advanced usage.
        :return: :class:`urllib3.response.HTTPResponse` object.

        Get object content

        Args:
            bucket_name (str): Name of the bucket
            object_name (str): Name of the object
            offset (int): Start byte position
            length (int): Number of bytes to retrieve

        Returns:
            object: Object content
        """
        return self.client.get_object(
            bucket_name=bucket_name,
            object_name=object_name,
            offset=offset,
            length=length,
        )

    def fget_object(self, bucket_name: str, object_name: str, file_path: str):
        """
        Minio params:
        :param bucket_name: Name of the bucket.
        :param object_name: Object name in the bucket.
        :param file_path: Name of file to download
        :param request_headers: Any additional headers to be added with GET request.
        :param ssec: Server-side encryption customer key.
        :param version_id: Version-ID of the object.
        :param extra_query_params: Extra query parameters for advanced usage.
        :param temp_file_path: Path to a temporary file
        :return: :class:`urllib3.response.HTTPResponse` object.

        Download object to file

        Args:
            bucket_name (str): Name of the bucket
            object_name (str): Name of the object
            file_path (str): Path to save the file

        Returns:
            object: Response from MinIO API
        """
        return self.client.fget_object(
            bucket_name=bucket_name, object_name=object_name, file_path=file_path
        )

    def presigned_get_object(
        self, bucket_name: str, object_name: str, expires: int = timedelta(hours=3)
    ):
        """
        Minio params:
        Get presigned URL of an object to download its data with expiry time
        and custom request parameters.

        :param bucket_name: Name of the bucket.
        :param object_name: Object name in the bucket.
        :param expires: Expiry in seconds; defaults to 7 days.
        :param response_headers: Optional response_headers argument to
                                                        specify response fields like date, size,
                                                        type of file, data about server, etc.
        :param request_date: Optional request_date argument to
                                                specify a different request date. Default is
                                                current date.
        :param version_id: Version ID of the object.
        :param extra_query_params: Extra query parameters for advanced usage.
        :return: URL string.

        Example::
                # Get presigned URL string to download 'my-object' in
                # 'my-bucket' with default expiry (i.e. 7 days).
                url = client.presigned_get_object("my-bucket", "my-object")
                print(url)

                # Get presigned URL string to download 'my-object' in
                # 'my-bucket' with two hours expiry.
                url = client.presigned_get_object("my-bucket", "my-object", expires=timedelta(hours=2))
                print(url)

        Get presigned URL for object

        Args:
            bucket_name (str): Name of the bucket
            object_name (str): Name of the object
            expires (int or timedelta): Expiry time

        Returns:
            str: Presigned URL
        """
        if type(expires) == int:
            expires = timedelta(seconds=expires)
        return self.client.presigned_get_object(
            bucket_name=bucket_name, object_name=object_name, expires=expires
        )

    def put_object(self, bucket_name, object_name, data, metadata=None, length=-1):
        """
        Minio params:
        :param bucket_name: Name of the bucket.
        :param object_name: Object name in the bucket.
        :param data: An object having callable read() returning bytes object.
        :param length: Data size; -1 for unknown size and set valid part_size.
        :param content_type: Content type of the object.
        :param metadata: Any additional metadata to be uploaded along
                with your PUT request.
        :param sse: Server-side encryption.
        :param progress: A progress object;
        :param part_size: Multipart part size.
        :param num_parallel_uploads: Number of parallel uploads.
        :param tags: :class:`Tags` for the object.
        :param retention: :class:`Retention` configuration object.
        :param legal_hold: Flag to set legal hold for the object.

        Upload object to bucket

        Args:
            bucket_name (str): Name of the bucket
            object_name (str): Name of the object
            data: File-like object or bytes
            metadata (dict): Object metadata
            length (int): Content length

        Returns:
            object: Response from MinIO API
        """
        return self.client.put_object(
            bucket_name=bucket_name,
            object_name=object_name,
            data=data,
            metadata=metadata,
            length=length,
        )

    def list_objects(self, bucket_name: str, recursive=True):
        """
        Minio params:
        :param bucket_name: Name of the bucket.
        # :param prefix: Object name starts with prefix.
        # :param recursive: List recursively than directory structure emulation.
        # :param start_after: List objects after this key name.
        # :param include_user_meta: MinIO specific flag to control to include
        # 						user metadata.
        # :param include_version: Flag to control whether include object
        # 						versions.
        # :param use_api_v1: Flag to control to use ListObjectV1 S3 API or not.
        # :param use_url_encoding_type: Flag to control whether URL encoding type
        # 							to be used or not.
        :return: Iterator of :class:`Object <Object>`.

        List objects in bucket

        Args:
            bucket_name (str): Name of the bucket
            recursive (bool): List recursively

        Returns:
            list: List of objects in bucket
        """
        return self.client.list_objects(bucket_name=bucket_name, recursive=recursive)


class DFPExternalStorageFile(File):
    """Enhanced File class with external storage support"""

    def __init__(self, *args, **kwargs):
        """Initialize file with extended functionality"""
        try:
            super(DFPExternalStorageFile, self).__init__(*args, **kwargs)
            frappe.logger().debug(
                f"DFPExternalStorageFile initialized for file: {self.name if hasattr(self, 'name') else 'New File'}"
            )
        except Exception as e:
            frappe.logger().error(
                f"Error initializing DFPExternalStorageFile: {str(e)}"
            )
            raise

    def validate(self):
        """Validate storage configuration before save"""
        try:
            # Log validation attempt
            frappe.logger().debug(
                f"Validating storage configuration for file: {self.name}"
            )

            # Check if external storage is set
            if self.dfp_external_storage:
                frappe.logger().debug(
                    f"External storage set to: {self.dfp_external_storage}"
                )

                # Check if storage doc exists
                if not self.dfp_external_storage_doc:
                    error_msg = "External storage configuration not found. Please verify the storage connection exists."
                    frappe.logger().error(f"Validation failed: {error_msg}")
                    frappe.throw(error_msg)

                # Handle different storage types
                storage_type = self.dfp_external_storage_doc.type

                # Specific validation for S3 storage types
                if storage_type in ["AWS S3", "S3 Compatible"]:
                    # Check if client is initialized
                    if not self.dfp_external_storage_client:
                        # Get diagnostic info
                        storage_doc = self.dfp_external_storage_doc
                        issues = []
                        if not storage_doc.endpoint:
                            issues.append("endpoint")
                        if not storage_doc.access_key:
                            issues.append("access key")
                        if not storage_doc.region:
                            issues.append("region")
                        if not storage_doc.bucket_name:
                            issues.append("bucket name")

                        if issues:
                            error_msg = (
                                f"Storage configuration is missing: {', '.join(issues)}"
                            )
                            frappe.logger().error(f"Validation failed: {error_msg}")
                            frappe.throw(error_msg)
                        else:
                            error_msg = "Failed to initialize storage client. Please check error logs for details."
                            frappe.logger().error(f"Validation failed: {error_msg}")
                            frappe.throw(error_msg)

                # For non-S3 storage types, perform specific validations
                elif storage_type == "Google Drive":
                    # Validate Google Drive configuration
                    if not self.dfp_external_storage_doc.google_client_id:
                        frappe.throw("Google Drive client ID is required")
                    if not self.dfp_external_storage_doc.google_refresh_token:
                        frappe.throw("Google Drive authentication is not complete")
                elif storage_type == "OneDrive":
                    # Validate OneDrive configuration
                    if not self.dfp_external_storage_doc.onedrive_client_id:
                        frappe.throw("OneDrive client ID is required")
                    if not self.dfp_external_storage_doc.onedrive_refresh_token:
                        frappe.throw("OneDrive authentication is not complete")
                elif storage_type == "Dropbox":
                    # Validate Dropbox configuration
                    if not self.dfp_external_storage_doc.dropbox_app_key:
                        frappe.throw("Dropbox app key is required")
                    if not self.dfp_external_storage_doc.dropbox_refresh_token:
                        frappe.throw("Dropbox authentication is not complete")

                frappe.logger().debug(f"Storage validation successful for {self.name}")

        except Exception as e:
            frappe.logger().error(
                f"Unexpected error during storage validation: {str(e)}"
            )
            raise

    def is_image(self):
        """
        Check if file is an image

        Returns:
            bool: True if file is an image, False otherwise
        """
        mime_type = self.dfp_mime_type_guess_by_file_name
        return mime_type and mime_type.startswith("image/")

    def get_image_tag(self, alt_text=""):
        """
        Get HTML image tag for the file

        Args:
            alt_text (str): Alternative text for the image

        Returns:
            str: HTML image tag
        """
        if not self.is_image():
            return ""

        url = (
            self.get_public_url() if hasattr(self, "get_public_url") else self.file_url
        )
        return f'<img src="{url}" alt="{alt_text or self.file_name}">'

    @property
    def is_remote_file(self):
        """
        Check if file is stored remotely

        Returns:
            bool: True if file is remote, False otherwise
        """
        return (
            True
            if self.dfp_external_storage_s3_key
            else super(DFPExternalStorageFile, self).is_remote_file
        )

    @cached_property
    def dfp_external_storage_doc(self):
        """
        Get external storage document for this file

        Returns:
            Document: External storage document or None
        """
        dfp_ext_strg_doc = None
        # 1. Use defined
        if self.dfp_external_storage:
            try:
                dfp_ext_strg_doc = frappe.get_doc(
                    "DFP External Storage", self.dfp_external_storage
                )
            except:
                pass
        if not dfp_ext_strg_doc:
            # 2. Specific folder connection
            dfp_ext_strg_name = frappe.db.get_value(
                "DFP External Storage by Folder",
                fieldname="parent",
                filters={"folder": self.folder},
            )
            # 3. Default connection (Home folder)
            if not dfp_ext_strg_name:
                dfp_ext_strg_name = frappe.db.get_value(
                    "DFP External Storage by Folder",
                    fieldname="parent",
                    filters={"folder": "Home"},
                )
            if dfp_ext_strg_name:
                dfp_ext_strg_doc = frappe.get_doc(
                    "DFP External Storage", dfp_ext_strg_name
                )
        return dfp_ext_strg_doc

    def dfp_is_s3_remote_file(self):
        """
        Check if file is stored in S3

        Returns:
            bool: True if file is in S3, False otherwise
        """
        if self.dfp_external_storage_s3_key and self.dfp_external_storage_doc:
            return True
        return False

    def dfp_is_cacheable(self):
        """
        Check if file is cacheable

        Returns:
            bool: True if file is cacheable, False otherwise
        """
        try:
            return (
                not self.is_private
                and self.dfp_external_storage_doc
                and self.dfp_external_storage_doc.setting_cache_files_smaller_than
                and self.dfp_file_size != 0
                and self.dfp_file_size
                < self.dfp_external_storage_doc.setting_cache_files_smaller_than
            )
        except Exception:
            return False

    @cached_property
    def dfp_file_size(self) -> int:
        """
        Get file size, possibly from remote storage

        Returns:
            int: File size in bytes
        """
        if (
            self.dfp_is_s3_remote_file()
            and self.dfp_external_storage_doc.remote_size_enabled
        ):
            try:
                # For S3 storage
                if self.dfp_external_storage_doc.type in ["AWS S3", "S3 Compatible"]:
                    object_info = self.dfp_external_storage_doc.client.stat_object(
                        bucket_name=self.dfp_external_storage_doc.bucket_name,
                        object_name=self.dfp_external_storage_s3_key,
                    )
                    return object_info.size
                # For other storage types
                else:
                    # Use storage handler to get file size
                    storage_handler = handle_storage_type(self)
                    if storage_handler and hasattr(storage_handler, "get_file_size"):
                        return storage_handler.get_file_size()

            except Exception as e:
                frappe.log_error(
                    f"Error getting remote file size: {self.dfp_external_storage_s3_key} - {str(e)}",
                    title="Remote File Size Error",
                )
        return self.file_size

    @cached_property
    def dfp_external_storage_client(self):
        """
        Get external storage client

        Returns:
            object: External storage client or None
        """
        if self.dfp_external_storage_doc:
            return self.dfp_external_storage_doc.client
        return None

    def dfp_external_storage_ignored_doctypes(self):
        """
        Check if file is attached to an ignored doctype

        Returns:
            bool: True if doctype is ignored, False otherwise
        """
        if (
            self.attached_to_doctype
            and self.dfp_external_storage_doc
            and hasattr(self.dfp_external_storage_doc, "doctypes_ignored")
            and self.attached_to_doctype
            in [
                i.doctype_to_ignore
                for i in self.dfp_external_storage_doc.doctypes_ignored
            ]
        ):
            frappe.msgprint(
                _(
                    """This doctype does not allow remote files attached to it. Check "DFP External Storage" advanced settings for more details."""
                )
            )
            return True
        return False

    def dfp_external_storage_upload_file(self, local_file=None):
        """
        Upload file to external storage

        Args:
            local_file (str): Path to local file

        Returns:
            bool: True if upload successful, False otherwise
        """
        try:
            # Log upload attempt
            frappe.logger().debug(
                f"Attempting to upload file to S3: {self.name}, Local file: {local_file}"
            )

            # Check for ignored doctypes
            if self.dfp_external_storage_ignored_doctypes():
                frappe.logger().info(
                    f"Doctype ignored for external storage upload: {self.attached_to_doctype}"
                )
                self.dfp_external_storage = ""
                return False

            # Get storage handler for the specific storage type
            storage_handler = handle_storage_type(self)
            if storage_handler:
                return storage_handler.upload_file(local_file)

            # Basic validations for S3 storage
            if (
                not self.dfp_external_storage_doc
                or not self.dfp_external_storage_doc.enabled
            ):
                frappe.msgprint("External storage is not configured or enabled")
                frappe.logger().warning("External storage is not configured or enabled")
                return False

            # Validate client exists
            if not self.dfp_external_storage_client:
                frappe.msgprint(
                    "Failed to initialize storage client. Please check your storage configuration."
                )
                frappe.logger().error(
                    "Failed to initialize storage client. Please check your storage configuration."
                )
                return False

            if self.is_folder:
                frappe.logger().debug(f"Cannot upload folder to S3: {self.name}")
                return False

            if self.dfp_external_storage_s3_key:
                # File already on storage
                frappe.logger().debug(
                    f"File already on storage with key {self.dfp_external_storage_s3_key}"
                )
                return False

            if self.file_url and self.file_url.startswith(URL_PREFIXES):
                frappe.logger().error(
                    f"Cannot upload URL file to storage: {self.file_url}"
                )
                raise NotImplementedError(
                    "http(s)://file(s) not ready to be saved to local or external storage(s)."
                )

            # Add content type detection
            content_type, _ = mimetypes.guess_type(self.file_name)
            if not content_type:
                content_type = "application/octet-stream"  # Default content type
            frappe.logger().debug(f"Detected content type: {content_type}")

            # Store original file_url for rollback if needed
            original_file_url = self.file_url

            # Define S3 key with proper naming
            base, extension = os.path.splitext(self.file_name)
            key = f"{frappe.local.site}/{base}-{self.name}{extension}"
            frappe.logger().debug(f"Generated S3 key: {key}")

            # Determine file path
            is_public = "/public" if not self.is_private else ""
            if not local_file:
                local_file = "./" + frappe.local.site + is_public + self.file_url
            frappe.logger().debug(f"Local file path: {local_file}")

            # Validate file existence
            if not os.path.exists(local_file):
                error_msg = f"Local file not found: {local_file}"
                frappe.logger().error(error_msg)
                frappe.throw(_(error_msg))

            # Upload to S3
            try:
                with open(local_file, "rb") as f:
                    file_size = os.path.getsize(local_file)

                    self.dfp_external_storage_client.put_object(
                        bucket_name=self.dfp_external_storage_doc.bucket_name,
                        object_name=key,
                        data=f,
                        length=file_size,
                        metadata={
                            "Content-Type": content_type,
                            "Original-Filename": self.file_name,
                        },
                    )

                # Update file document
                self.dfp_external_storage_s3_key = key
                self.dfp_external_storage = self.dfp_external_storage_doc.name
                self.file_url = f"/{DFP_EXTERNAL_STORAGE_URL_SEGMENT_FOR_FILE_LOAD}/{self.name}/{self.file_name}"
                frappe.logger().debug(
                    f"S3 upload successful. Updated file_url: {self.file_url}"
                )

                # Remove local file after successful upload
                os.remove(local_file)
                frappe.logger().debug(f"Removed local file: {local_file}")
                return True

            except Exception as upload_error:
                error_msg = _("Error saving file in remote folder: {}").format(
                    str(upload_error)
                )
                frappe.logger().error(f"{error_msg}: {self.file_name}", exc_info=True)

                # Handle new file upload failure
                if not self.get_doc_before_save():
                    error_extra = _("File saved in local filesystem.")
                    frappe.log_error(f"{error_msg} {error_extra}: {self.file_name}")
                    # Reset S3 related fields
                    self.dfp_external_storage_s3_key = ""
                    self.dfp_external_storage = ""
                    self.file_url = original_file_url
                    frappe.msgprint(
                        "File saved in local filesystem due to upload error"
                    )
                else:
                    # If modifying existing file, throw error
                    frappe.throw(error_msg)
                    frappe.throw(str(upload_error))
                return False

        except Exception as e:
            frappe.logger().error(
                f"Unexpected error during S3 upload: {str(e)}", exc_info=True
            )
            frappe.msgprint(f"Failed to upload file to S3: {str(e)}")
            frappe.throw(_("Failed to upload file to S3: {}").format(str(e)))
            return False

    def dfp_external_storage_delete_file(self):
        """
        Delete file from external storage

        Returns:
            bool: True if delete successful, False otherwise
        """
        if not self.dfp_is_s3_remote_file():
            return False

        # Get storage handler for the specific storage type
        storage_handler = handle_storage_type(self)
        if storage_handler:
            return storage_handler.delete_file()

        # Do not delete if other file docs are using same storage key
        files_using_s3_key = frappe.get_all(
            "File",
            filters={
                "dfp_external_storage_s3_key": self.dfp_external_storage_s3_key,
                "dfp_external_storage": self.dfp_external_storage,
                "name": ["!=", self.name],  # Exclude current file
            },
        )
        if len(files_using_s3_key):
            return False

        error_msg = _("Error deleting file in remote folder.")
        # Only delete if connection is enabled
        if (
            not self.dfp_external_storage_doc
            or not self.dfp_external_storage_doc.enabled
        ):
            error_extra = _("Write disabled for connection <strong>{}</strong>").format(
                self.dfp_external_storage_doc.title
            )
            frappe.throw(f"{error_msg} {error_extra}")

        try:
            self.dfp_external_storage_client.remove_object(
                bucket_name=self.dfp_external_storage_doc.bucket_name,
                object_name=self.dfp_external_storage_s3_key,
            )
            return True
        except Exception as e:
            frappe.log_error(f"{error_msg}: {self.file_name}", message=str(e))
            frappe.throw(f"{error_msg} {str(e)}")
            return False

    def dfp_external_storage_download_to_file(self, local_file):
        """
        Stream file from storage directly to local_file

        Args:
            local_file (str): Path to save the file

        Returns:
            bool: True if download successful, False otherwise
        """
        if not self.dfp_is_s3_remote_file():
            return False

        # Get storage handler for the specific storage type
        storage_handler = handle_storage_type(self)
        if storage_handler and hasattr(storage_handler, "download_to_file"):
            return storage_handler.download_to_file(local_file)

        try:
            key = self.dfp_external_storage_s3_key

            self.dfp_external_storage_client.fget_object(
                bucket_name=self.dfp_external_storage_doc.bucket_name,
                object_name=key,
                file_path=local_file,
            )
            return True
        except Exception as e:
            error_msg = _(
                "Error downloading to file from remote folder. Check Error Log for more information."
            )
            frappe.log_error(title=f"{error_msg}: {self.file_name}", message=str(e))
            frappe.throw(error_msg)
            return False

    def dfp_external_storage_file_proxy(self):
        """
        Get a file-like object for reading from storage

        Returns:
            object: File-like object
        """
        if not self.dfp_is_s3_remote_file():
            frappe.log_error(f"Invalid S3 file configuration for {self.name}")
            return None

        # Get storage handler for the specific storage type
        storage_type = self.dfp_external_storage_doc.type
        if storage_type not in ["AWS S3", "S3 Compatible"]:
            storage_handler = handle_storage_type(self)
            if storage_handler and hasattr(storage_handler, "get_file_proxy"):
                return storage_handler.get_file_proxy()
            else:
                frappe.log_error(f"File proxy not supported for {storage_type}")
                return None

        def read_chunks(offset=0, size=0):
            """Read chunks of data from storage"""
            try:
                with self.dfp_external_storage_client.get_object(
                    bucket_name=self.dfp_external_storage_doc.bucket_name,
                    object_name=self.dfp_external_storage_s3_key,
                    offset=offset,
                    length=size,
                ) as response:
                    content = response.read()
                return content
            except Exception as e:
                frappe.log_error(f"Chunk read error: {str(e)}")
                raise

        return S3FileProxy(readFn=read_chunks, object_size=self.dfp_file_size)

    def dfp_external_storage_download_file(self) -> bytes:
        """
        Download file content from storage

        Returns:
            bytes: File content
        """
        content = b""
        if not self.dfp_is_s3_remote_file():
            return content

        # Get storage handler for the specific storage type
        storage_handler = handle_storage_type(self)
        if storage_handler and hasattr(storage_handler, "download_file"):
            return storage_handler.download_file()

        try:
            with self.dfp_external_storage_client.get_object(
                bucket_name=self.dfp_external_storage_doc.bucket_name,
                object_name=self.dfp_external_storage_s3_key,
            ) as response:
                content = response.read()
            return content
        except Exception as e:
            error_msg = _("Error downloading file from remote folder")
            frappe.log_error(title=f"{error_msg}: {self.file_name}", message=str(e))
            frappe.throw(error_msg)
        return content

    def dfp_external_storage_stream_file(self) -> t.Iterable[bytes]:
        """
        Stream file from storage

        Returns:
            iterator: File content iterator
        """
        # Get storage handler for the specific storage type
        storage_handler = handle_storage_type(self)
        if storage_handler and hasattr(storage_handler, "stream_file"):
            return storage_handler.stream_file()

        try:
            if not self.dfp_external_storage_doc:
                frappe.throw(_("Storage configuration not found"))
            return wrap_file(
                environ=frappe.local.request.environ,
                file=self.dfp_external_storage_file_proxy(),
                buffer_size=self.dfp_external_storage_doc.setting_stream_buffer_size,
            )
        except Exception as e:
            frappe.log_error(f"File streaming error: {str(e)}")
            frappe.throw(_("Failed to stream file"))

    def download_to_local_and_remove_remote(self):
        """
        Download file from remote storage and remove the remote file

        Returns:
            bool: True if successful, False otherwise
        """
        # Get storage handler for the specific storage type
        storage_handler = handle_storage_type(self)
        if storage_handler and hasattr(
            storage_handler, "download_to_local_and_remove_remote"
        ):
            return storage_handler.download_to_local_and_remove_remote()

        try:
            bucket = self.dfp_external_storage_doc.bucket_name
            key = self.dfp_external_storage_s3_key

            self.dfp_external_storage_s3_key = ""
            self.dfp_external_storage = ""

            with self.dfp_external_storage_client.get_object(
                bucket_name=bucket, object_name=key
            ) as response:
                self._content = response.read()
            self.save_file_on_filesystem()

            self.dfp_external_storage_client.remove_object(
                bucket_name=bucket, object_name=key
            )
            return True
        except Exception as e:
            error_msg = _("Error downloading and removing file from remote folder.")
            frappe.log_error(title=f"{error_msg}: {self.file_name}", message=str(e))
            frappe.throw(error_msg)
            return False

    def validate_file_on_disk(self):
        """
        Check if file exists on disk

        Returns:
            bool: True if validation passes
        """
        return (
            True
            if self.dfp_is_s3_remote_file()
            else super(DFPExternalStorageFile, self).validate_file_on_disk()
        )

    def exists_on_disk(self):
        """
        Check if file exists on disk

        Returns:
            bool: True if file exists on disk
        """
        return (
            False
            if self.dfp_is_s3_remote_file()
            else super(DFPExternalStorageFile, self).exists_on_disk()
        )

    @frappe.whitelist()
    def optimize_file(self):
        """
        Optimize image file (compress, resize)

        Raises:
            NotImplementedError: If file is remote
        """
        if self.dfp_is_s3_remote_file():
            raise NotImplementedError("Only local image files can be optimized")
        super(DFPExternalStorageFile, self).optimize_file()

    def _remote_file_local_path_get(self):
        """
        Get local path for remote file

        Returns:
            str: Local path

        Raises:
            frappe.ValidationError: If path parameters are invalid
        """
        if not self.name or not self.file_name:
            frappe.throw(_("Invalid file path parameters"))
        return f"/{DFP_EXTERNAL_STORAGE_URL_SEGMENT_FOR_FILE_LOAD}/{self.name}/{self.file_name}"

    def dfp_file_url_is_s3_location_check_if_s3_data_is_not_defined(self):
        """
        Set S3 key if file_url exists and can be rendered

        This is useful when a file is copied (e.g., when amending a sales invoice)
        """
        if not self.file_url or self.is_remote_file or self.dfp_external_storage_s3_key:
            return
        try:
            dfp_es_file_renderer = DFPExternalStorageFileRenderer(path=self.file_url)
            if not dfp_es_file_renderer.can_render():
                return
            s3_data = frappe.get_value(
                "File", dfp_es_file_renderer.file_id_get(), fieldname="*"
            )
            if s3_data:
                self.dfp_external_storage = s3_data["dfp_external_storage"]
                self.dfp_external_storage_s3_key = s3_data[
                    "dfp_external_storage_s3_key"
                ]
                self.content_hash = s3_data["content_hash"]
                self.file_size = s3_data["file_size"]
                # It is "duplicated" within Frappe but not in S3 😏
                self.flags.ignore_duplicate_entry_error = True
        except Exception as e:
            frappe.log_error(f"Error checking S3 location: {str(e)}")

    def get_content(self) -> bytes:
        """
        Get file content

        Returns:
            bytes: File content

        Raises:
            frappe.PageDoesNotExistError: If file is not downloadable
        """
        self.dfp_file_url_is_s3_location_check_if_s3_data_is_not_defined()
        if not self.dfp_is_s3_remote_file():
            return super(DFPExternalStorageFile, self).get_content()
        try:
            if not self.is_downloadable():
                raise Exception("File not available")
            return self.dfp_external_storage_download_file()
        except Exception as e:
            # If no document, no read permissions, etc. For security reasons do not give any information
            frappe.log_error(f"Error getting file content: {str(e)}")
            raise frappe.PageDoesNotExistError()

    @cached_property
    def dfp_mime_type_guess_by_file_name(self):
        """
        Guess MIME type from file name

        Returns:
            str: MIME type or None
        """
        content_type, _ = mimetypes.guess_type(self.file_name)
        if content_type:
            return content_type
        return None

    def dfp_presigned_url_get(self):
        """
        Get presigned URL for the file

        Returns:
            str: Presigned URL or None
        """
        if (
            not self.dfp_is_s3_remote_file()
            or not self.dfp_external_storage_doc.presigned_urls
        ):
            return None

        # Get storage handler for the specific storage type
        storage_handler = handle_storage_type(self)
        if storage_handler and hasattr(storage_handler, "get_presigned_url"):
            return storage_handler.get_presigned_url()

        # For S3 Storage types
        if (
            self.dfp_external_storage_doc.presigned_mimetypes_starting
            and self.dfp_mime_type_guess_by_file_name
        ):
            # Get list exploding by new line, removing empty lines and cleaning starting and ending spaces
            presigned_mimetypes_starting = [
                i.strip()
                for i in self.dfp_external_storage_doc.presigned_mimetypes_starting.split(
                    "\n"
                )
                if i.strip()
            ]
            if not any(
                self.dfp_mime_type_guess_by_file_name.startswith(i)
                for i in presigned_mimetypes_starting
            ):
                return None
        return self.dfp_external_storage_client.presigned_get_object(
            bucket_name=self.dfp_external_storage_doc.bucket_name,
            object_name=self.dfp_external_storage_s3_key,
            expires=self.dfp_external_storage_doc.setting_presigned_url_expiration,
        )


def hook_file_before_save(doc, method):
    """
    This method is called before the document is saved to DB

    Args:
        doc: File document
        method: Method name
    """
    try:
        previous = doc.get_doc_before_save()
        print("previous", previous)

        # Check if the document is a DFPExternalStorageFile instance
        if not hasattr(doc, "dfp_external_storage_upload_file"):
            try:
                # Convert the normal File to DFPExternalStorageFile
                from frappe.core.doctype.file.file import file
                from dfp_external_storage.dfp_external_storage.doctype.dfp_external_storage.dfp_external_storage import (
                    DFPExternalStorageFile,
                )

                # Create a new DFPExternalStorageFile with the same name
                dfp_file = DFPExternalStorageFile(doc.name)

                # Copy all attributes from the original doc to the new one
                for key, value in doc.__dict__.items():
                    if key != "commands" and key != "_meta" and key != "_table_fields":
                        setattr(dfp_file, key, value)

                # Now process the DFPExternalStorageFile instead
                doc = dfp_file
            except Exception as e:
                frappe.log_error(
                    f"Failed to convert File to DFPExternalStorageFile: {str(e)}"
                )
                return  # Exit early if conversion fails

        if not previous:
            # NEW "File": Case 1: remote selected => upload to remote and continue "File" flow
            doc.dfp_external_storage_upload_file()
            return

        # MODIFY "File"

        # MODIFY "File": Case 1: Existent local file + new storage selected => upload to remote
        if (
            not doc.dfp_external_storage_s3_key
            and doc.dfp_external_storage
            and not previous.dfp_external_storage
        ):
            doc.dfp_external_storage_upload_file()

        # MODIFY "File": Case 2: Existent remote file + no storage selected => download to local + remove from remote
        elif previous.dfp_external_storage and not doc.dfp_external_storage:
            previous.download_to_local_and_remove_remote()
            doc.file_url = previous.file_url  # << contains local file path downloaded
            doc.dfp_external_storage_s3_key = ""

        # MODIFY "File": Case 3: Existent remote file + new remote selected => stream from old to new remote + delete from old remote
        elif (
            previous.dfp_external_storage
            and doc.dfp_external_storage
            and previous.dfp_external_storage != doc.dfp_external_storage
        ):
            try:
                # MODIFY "File": Case 3.1.: new remote + not allowed doctype => download to local + remove old remote
                # TODO: Maybe we should left in old remote?? and we should check if old remote allows the doctype??
                if doc.dfp_external_storage_ignored_doctypes():
                    previous.download_to_local_and_remove_remote()
                    doc.file_url = (
                        previous.file_url
                    )  # << contains local file path downloaded
                    doc.dfp_external_storage_s3_key = ""
                    doc.dfp_external_storage = ""
                # MODIFY "File": Case 3.2.: new remote + allowed doctype => stream from old to new remote + delete from old remote
                else:
                    # Check if we're moving between different storage types
                    old_storage_doc = previous.dfp_external_storage_doc
                    new_storage_doc = doc.dfp_external_storage_doc

                    if old_storage_doc.type != new_storage_doc.type:
                        # If storage types differ, we need to download and reupload
                        # Download from the old storage
                        content = previous.dfp_external_storage_download_file()

                        # Create a temporary file
                        temp_file_path = f"/tmp/{doc.name}_{doc.file_name}"
                        with open(temp_file_path, "wb") as f:
                            f.write(content)

                        # Remember the original key
                        original_key = doc.dfp_external_storage_s3_key

                        # Upload to the new storage
                        doc.dfp_external_storage_upload_file(temp_file_path)

                        # Clean up
                        os.remove(temp_file_path)

                        # Remove from old storage
                        previous.dfp_external_storage_delete_file()
                    else:
                        # Same storage type, stream directly

                        # Get file from previous remote in chunks of 10MB (not loading it fully in memory)
                        with previous.dfp_external_storage_file_proxy() as response:
                            doc.dfp_external_storage_client.put_object(
                                bucket_name=doc.dfp_external_storage_doc.bucket_name,
                                object_name=doc.dfp_external_storage_s3_key,
                                data=response,
                                length=response.object_size,
                                # Meta removed because same s3 file can be used within different File docs
                                # metadata={"frappe_file_id": self.name}
                            )
                        # New s3 key => update "file_url"
                        doc.file_url = doc._remote_file_local_path_get()
                        # Remove file from previous remote
                        previous.dfp_external_storage_delete_file()
                        # previous.dfp_external_storage_client.remove_object(
                        #     bucket_name=previous.dfp_external_storage_doc.bucket_name,
                        #     object_name=previous.dfp_external_storage_s3_key,
                        # )
            except Exception as e:
                error_msg = _("Error putting file from one remote to another.")
                frappe.log_error(f"{error_msg}: {doc.file_name}", message=str(e))
                frappe.throw(error_msg)

        # Clean cache when updating "File"
        if doc.dfp_external_storage_s3_key:
            cache_key = f"{DFP_EXTERNAL_STORAGE_PUBLIC_CACHE_PREFIX}{doc.name}"
            frappe.cache().delete_value(cache_key)
    except Exception as e:
        frappe.log_error(f"Error in hook_file_before_save: {str(e)}")


def hook_file_on_update(doc, method):
    """DEPRECATED! Remove method after 2025.01.01 ("/dfp_external_storage/dfp_external_storage/hooks.py" too)"""
    pass


def hook_file_after_delete(doc, method):
    """
    Called after a document is deleted

    Args:
        doc: File document
        method: Method name
    """
    try:
        doc.dfp_external_storage_delete_file()
    except Exception as e:
        frappe.log_error(f"Error in hook_file_after_delete: {str(e)}")


class DFPExternalStorageFileRenderer:
    """
    Renderer for files stored in external storage
    """

    def __init__(self, path, status_code=None):
        """
        Initialize renderer

        Args:
            path (str): File path
            status_code (int): HTTP status code
        """
        self.path = path
        self.status_code = status_code
        self._regex = None

    def _regexed_path(self):
        """Parse file path using regex"""
        self._regex = re.search(
            rf"{DFP_EXTERNAL_STORAGE_URL_SEGMENT_FOR_FILE_LOAD}\/(.+)\/(.+\.\w+)$",
            self.path,
        )

    def file_id_get(self):
        """
        Get file ID from path

        Returns:
            str: File ID or None
        """
        if self.can_render():
            return self._regex[1]
        return None

    def can_render(self):
        """
        Check if path can be rendered

        Returns:
            bool: True if path can be rendered
        """
        if not self._regex:
            self._regexed_path()
        return bool(self._regex)

    def render(self):
        """
        Render file

        Returns:
            Response: HTTP response
        """
        file_id = self._regex[1]
        file_name = self._regex[2] if len(self._regex.regs) == 3 else ""
        return file(name=file_id, file=file_name)


def file(name: str, file: str):
    """
    Get file content for HTTP response

    Args:
        name (str): File name
        file (str): File path

    Returns:
        Response: HTTP response

    Raises:
        frappe.PageDoesNotExistError: If file not found or not accessible
    """
    if not name or not file:
        raise frappe.PageDoesNotExistError()

    cache_key = f"{DFP_EXTERNAL_STORAGE_PUBLIC_CACHE_PREFIX}{name}"

    response_values = frappe.cache().get_value(cache_key)
    if not response_values:
        try:
            doc = frappe.get_doc("File", name)
            if not doc or not doc.is_downloadable() or doc.file_name != file:
                raise Exception("File not available")
        except Exception:
            # If no document, no read permissions, etc. For security reasons do not give any information, so just raise a 404 error
            raise frappe.PageDoesNotExistError()

        response_values = {}
        response_values["headers"] = []

        try:
            # Check for presigned URL first
            presigned_url = doc.dfp_presigned_url_get()
            if presigned_url:
                frappe.flags.redirect_location = presigned_url
                raise frappe.Redirect

            # Handle by storage type
            if (
                hasattr(doc, "dfp_external_storage_doc")
                and doc.dfp_external_storage_doc
            ):
                storage_type = doc.dfp_external_storage_doc.type

                # Use storage handler for non-S3 types if streaming is needed
                if storage_type not in ["AWS S3", "S3 Compatible"]:
                    storage_handler = handle_storage_type(doc)
                    if storage_handler and hasattr(storage_handler, "prepare_response"):
                        response_data = storage_handler.prepare_response()
                        response_values.update(response_data)

            # If no storage handler or S3 storage
            if "response" not in response_values:

                # Do not stream file if cacheable or smaller than stream buffer chunks size
                if (
                    doc.dfp_is_cacheable()
                    or doc.dfp_file_size
                    < doc.dfp_external_storage_doc.setting_stream_buffer_size
                ):
                    response_values["response"] = (
                        doc.dfp_external_storage_download_file()
                    )
                else:
                    response_values["response"] = doc.dfp_external_storage_stream_file()
                    response_values["headers"].append(
                        ("Content-Length", doc.dfp_file_size)
                    )
        except frappe.Redirect:
            raise
        except Exception as e:
            frappe.log_error(
                f"Error obtaining remote file content: {name}/{file} - {str(e)}"
            )

        if "response" not in response_values or not response_values["response"]:
            raise frappe.PageDoesNotExistError()

        if doc.dfp_mime_type_guess_by_file_name:
            response_values["mimetype"] = doc.dfp_mime_type_guess_by_file_name
        response_values["status"] = 200

        if doc.dfp_is_cacheable():
            frappe.cache().set_value(
                key=cache_key,
                val=response_values,
                expires_in_sec=doc.dfp_external_storage_doc.setting_cache_expiration_secs,
            )

    if "status" in response_values and response_values["status"] == 200:
        return Response(**response_values)

    raise frappe.PageDoesNotExistError()


@frappe.whitelist()
def test_s3_connection(doc_name=None, connection_data=None):
    """
    Test the connection to S3 storage

    Args:
        doc_name (str): Document name
        connection_data (dict): Connection parameters

    Returns:
        dict: Test result
    """
    try:
        if doc_name and not connection_data:
            # If we have a document name but no connection data, load it from the document
            doc = frappe.get_doc("DFP External Storage", doc_name)

            # Test connection using the document
            result = doc.verify_connection()
            return {"success": result, "message": "Connection tested"}

        elif connection_data:
            # If connection data is provided, use it directly
            if isinstance(connection_data, str):
                import json

                connection_data = json.loads(connection_data)

            # For testing a new or modified connection
            storage_type = connection_data.get("storage_type", "AWS S3")

            # For S3 storage types
            if storage_type in ["AWS S3", "S3 Compatible"]:
                endpoint = connection_data.get("endpoint")
                secure = connection_data.get("secure", False)
                bucket_name = connection_data.get("bucket_name")
                region = connection_data.get("region", "auto")
                access_key = connection_data.get("access_key")

                # If we're testing an existing document, get the secret key from it
                if doc_name and not connection_data.get("secret_key"):
                    secret_key = get_decrypted_password(
                        "DFP External Storage", doc_name, "secret_key"
                    )
                else:
                    secret_key = connection_data.get("secret_key")

                if not all([endpoint, bucket_name, access_key, secret_key]):
                    missing = []
                    if not endpoint:
                        missing.append("Endpoint")
                    if not bucket_name:
                        missing.append("Bucket Name")
                    if not access_key:
                        missing.append("Access Key")
                    if not secret_key:
                        missing.append("Secret Key")

                    return {
                        "success": False,
                        "message": f"Missing required fields: {', '.join(missing)}",
                    }

                # Create a temporary client to test the connection
                try:
                    if storage_type == "AWS S3":
                        import boto3

                        client = boto3.client(
                            "s3",
                            aws_access_key_id=access_key,
                            aws_secret_access_key=secret_key,
                            region_name=region,
                        )

                        # Test connection by listing buckets
                        response = client.list_buckets()

                        # Check if bucket exists
                        bucket_exists = False
                        for b in response["Buckets"]:
                            if b["Name"] == bucket_name:
                                bucket_exists = True
                                break
                        if not bucket_exists:
                            return {
                                "success": False,
                                "message": f"Connection successful, but bucket '{bucket_name}' not found. Available buckets: {', '.join([b['Name'] for b in response['Buckets']])}",
                            }

                        return {
                            "success": True,
                            "message": f"Successfully connected to AWS S3. Bucket '{bucket_name}' exists.",
                        }
                    else:
                        # S3 Compatible storage
                        from minio import Minio

                        client = Minio(
                            endpoint=endpoint,
                            access_key=access_key,
                            secret_key=secret_key,
                            region=region,
                            sucure=secure,
                        )

                        # Check if bucket exists
                        bucket_exists = client.bucket_exists(bucket_name)

                        if not bucket_exists:
                            return {
                                "success": False,
                                "message": f"Connection successful, but bucket '{bucket_name}' not found.",
                            }
                        return {
                            "success": True,
                            "message": f"Successfully connected to S3 compatible storage. Bucket '{bucket_name}' exists.",
                        }
                except Exception as e:
                    return {"success": False, "message": f"Connection failed: {str(e)}"}

            # For other storage types, route to appropriate handler
            elif storage_type == "Google Drive":
                try:
                    from dfp_external_storage.gdrive_integration import (
                        test_connection_params,
                    )

                    return test_connection_params(connection_data)
                except ImportError:
                    return {
                        "success": False,
                        "message": "Google Drive integration not available",
                    }

            elif storage_type == "OneDrive":
                try:
                    from dfp_external_storage.onedrive_integration import (
                        test_connection_params,
                    )

                    return test_connection_params(connection_data)
                except ImportError:
                    return {
                        "success": False,
                        "message": "OneDrive integration not available",
                    }

            elif storage_type == "Dropbox":
                try:
                    from dfp_external_storage.dropbox_integration import (
                        test_connection_params,
                    )

                    return test_connection_params(connection_data)
                except ImportError:
                    return {
                        "success": False,
                        "message": "Dropbox integration not available",
                    }

            else:
                return {
                    "success": False,
                    "message": f"Unsupported storage type: {storage_type}",
                }
        else:
            return {"success": False, "message": "No connection data provided"}
    except Exception as e:
        frappe.log_error(f"Error testing S3 connection: {str(e)}")
        return {"success": False, "message": f"Error testing connection: {str(e)}"}
