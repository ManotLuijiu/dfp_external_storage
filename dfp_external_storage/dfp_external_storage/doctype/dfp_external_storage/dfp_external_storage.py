import os
import re
import io
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

# Import Google Drive integration
from gdrive_integration import GoogleDriveConnection

# Import OneDrive integration
from onedrive_integration import OneDriveConnection

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
            tenant = storage_doc.onedrive_tenant or 'common'
            
            return OneDriveConnection(
                client_id=client_id,
                client_secret=client_secret,
                tenant=tenant,
                refresh_token=refresh_token
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
            with open(local_file, 'rb') as f:
                # Upload to OneDrive
                result = self.client.put_object(
                    folder_id=self.storage_doc.onedrive_folder_id,
                    file_name=self.file_name,
                    data=f,
                    metadata={"Content-Type": content_type}
                )
                
                # Update file document with OneDrive file ID
                self.file_doc.dfp_external_storage_s3_key = result.get('id')
                self.file_doc.dfp_external_storage = self.storage_doc.name
                
                # Update file_url to use our custom URL pattern
                from dfp_external_storage.dfp_external_storage.doctype.dfp_external_storage.dfp_external_storage import DFP_EXTERNAL_STORAGE_URL_SEGMENT_FOR_FILE_LOAD
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
                file_id=self.file_doc.dfp_external_storage_s3_key
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
                file_id=self.file_doc.dfp_external_storage_s3_key
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
                file_id=self.file_doc.dfp_external_storage_s3_key
            )
            
            # Wrap the file content for streaming
            return wrap_file(
                environ=frappe.local.request.environ,
                file=file_content,
                buffer_size=self.storage_doc.setting_stream_buffer_size
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
                file_id=self.file_doc.dfp_external_storage_s3_key
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
                folder_id=None,  # Not needed for OneDrive
                file_id=file_id
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
                expires=self.storage_doc.setting_presigned_url_expiration
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


# Functions to update DFPExternalStorageFile class to handle Google Drive
def handle_storage_type(file_doc):
    """
    Handle different storage types and return the appropriate handler

    Args:
        file_doc: DFPExternalStorageFile instance

    Returns:
        object: Storage handler instance
    """
    storage_type = file_doc.dfp_external_storage_doc.type

    if storage_type == "Google Drive":
        return DFPExternalStorageGoogleDriveFile(file_doc)
    return None  # Default S3 handlers will be used


# Modifications needed in DFPExternalStorageFile class:
"""
The following functions need to be updated in the main DFPExternalStorageFile class:

1. dfp_external_storage_upload_file:
   - Add a check for Google Drive storage type
   - Call the appropriate handler

2. dfp_external_storage_delete_file:
   - Add a check for Google Drive storage type
   - Call the appropriate handler

3. dfp_external_storage_download_file: 
   - Add a check for Google Drive storage type
   - Call the appropriate handler

4. dfp_external_storage_stream_file:
   - Add a check for Google Drive storage type
   - Call the appropriate handler

5. download_to_local_and_remove_remote:
   - Add a check for Google Drive storage type
   - Call the appropriate handler

6. dfp_presigned_url_get:
   - Add a check for Google Drive storage type
   - Call the appropriate handler
"""


class S3FileProxy:

    def __init__(self, readFn, object_size):
        self.readFn = readFn
        self.object_size = object_size
        # self.size = object_size # DEPRECATED! size is deprecated tell to Khoran, must be replaced by object_size
        self.offset = 0

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_value, traceback):
        pass

    def seek(self, offset, whence=0):
        if whence == io.SEEK_SET:
            self.offset = offset
        elif whence == io.SEEK_CUR:
            self.offset = self.offset + offset
        elif whence == io.SEEK_END:
            self.offset = self.object_size + offset

    def seekable(self):
        return True

    def tell(self):
        return self.offset

    def read(self, size=0):
        content = self.readFn(self.offset, size)
        self.offset = self.offset + len(content)
        return content


