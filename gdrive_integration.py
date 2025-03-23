"""
Google Drive Integration for DFP External Storage

This module adds Google Drive support to the DFP External Storage app.
It requires the following dependencies:
- google-api-python-client
- google-auth
- google-auth-oauthlib
"""

import io
import os
import re
import json
import frappe
from frappe import _
from frappe.utils import get_request_site_address, get_url
from datetime import datetime, timedelta
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
from googleapiclient.http import MediaIoBaseUpload, MediaIoBaseDownload
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import Flow
from google.auth.transport.requests import Request
from google.auth.exceptions import RefreshError

# Google Drive API scopes
SCOPES = ["https://www.googleapis.com/auth/drive.file"]

# Cache key prefix for Google Drive tokens
DFP_GDRIVE_TOKEN_CACHE_PREFIX = "dfp_gdrive_token:"


class GoogleDriveConnection:
    """Google Drive connection handler for DFP External Storage"""

    def __init__(
        self,
        client_id,
        client_secret,
        refresh_token,
        token_uri="https://oauth2.googleapis.com/token",
    ):
        """
        Initialize Google Drive connection

        Args:
            client_id (str): Google API Client ID
            client_secret (str): Google API Client Secret
            refresh_token (str): OAuth2 refresh token
            token_uri (str): Token URI for OAuth2
        """
        self.client_id = client_id
        self.client_secret = client_secret
        self.refresh_token = refresh_token
        self.token_uri = token_uri
        self.service = None

        # Initialize the connection
        self._connect()

    def _connect(self):
        """Establish connection to Google Drive API"""
        try:
            creds = Credentials(
                None,  # No access token initially
                refresh_token=self.refresh_token,
                token_uri=self.token_uri,
                client_id=self.client_id,
                client_secret=self.client_secret,
                scopes=SCOPES,
            )

            # Refresh the token if expired
            if creds.expired:
                creds.refresh(Request())

            # Build the Drive API service
            self.service = build("drive", "v3", credentials=creds)
            return True
        except Exception as e:
            frappe.log_error(f"Google Drive connection error: {str(e)}")
            return False

    def validate_folder(self, folder_id):
        """
        Validate if a Google Drive folder exists and is accessible

        Args:
            folder_id (str): Google Drive folder ID

        Returns:
            bool: True if folder exists and is accessible
        """
        try:
            # Try to get folder metadata
            folder = (
                self.service.files()
                .get(
                    fileId=folder_id, fields="id,name,mimeType", supportsAllDrives=True
                )
                .execute()
            )

            # Verify it's a folder
            if folder.get("mimeType") != "application/vnd.google-apps.folder":
                frappe.msgprint(
                    _("The specified Google Drive ID is not a folder"), alert=True
                )
                return False

            frappe.msgprint(
                _("Google Drive folder found: {0}").format(folder.get("name")),
                indicator="green",
                alert=True,
            )
            return True
        except HttpError as e:
            if e.resp.status == 404:
                frappe.throw(_("Google Drive folder not found"))
            else:
                frappe.throw(
                    _("Error accessing Google Drive folder: {0}").format(str(e))
                )
            return False
        except Exception as e:
            frappe.throw(_("Error validating Google Drive folder: {0}").format(str(e)))
            return False

    def remove_object(self, folder_id, file_id):
        """
        Remove a file from Google Drive

        Args:
            folder_id (str): Not used for Google Drive (included for API compatibility)
            file_id (str): Google Drive file ID

        Returns:
            bool: True if file was successfully deleted
        """
        try:
            self.service.files().delete(fileId=file_id).execute()
            return True
        except Exception as e:
            frappe.log_error(f"Google Drive delete error: {str(e)}")
            return False

    def stat_object(self, folder_id, file_id):
        """
        Get file metadata from Google Drive

        Args:
            folder_id (str): Not used for Google Drive (included for API compatibility)
            file_id (str): Google Drive file ID

        Returns:
            dict: File metadata
        """
        try:
            return (
                self.service.files()
                .get(
                    fileId=file_id,
                    fields="id,name,mimeType,size,modifiedTime,md5Checksum",
                )
                .execute()
            )
        except Exception as e:
            frappe.log_error(f"Google Drive stat error: {str(e)}")
            raise

    def get_object(self, folder_id, file_id, offset=0, length=0):
        """
        Get file content from Google Drive

        Args:
            folder_id (str): Not used for Google Drive (included for API compatibility)
            file_id (str): Google Drive file ID
            offset (int): Start byte position (not directly supported by Google Drive)
            length (int): Number of bytes to read (not directly supported by Google Drive)

        Returns:
            BytesIO: File content as a file-like object
        """
        try:
            request = self.service.files().get_media(fileId=file_id)
            file_content = io.BytesIO()
            downloader = MediaIoBaseDownload(file_content, request)

            done = False
            while not done:
                status, done = downloader.next_chunk()

            # Reset position to beginning
            file_content.seek(0)

            # Handle offset and length if specified
            if offset > 0 or length > 0:
                file_content.seek(offset)
                if length > 0:
                    return io.BytesIO(file_content.read(length))

            return file_content
        except Exception as e:
            frappe.log_error(f"Google Drive download error: {str(e)}")
            raise

    def fget_object(self, folder_id, file_id, file_path):
        """
        Download file from Google Drive to a local path

        Args:
            folder_id (str): Not used for Google Drive (included for API compatibility)
            file_id (str): Google Drive file ID
            file_path (str): Local file path to save the file

        Returns:
            bool: True if file was successfully downloaded
        """
        try:
            request = self.service.files().get_media(fileId=file_id)
            with open(file_path, "wb") as f:
                downloader = MediaIoBaseDownload(f, request)
                done = False
                while not done:
                    status, done = downloader.next_chunk()
            return True
        except Exception as e:
            frappe.log_error(f"Google Drive download to file error: {str(e)}")
            raise

    def put_object(self, folder_id, file_name, data, metadata=None, length=-1):
        """
        Upload file to Google Drive

        Args:
            folder_id (str): Google Drive folder ID to upload to
            file_name (str): Name for the uploaded file
            data: File-like object with data to upload
            metadata (dict): Additional metadata (not used for Google Drive)
            length (int): Data size (optional)

        Returns:
            dict: File metadata for the uploaded file
        """
        try:
            # Prepare file metadata
            file_metadata = {"name": file_name, "parents": [folder_id]}

            # Prepare media
            mimetype = (
                metadata.get("Content-Type", "application/octet-stream")
                if metadata
                else "application/octet-stream"
            )
            media = MediaIoBaseUpload(data, mimetype=mimetype, resumable=True)

            # Upload file
            file = (
                self.service.files()
                .create(
                    body=file_metadata,
                    media_body=media,
                    fields="id,name,mimeType,size,modifiedTime,md5Checksum",
                )
                .execute()
            )

            return file
        except Exception as e:
            frappe.log_error(f"Google Drive upload error: {str(e)}")
            raise

    def list_objects(self, folder_id, recursive=True):
        """
        List files in a Google Drive folder

        Args:
            folder_id (str): Google Drive folder ID
            recursive (bool): Whether to list files in subfolders

        Returns:
            list: List of file metadata objects
        """
        try:
            query = f"'{folder_id}' in parents and trashed=false"

            page_token = None
            while True:
                response = (
                    self.service.files()
                    .list(
                        q=query,
                        spaces="drive",
                        fields="nextPageToken, files(id, name, mimeType, size, modifiedTime, md5Checksum, parents)",
                        pageToken=page_token,
                    )
                    .execute()
                )

                for file in response.get("files", []):
                    # Adapt Google Drive response to match S3 format
                    yield {
                        "object_name": file.get("name"),
                        "size": int(file.get("size", 0)) if file.get("size") else 0,
                        "etag": file.get("md5Checksum", ""),
                        "last_modified": file.get("modifiedTime"),
                        "is_dir": file.get("mimeType")
                        == "application/vnd.google-apps.folder",
                        "storage_class": "GOOGLE_DRIVE",
                        "metadata": {
                            "id": file.get("id"),
                            "mime_type": file.get("mimeType"),
                        },
                    }

                page_token = response.get("nextPageToken")
                if not page_token or not recursive:
                    break

            # If recursive, get files from subfolders
            if recursive:
                # Find subfolders
                folder_query = f"'{folder_id}' in parents and mimeType='application/vnd.google-apps.folder' and trashed=false"
                folders_response = (
                    self.service.files()
                    .list(q=folder_query, fields="files(id)")
                    .execute()
                )

                # List files in each subfolder
                for subfolder in folders_response.get("files", []):
                    subfolder_id = subfolder.get("id")
                    yield from self.list_objects(subfolder_id, recursive)

        except Exception as e:
            frappe.log_error(f"Google Drive list error: {str(e)}")
            yield None

    def presigned_get_object(self, folder_id, file_id, expires=timedelta(hours=3)):
        """
        Create a temporary shareable link for a Google Drive file

        Args:
            folder_id (str): Not used for Google Drive (included for API compatibility)
            file_id (str): Google Drive file ID
            expires (timedelta): How long the link should be valid

        Returns:
            str: Temporary shareable link
        """
        try:
            # Create a permission for anyone with the link to access the file
            # This is similar to a presigned URL in S3
            expiration = datetime.utcnow() + expires
            expires_epoch = int(expiration.timestamp())

            # Use Drive API to create a web view link
            # Note: This is different from S3 presigned URLs as it requires changing permissions
            file = (
                self.service.files().get(fileId=file_id, fields="webViewLink").execute()
            )

            # Return the web view link
            return file.get("webViewLink")
        except Exception as e:
            frappe.log_error(f"Google Drive presigned URL error: {str(e)}")
            return None