class DFPExternalStorage(Document):

    def validate(self):
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
        if not previous or has_changed(
            self, previous, DFP_EXTERNAL_STORAGE_CONNECTION_FIELDS
        ):
            self.validate_bucket()

    def diagnose_storage_config(self):
        """Diagnostic method to check storage configuration"""
        issues = []

        if not self.endpoint:
            issues.append("Missing endpoint")
        if not self.bucket_name:
            issues.append("Missing bucket name")
        if not self.access_key:
            issues.append("Missing access key")
        if not self.secret_key:
            issues.append("Missing secret key")

        return issues

    def verify_connection(self):
        """Verify S3 connection settings"""
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

            # Then test connection
            if self.type == "AWS S3":
                response = self.client.client.list_buckets()
                frappe.msgprint(
                    _("Successfully connected to AWS S3"), indicator="green"
                )
                return True
            else:
                response = self.client.client.list_buckets()
                frappe.msgprint(
                    _("Successfully connected to S3 compatible storage"),
                    indicator="green",
                )
                return True
        except Exception as e:
            frappe.log_error(f"Connection verification failed: {str(e)}")
            frappe.msgprint(
                _("Failed to verify connection: {}").format(str(e)), indicator="red"
            )
            return False

    def validate_bucket(self):
        """
        Enhanced bucket validation with configuration and connection checks
        """
        # First verify configuration and connection
        if not self.verify_connection():
            return False

        # Then proceed with existing bucket validation
        if self.client:
            self.client.validate_bucket(self.bucket_name)

    def on_trash(self):
        if self.files_within:
            frappe.throw(
                _("Can not be deleted. There are {} files using this bucket.").format(
                    self.files_within
                )
            )

    # Mimic Next3 Adding by Manot L.
    # @cached_property
    # def cdn_url(self):
    #     """Get CDN URL if configured"""
    #     if not self.use_cdn or not self.cdn_domain:
    #         return None
    #     return f"{self.cdn_protocol}://{self.cdn_domain.strip('/')}/"

    # def get_cdn_url(self, object_key):
    #     """Generate CDN URL for an object"""
    #     if not self.cdn_url:
    #         return None
    #     return f"{self.cdn_url}{object_key}"

    # def serve_via_cdn(self, file_doc):
    #     """Check if file should be served via CDN"""
    #     # Add any file type restrictions here
    #     return self.use_cdn and self.cdn_domain

    @cached_property
    def setting_stream_buffer_size(self):
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
        return frappe.db.count("File", filters={"dfp_external_storage": self.name})

    # def validate_bucket(self):
    #     # Add connection validation before bucket check
    #     if not self.endpoint or not self.access_key or not self.secret_key:
    #         frappe.throw(_("S3 connection parameters are incomplete"))
    #     if self.client:
    #         try:
    #             self.client.validate_bucket(self.bucket_name)
    #         except Exception as e:
    #             frappe.log_error(f"Bucket validation error: {str(e)}")
    #             frappe.throw(_("Failed to validate S3 bucket"))
    # self.client.validate_bucket(self.bucket_name)

    # Adding by Manot L.
    @cached_property
    def cdn_url(self):
        """Get CloudFront URL if configured"""
        if self.cloudfront_enabled and self.cloudfront_domain:
            return f"https://{self.cloudfront_domain.strip('/')}/"
        return None

    def get_cdn_url(self, object_key):
        """Generate CloudFront URL for an object"""
        if not self.cdn_url:
            return None
        return f"{self.cdn_url}{object_key}"

    @cached_property
    def client(self):
        """Initialize S3 client with proper error handling"""
        try:
            # Debug logging for configuration
            # frappe.logger().debug(
            #     f"Storage Configuration: endpoint={self.endpoint}, access_key={self.access_key}, region={self.region}, type={self.type}, secure={self.secure}"
            # )
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
            # Debug logging for secret key
            # frappe.logger().debug("Attempting to get secret key...")
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
            # Debug logging for client type
            # frappe.logger().debug(f"Initializing client for type: {self.type}")
            if self.type == "AWS S3":
                try:
                    import boto3

                    # frappe.logger().debug(
                    #     f"Initializing AWS S3 client with region {self.region}"
                    # )

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
            else:
                try:
                    # frappe.logger().debug(
                    #     f"Initializing MinIO client with endpoint {self.endpoint}"
                    # )
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
        # if self.endpoint and self.access_key and self.secret_key and self.region:
        #     try:
        #         if self.is_new() and self.secret_key:
        #             key_secret = self.secret_key
        #         else:
        #             key_secret = get_decrypted_password(
        #                 "DFP External Storage", self.name, "secret_key"
        #             )
        #         if key_secret:
        #             if self.type == "S3":
        #                 # Use boto3 for AWS S3
        #                 import boto3

        #                 return AWSS3Connection(
        #                     access_key=self.access_key,
        #                     secret_key=key_secret,
        #                     region=self.region,
        #                 )
        #             else:
        #                 # Use Minio for S3 Compatible storage
        #                 return MinioConnection(
        #                     endpoint=self.endpoint,
        #                     access_key=self.access_key,
        #                     secret_key=key_secret,
        #                     region=self.region,
        #                     secure=self.secure,
        #                 )
        #     except:
        #         pass

    def remote_files_list(self):
        return self.client.list_objects(self.bucket_name, recursive=True)


class AWSS3Connection:
    def __init__(self, access_key: str, secret_key: str, region: str):
        import boto3

        self.client = boto3.client(
            "s3",
            aws_access_key_id=access_key,
            aws_secret_access_key=secret_key,
            region_name=region,
        )

    def validate_bucket(self, bucket_name: str):
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
        return self.client.delete_object(Bucket=bucket_name, Key=object_name)

    def stat_object(self, bucket_name: str, object_name: str):
        return self.client.head_object(Bucket=bucket_name, Key=object_name)

    def get_object(
        self, bucket_name: str, object_name: str, offset: int = 0, length: int = 0
    ):
        range_header = f"bytes={offset}-{offset+length-1}" if length else None
        kwargs = {"Bucket": bucket_name, "Key": object_name}
        if range_header:
            kwargs["Range"] = range_header
        return self.client.get_object(**kwargs)["Body"]

    def fget_object(self, bucket_name: str, object_name: str, file_path: str):
        return self.client.download_file(bucket_name, object_name, file_path)

    def put_object(
        self,
        bucket_name: str,
        object_name: str,
        data,
        metadata: dict = None,
        length: int = -1,
    ):
        return self.client.upload_fileobj(data, bucket_name, object_name)

    def list_objects(self, bucket_name: str, recursive: bool = True):
        paginator = self.client.get_paginator("list_objects_v2")
        for page in paginator.paginate(Bucket=bucket_name):
            for obj in page.get("Contents", []):
                yield obj