# Helper functions for Google Drive OAuth flow


def get_google_drive_oauth_url(client_id, client_secret, redirect_uri=None):
    """
    Generate OAuth URL for Google Drive authentication

    Args:
        client_id (str): Google API Client ID
        client_secret (str): Google API Client Secret
        redirect_uri (str): OAuth redirect URI

    Returns:
        str: OAuth URL for user authorization
    """
    if not redirect_uri:
        redirect_uri = get_url(
            "/api/method/dfp_external_storage.gdrive_integration.oauth_callback"
        )

    try:
        # Create OAuth flow
        flow = Flow.from_client_config(
            {
                "web": {
                    "client_id": client_id,
                    "client_secret": client_secret,
                    "auth_uri": "https://accounts.google.com/o/oauth2/auth",
                    "token_uri": "https://oauth2.googleapis.com/token",
                    "redirect_uris": [redirect_uri],
                }
            },
            scopes=SCOPES,
            redirect_uri=redirect_uri,
        )

        # Generate authorization URL
        auth_url, _ = flow.authorization_url(
            access_type="offline",
            include_granted_scopes="true",
            prompt="consent",  # Force to get refresh token
        )

        # Store flow information in cache for callback
        cache_key = f"{DFP_GDRIVE_TOKEN_CACHE_PREFIX}flow_{frappe.session.user}"
        frappe.cache().set_value(cache_key, flow.to_json())

        return auth_url
    except Exception as e:
        frappe.log_error(f"Google Drive OAuth URL generation error: {str(e)}")
        frappe.throw(_("Error generating Google Drive OAuth URL: {0}").format(str(e)))