class MinioConnection:
    def __init__(
        self, endpoint: str, access_key: str, secret_key: str, region: str, secure: bool
    ):
        self.client = Minio(
            endpoint=endpoint,
            access_key=access_key,
            secret_key=secret_key,
            region=region,
            secure=secure,
        )

    def validate_bucket(self, bucket_name: str):
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
        """
        return self.client.list_objects(bucket_name=bucket_name, recursive=recursive)


class DFPExternalStorageFile(File):
    def __init__(self, *args, **kwargs):
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

                frappe.logger().debug(f"Storage validation successful for {self.name}")

        except Exception as e:
            frappe.logger().error(
                f"Unexpected error during storage validation: {str(e)}"
            )
            raise

        # if self.dfp_external_storage and not self.dfp_external_storage_doc.client:
        #     # Get diagnostic info
        #     storage_doc = self.dfp_external_storage_doc
        #     issues = []
        #     if not storage_doc.endpoint:
        #         issues.append("endpoint")
        #     if not storage_doc.access_key:
        #         issues.append("access key")
        #     if not storage_doc.region:
        #         issues.append("region")
        #     if not storage_doc.bucket_name:
        #         issues.append("bucket name")

        #     if issues:
        #         frappe.throw(f"Storage configuration is missing: {', '.join(issues)}")
        #     else:
        #         frappe.throw(
        #             "Failed to initialize storage client. Please check error logs for details."
        #         )

    # def get_presigned_or_cdn_url(self):
    #     """Get either CloudFront or presigned URL"""
    #     if self.dfp_external_storage_doc.cdn_url:
    #         return self.dfp_external_storage_doc.get_cdn_url(
    #             self.dfp_external_storage_s3_key
    #         )
    #     return self.dfp_presigned_url_get()

    # Add to DFPExternalStorageFile class

    # def get_public_url(self):
    #     """Get public URL for the file (through CDN if enabled)"""
    #     if not self.dfp_is_s3_remote_file():
    #         return self.file_url

    #     if self.dfp_external_storage_doc.serve_via_cdn(self):
    #         return self.dfp_external_storage_doc.get_cdn_url(
    #             self.dfp_external_storage_s3_key
    #         )

    #     # Otherwise, return presigned URL if available
    #     presigned_url = self.dfp_presigned_url_get()
    #     if presigned_url:
    #         return presigned_url

    #     # Fallback to regular file URL
    #     return self.file_url

    def is_image(self):
        """Check if file is an image"""
        mime_type = self.dfp_mime_type_guess_by_file_name
        return mime_type and mime_type.startswith("image/")

    def get_image_tag(self, alt_text=""):
        """Get HTML image tag for the file (for WordPress-like functionality)"""
        if not self.is_image():
            return ""

        url = self.get_public_url()
        return f'<img src="{url}" alt="{alt_text or self.file_name}">'

    @property
    def is_remote_file(self):
        return (
            True
            if self.dfp_external_storage_s3_key
            else super(DFPExternalStorageFile, self).is_remote_file
        )

    @cached_property
    def dfp_external_storage_doc(self):
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
        if self.dfp_external_storage_s3_key and self.dfp_external_storage_doc:
            return True

    def dfp_is_cacheable(self):
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
        # return (
        #     not self.is_private
        #     and self.dfp_external_storage_doc.setting_cache_files_smaller_than
        #     and self.dfp_file_size != 0
        #     and self.dfp_file_size
        #     < self.dfp_external_storage_doc.setting_cache_files_smaller_than
        # )

    @cached_property
    def dfp_file_size(self) -> int:
        if (
            self.dfp_is_s3_remote_file()
            and self.dfp_external_storage_doc.remote_size_enabled
        ):
            try:
                object_info = self.dfp_external_storage_doc.client.stat_object(
                    bucket_name=self.dfp_external_storage_doc.bucket_name,
                    object_name=self.dfp_external_storage_s3_key,
                )
                return object_info.size
            except:
                frappe.log_error(
                    title=f"Error getting remote file size: {self.dfp_external_storage_s3_key}"
                )
        return self.file_size

    @cached_property
    def dfp_external_storage_client(self):
        if self.dfp_external_storage_doc:
            return self.dfp_external_storage_doc.client

    def dfp_external_storage_ignored_doctypes(self):
        "Do not apply for files attached to specified doctypes"
        if (
            self.attached_to_doctype
            and self.dfp_external_storage_doc
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

    def dfp_external_storage_upload_file(self, local_file=None):
        """
        Critical fields: "dfp_external_storage_s3_key", "dfp_external_storage" and "file_url"
        :param local_file: if given, file path for reading the content. If not given, the content field of this File is used
        """
        try:
            # Log upload attempt
            frappe.logger().debug(
                f"Attempting to upload file to S3: {self.name}, Local file: {local_file}"
            )

            # Check for ignored doctypes
            if self.dfp_external_storage_ignored_doctypes():
                frappe.logger().info(
                    f"Doctype ignored for S3 upload: {self.attached_to_doctype}"
                )
                self.dfp_external_storage = ""
                return False

            # Basic validations
            # if (
            #     not self.dfp_external_storage_doc
            #     or not self.dfp_external_storage_doc.enabled
            # ):
            #     frappe.throw(_("External storage is not configured or enabled"))
            #     return False

            # Validate storage configuration
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
                # File already on S3
                frappe.logger().debug(
                    f"File already on S3 with key {self.dfp_external_storage_s3_key}"
                )
                return False

            if self.file_url and self.file_url.startswith(URL_PREFIXES):
                frappe.logger().error(f"Cannot upload URL file to S3: {self.file_url}")
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
                    # frappe.logger().debug(
                    #     f"Uploading file {self.file_name} ({file_size} bytes)"
                    # )

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

        except Exception as e:
            frappe.logger().error(
                f"Unexpected error during S3 upload: {str(e)}", exc_info=True
            )
            frappe.msgprint(f"Failed to upload file to S3: {str(e)}")
            frappe.throw(_("Failed to upload file to S3: {}").format(str(e)))
            return False
        # if self.dfp_external_storage_ignored_doctypes():
        #     self.dfp_external_storage = ""
        #     return False
        # if (
        #     not self.dfp_external_storage_doc
        #     or not self.dfp_external_storage_doc.enabled
        # ):
        #     return False
        # if self.is_folder:
        #     return False
        # if self.dfp_external_storage_s3_key:
        # File already on S3
        # return False
        # if self.file_url and self.file_url.startswith(URL_PREFIXES):
        # frappe.throw(_("Not implemented save http(s)://file(s) to local."))
        # raise NotImplementedError(
        #     "http(s)://file(s) not ready to be saved to local or external storage(s)."
        # )

        # original_file_url = self.file_url

        # Define S3 key
        # key = f"{frappe.local.site}/{self.file_name}" # << Before 2024.03.03
        # base, extension = os.path.splitext(self.file_name)
        # key = f"{frappe.local.site}/{base}-{self.name}{extension}"

        # is_public = "/public" if not self.is_private else ""
        # if not local_file:
        # local_file = "./" + frappe.local.site + is_public + self.file_url

        # try:
        #     if not os.path.exists(local_file):
        #         frappe.throw(_("Local file not found"))
        #     with open(local_file, "rb") as f:
        #         self.dfp_external_storage_client.put_object(
        #             bucket_name=self.dfp_external_storage_doc.bucket_name,
        #             object_name=key,
        #             data=f,
        #             length=os.path.getsize(local_file),
        #             # Meta removed because same s3 file can be used within different File docs
        #             # metadata={"frappe_file_id": self.name}
        #         )

        #     self.dfp_external_storage_s3_key = key
        #     self.dfp_external_storage = self.dfp_external_storage_doc.name
        #     self.file_url = f"/{DFP_EXTERNAL_STORAGE_URL_SEGMENT_FOR_FILE_LOAD}/{self.name}/{self.file_name}"
        #     os.remove(local_file)
        # except Exception as e:
        #     error_msg = _("Error saving file in remote folder: {}").format(str(e))
        #     frappe.log_error(f"{error_msg}: {self.file_name}", message=e)
        #     # If file is new we upload to local filesystem
        #     if not self.get_doc_before_save():
        #         error_extra = _("File saved in local filesystem.")
        #         frappe.log_error(f"{error_msg} {error_extra}: {self.file_name}")
        #         self.dfp_external_storage_s3_key = ""
        #         self.dfp_external_storage = ""
        #         self.file_url = original_file_url
        #     # If modifing existent file throw error
        #     else:
        #         frappe.throw(error_msg)

    def dfp_external_storage_delete_file(self):
        if not self.dfp_is_s3_remote_file():
            return
        # Do not delete if other file docs are using same dfp_external_storage
        # and dfp_external_storage_s3_key
        files_using_s3_key = frappe.get_all(
            "File",
            filters={
                "dfp_external_storage_s3_key": self.dfp_external_storage_s3_key,
                "dfp_external_storage": self.dfp_external_storage,
            },
        )
        if len(files_using_s3_key):
            return
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
        except Exception as e:
            frappe.log_error(f"{error_msg}: {self.file_name}", message=e)
            frappe.throw(f"{error_msg} {str(e)}")

    def dfp_external_storage_download_to_file(self, local_file):
        """
        Stream file from S3 directly to local_file. This avoids reading the whole file into memory at any point
        :param local_file: path to a local file to stream content to
        """
        if not self.dfp_is_s3_remote_file():
            # frappe.msgprint(_("S3 key not found: ") + self.file_name,
            # 	indicator="red", title=_("Error processing File"), alert=True)
            return
        try:
            key = self.dfp_external_storage_s3_key

            self.dfp_external_storage_client.fget_object(
                bucket_name=self.dfp_external_storage_doc.bucket_name,
                object_name=key,
                file_path=local_file,
            )
        except Exception as e:
            error_msg = _(
                "Error downloading to file from remote folder. Check Error Log for more information."
            )
            frappe.log_error(title=f"{error_msg}: {self.file_name}", message=e)
            frappe.throw(error_msg)

    def dfp_external_storage_file_proxy(self):
        """
        Get a read-only context manager file-like object that will read requested bytes directly from S3. This allows you to avoid downloading the whole file when only parts or chunks of it will be read from.
        """
        if not self.dfp_is_s3_remote_file():
            frappe.log_error(f"Invalid S3 file configuration for {self.name}")
            return

        def read_chunks(offset=0, size=0):
            try:
                # frappe.logger().debug(f"Reading chunk: offset={offset}, size={size}")
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
            # with self.dfp_external_storage_client.get_object(
            #     bucket_name=self.dfp_external_storage_doc.bucket_name,
            #     object_name=self.dfp_external_storage_s3_key,
            #     offset=offset,
            #     length=size,
            # ) as response:
            #     content = response.read()
            # return content

        return S3FileProxy(readFn=read_chunks, object_size=self.dfp_file_size)

    def dfp_external_storage_download_file(self) -> bytes:
        content = b""
        if not self.dfp_is_s3_remote_file():
            return content
        try:
            with self.dfp_external_storage_client.get_object(
                bucket_name=self.dfp_external_storage_doc.bucket_name,
                object_name=self.dfp_external_storage_s3_key,
            ) as response:
                content = response.read()
            return content
        except:
            error_msg = _("Error downloading file from remote folder")
            frappe.log_error(title=f"{error_msg}: {self.file_name}")
            frappe.throw(error_msg)
        return content

    def dfp_external_storage_stream_file(self) -> t.Iterable[bytes]:
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
        # return wrap_file(
        #     environ=frappe.local.request.environ,
        #     file=self.dfp_external_storage_file_proxy(),
        #     buffer_size=self.dfp_external_storage_doc.setting_stream_buffer_size,
        # )

    def download_to_local_and_remove_remote(self):
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
        except:
            error_msg = _("Error downloading and removing file from remote folder.")
            frappe.log_error(title=f"{error_msg}: {self.file_name}")
            frappe.throw(error_msg)

    def validate_file_on_disk(self):
        return (
            True
            if self.dfp_is_s3_remote_file()
            else super(DFPExternalStorageFile, self).validate_file_on_disk()
        )

    def exists_on_disk(self):
        return (
            False
            if self.dfp_is_s3_remote_file()
            else super(DFPExternalStorageFile, self).exists_on_disk()
        )

    @frappe.whitelist()
    def optimize_file(self):
        if self.dfp_is_s3_remote_file():
            raise NotImplementedError("Only local image files can be optimized")
        super(DFPExternalStorageFile, self).optimize_file()

    def _remote_file_local_path_get(self):
        if not self.name or not self.file_name:
            frappe.throw(_("Invalid file path parameters"))
        return f"/{DFP_EXTERNAL_STORAGE_URL_SEGMENT_FOR_FILE_LOAD}/{self.name}/{self.file_name}"

    def dfp_file_url_is_s3_location_check_if_s3_data_is_not_defined(self):
        """
        Set `dfp_external_storage_s3_key` if `file_url` exists and can be rendered.
        Sometimes, when a file is copied (for example, when amending a sales invoice), we have the `file_url` but not the `key` (refer to the method `copy_attachments_from_amended_from` in `document.py`).
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
        except:
            pass

    def get_content(self) -> bytes:
        self.dfp_file_url_is_s3_location_check_if_s3_data_is_not_defined()
        if not self.dfp_is_s3_remote_file():
            return super(DFPExternalStorageFile, self).get_content()
        try:
            if not self.is_downloadable():
                raise Exception("File not available")
            return self.dfp_external_storage_download_file()
        except Exception:
            # If no document, no read permissions, etc. For security reasons do not give any information, so just raise a 404 error
            raise frappe.PageDoesNotExistError()

    @cached_property
    def dfp_mime_type_guess_by_file_name(self):
        content_type, _ = mimetypes.guess_type(self.file_name)
        if content_type:
            return content_type

    def dfp_presigned_url_get(self):
        if (
            not self.dfp_is_s3_remote_file()
            or not self.dfp_external_storage_doc.presigned_urls
        ):
            return
        if (
            self.dfp_external_storage_doc.presigned_mimetypes_starting
            and self.dfp_mime_type_guess_by_file_name
        ):
            # get list exploding by new line, removing empty lines and cleaning starting and ending spaces
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
                return
        return self.dfp_external_storage_client.presigned_get_object(
            bucket_name=self.dfp_external_storage_doc.bucket_name,
            object_name=self.dfp_external_storage_s3_key,
            expires=self.dfp_external_storage_doc.setting_presigned_url_expiration,
        )