@frappe.whitelist()
def oauth_callback():
    """Handle OAuth callback from Google"""
    try:
        # Get authorization code from request
        code = frappe.request.args.get("code")
        if not code:
            frappe.throw(_("Missing authorization code"))

        # Get flow from cache
        cache_key = f"{DFP_GDRIVE_TOKEN_CACHE_PREFIX}flow_{frappe.session.user}"
        flow_json = frappe.cache().get_value(cache_key)
        if not flow_json:
            frappe.throw(_("Authentication session expired"))

        # Recreate flow
        flow = Flow.from_json(flow_json)

        # Exchange code for tokens
        flow.fetch_token(code=code)

        # Get credentials
        credentials = flow.credentials

        # Store in session for later use
        session_key = (
            f"{DFP_GDRIVE_TOKEN_CACHE_PREFIX}credentials_{frappe.session.user}"
        )
        frappe.cache().set_value(
            session_key,
            {
                "refresh_token": credentials.refresh_token,
                "client_id": credentials.client_id,
                "client_secret": credentials.client_secret,
                "token": credentials.token,
                "expiry": (
                    credentials.expiry.isoformat() if credentials.expiry else None
                ),
            },
        )

        # Clean up flow cache
        frappe.cache().delete_value(cache_key)

        # Redirect to success page or document
        success_url = frappe.cache().get_value(
            f"{DFP_GDRIVE_TOKEN_CACHE_PREFIX}success_url_{frappe.session.user}"
        )
        if success_url:
            frappe.cache().delete_value(
                f"{DFP_GDRIVE_TOKEN_CACHE_PREFIX}success_url_{frappe.session.user}"
            )
            frappe.local.response["type"] = "redirect"
            frappe.local.response["location"] = success_url
        else:
            # Default success message
            frappe.respond_as_web_page(
                _("Google Drive Authentication Successful"),
                _(
                    "You have successfully authenticated with Google Drive. You can close this window and return to the app."
                ),
                indicator_color="green",
            )
    except Exception as e:
        frappe.log_error(f"Google Drive OAuth callback error: {str(e)}")
        frappe.respond_as_web_page(
            _("Google Drive Authentication Failed"),
            _("An error occurred during authentication: {0}").format(str(e)),
            indicator_color="red",
        )