def hook_file_before_save(doc, method):
    """
    This method is called before the document is saved to DB (insert or update row)
    Critical fields: dfp_external_storage_s3_key, dfp_external_storage and file_url
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
                    previous.dfp_external_storage_client.remove_object(
                        bucket_name=previous.dfp_external_storage_doc.bucket_name,
                        object_name=previous.dfp_external_storage_s3_key,
                    )
            except:
                error_msg = _("Error putting file from one remote to another.")
                frappe.log_error(f"{error_msg}: {doc.file_name}")
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
    "Called after a document is deleted"
    doc.dfp_external_storage_delete_file()


class DFPExternalStorageFileRenderer:
    def __init__(self, path, status_code=None):
        self.path = path
        self.status_code = status_code
        self._regex = None

    def _regexed_path(self):
        self._regex = re.search(
            rf"{DFP_EXTERNAL_STORAGE_URL_SEGMENT_FOR_FILE_LOAD}\/(.+)\/(.+\.\w+)$",
            self.path,
        )

    def file_id_get(self):
        if self.can_render():
            return self._regex[1]

    def can_render(self):
        if not self._regex:
            self._regexed_path()
        if self._regex:
            return True

    def render(self):
        file_id = self._regex[1]
        file_name = self._regex[2] if len(self._regex.regs) == 3 else ""
        return file(name=file_id, file=file_name)


def file(name: str, file: str):
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
            presigned_url = doc.dfp_presigned_url_get()
            if presigned_url:
                frappe.flags.redirect_location = presigned_url
                raise frappe.Redirect
            # Do not stream file if cacheable or smaller than stream buffer chunks size
            if (
                doc.dfp_is_cacheable()
                or doc.dfp_file_size
                < doc.dfp_external_storage_doc.setting_stream_buffer_size
            ):
                response_values["response"] = doc.dfp_external_storage_download_file()
            else:
                response_values["response"] = doc.dfp_external_storage_stream_file()
                response_values["headers"].append(("Content-Length", doc.dfp_file_size))
        except frappe.Redirect:
            raise
        except:
            frappe.log_error(f"Error obtaining remote file content: {name}/{file}")

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
    """Test the connection to S3 storage"""
    try:
        if doc_name and not connection_data:
            # If we have a document name but no connection data, load it from the document
            doc = frappe.get_doc("DFP External Storage", doc_name)

            # Test connection using the document
            return doc.verify_connection()
        elif connection_data:
            # If connection data is provided, use it directly
            if isinstance(connection_data, str):
                import json

                connection_data = json.loads(connection_data)

            # For testing a new or modified connection
            storage_type = connection_data.get("storage_type", "AWS S3")
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
        else:
            return {"success": False, "message": "No connection data provided"}
    except Exception as e:
        frappe.log_error(f"Error testing S3 connection: {str(e)}")
        return {"success": False, "message": f"Error testing connection: {str(e)}"}