@frappe.whitelist()
def initiate_google_drive_auth(doc_name, client_id, client_secret):
    """
    Initiate Google Drive OAuth flow from the DFP External Storage document

    Args:
        doc_name (str): DFP External Storage document name
        client_id (str): Google API Client ID
        client_secret (str): Google API Client Secret

    Returns:
        dict: Response with auth_url for redirection
    """
    try:
        # Set success URL in cache
        success_url = get_url(f"/desk#Form/DFP External Storage/{doc_name}")
        frappe.cache().set_value(
            f"{DFP_GDRIVE_TOKEN_CACHE_PREFIX}success_url_{frappe.session.user}",
            success_url,
        )

        # Generate OAuth URL
        auth_url = get_google_drive_oauth_url(client_id, client_secret)

        return {"success": True, "auth_url": auth_url}
    except Exception as e:
        frappe.log_error(f"Error initiating Google Drive auth: {str(e)}")
        return {"success": False, "error": str(e)}


@frappe.whitelist()
def get_auth_credentials():
    """
    Get Google Drive auth credentials from session
    Returns credentials if they exist, None otherwise
    """
    session_key = f"{DFP_GDRIVE_TOKEN_CACHE_PREFIX}credentials_{frappe.session.user}"
    return frappe.cache().get_value(session_key)


@frappe.whitelist()
def test_google_drive_connection(doc_name=None, connection_data=None):
    """
    Test the connection to Google Drive

    Args:
        doc_name (str): DFP External Storage document name
        connection_data (dict): Connection data with client_id, client_secret, refresh_token, folder_id

    Returns:
        dict: Response with success status and message
    """
    try:
        if doc_name and not connection_data:
            # If we have a document name but no connection data, load it from the document
            doc = frappe.get_doc("DFP External Storage", doc_name)

            # Test the connection using document's stored credentials
            client_id = doc.google_client_id
            client_secret = frappe.utils.password.get_decrypted_password(
                "DFP External Storage", doc_name, "google_client_secret"
            )
            refresh_token = frappe.utils.password.get_decrypted_password(
                "DFP External Storage", doc_name, "google_refresh_token"
            )
            folder_id = doc.google_folder_id

        elif connection_data:
            # If connection data is provided, use it directly
            if isinstance(connection_data, str):
                connection_data = json.loads(connection_data)

            client_id = connection_data.get("client_id")
            client_secret = connection_data.get("client_secret")
            refresh_token = connection_data.get("refresh_token")
            folder_id = connection_data.get("folder_id")

        else:
            return {"success": False, "message": "No connection data provided"}

        # Validate required fields
        if not all([client_id, client_secret, refresh_token, folder_id]):
            missing = []
            if not client_id:
                missing.append("Client ID")
            if not client_secret:
                missing.append("Client Secret")
            if not refresh_token:
                missing.append("Refresh Token")
            if not folder_id:
                missing.append("Folder ID")

            return {
                "success": False,
                "message": f"Missing required fields: {', '.join(missing)}",
            }

        # Create connection and test
        connection = GoogleDriveConnection(
            client_id=client_id,
            client_secret=client_secret,
            refresh_token=refresh_token,
        )

        if not connection.service:
            return {
                "success": False,
                "message": "Failed to connect to Google Drive API",
            }

        # Test folder access
        folder_exists = connection.validate_folder(folder_id)

        if folder_exists:
            return {
                "success": True,
                "message": f"Successfully connected to Google Drive and verified folder access",
            }
        else:
            return {
                "success": False,
                "message": "Connected to Google Drive but folder not found or not accessible",
            }

    except Exception as e:
        frappe.log_error(f"Error testing Google Drive connection: {str(e)}")
        return {"success": False, "message": f"Error testing connection: {str(e)}"}
