"""
Dropbox Integration for DFP External Storage

This module adds Dropbox support to the DFP External Storage app.
It requires the following dependencies:
- dropbox
"""

import io
import os
import re
import json
import frappe
from frappe import _
from frappe.utils import get_request_site_address, get_url
from datetime import datetime, timedelta
import dropbox
from dropbox import DropboxOAuth2Flow
from dropbox.exceptions import ApiError, AuthError
from dropbox.files import FileMetadata, FolderMetadata

# Cache key prefix for Dropbox tokens
DFP_DROPBOX_TOKEN_CACHE_PREFIX = "dfp_dropbox_token:"


class DropboxConnection:
    """Dropbox connection handler for DFP External Storage"""

    def __init__(self, app_key, app_secret, refresh_token=None, access_token=None):
        """
        Initialize Dropbox connection

        Args:
            app_key (str): Dropbox app key
            app_secret (str): Dropbox app secret
            refresh_token (str): OAuth2 refresh token
            access_token (str): OAuth2 access token
        """
        self.app_key = app_key
        self.app_secret = app_secret
        self.refresh_token = refresh_token
        self.access_token = access_token

        # Initialize the connection
        self.dbx = None
        self._connect()

    def _connect(self):
        """Establish connection to Dropbox API"""
        try:
            if self.access_token:
                self.dbx = dropbox.Dropbox(self.access_token)
            elif self.refresh_token:
                self._refresh_token()
            else:
                return False

            # Verify connection
            self.dbx.users_get_current_account()
            return True
        except (AuthError, ApiError) as e:
            if isinstance(e, AuthError) and self.refresh_token:
                # Token expired, try to refresh
                self._refresh_token()
                return self.dbx is not None
            frappe.log_error(f"Dropbox connection error: {str(e)}")
            return False
        except Exception as e:
            frappe.log_error(f"Dropbox connection error: {str(e)}")
            return False

    def _refresh_token(self):
        """Refresh the access token using the refresh token"""
        try:
            # Create a Dropbox object with refresh token
            self.dbx = dropbox.Dropbox(
                app_key=self.app_key,
                app_secret=self.app_secret,
                oauth2_refresh_token=self.refresh_token,
            )

            # Get current account to verify the token is valid
            self.dbx.users_get_current_account()

            # Set access token (not directly available from the API)
            self.access_token = self.dbx._oauth2_access_token

            return True
        except Exception as e:
            frappe.log_error(f"Dropbox token refresh error: {str(e)}")
            self.dbx = None
            return False

    def validate_folder(self, folder_path):
        """
        Validate if a Dropbox folder exists and is accessible

        Args:
            folder_path (str): Dropbox folder path (e.g., '/MyFolder')

        Returns:
            bool: True if folder exists and is accessible
        """
        try:
            # Ensure folder path starts with /
            if not folder_path.startswith("/"):
                folder_path = "/" + folder_path

            # Try to get folder metadata
            metadata = self.dbx.files_get_metadata(folder_path)

            # Verify it's a folder
            if not isinstance(metadata, FolderMetadata):
                frappe.msgprint(
                    _("The specified Dropbox path is not a folder"), alert=True
                )
                return False

            frappe.msgprint(
                _("Dropbox folder found: {0}").format(folder_path),
                indicator="green",
                alert=True,
            )
            return True
        except ApiError as e:
            if e.error.is_path() and e.error.get_path().is_not_found():
                frappe.throw(_("Dropbox folder not found"))
            else:
                frappe.throw(_("Error accessing Dropbox folder: {0}").format(str(e)))
            return False
        except Exception as e:
            frappe.throw(_("Error validating Dropbox folder: {0}").format(str(e)))
            return False

    def remove_object(self, folder_path, file_path):
        """
        Remove a file from Dropbox

        Args:
            folder_path (str): Base folder path (not used directly, included for API compatibility)
            file_path (str): Full Dropbox file path

        Returns:
            bool: True if file was successfully deleted
        """
        try:
            self.dbx.files_delete_v2(file_path)
            return True
        except Exception as e:
            frappe.log_error(f"Dropbox delete error: {str(e)}")
            return False

    def stat_object(self, folder_path, file_path):
        """
        Get file metadata from Dropbox

        Args:
            folder_path (str): Base folder path (not used directly, included for API compatibility)
            file_path (str): Full Dropbox file path

        Returns:
            dict: File metadata
        """
        try:
            metadata = self.dbx.files_get_metadata(file_path)
            return metadata
        except Exception as e:
            frappe.log_error(f"Dropbox stat error: {str(e)}")
            raise

    def get_object(self, folder_path, file_path, offset=0, length=0):
        """
        Get file content from Dropbox

        Args:
            folder_path (str): Base folder path (not used directly, included for API compatibility)
            file_path (str): Full Dropbox file path
            offset (int): Start byte position (not directly supported by Dropbox)
            length (int): Number of bytes to read (not directly supported by Dropbox)

        Returns:
            BytesIO: File content as a file-like object
        """
        try:
            if offset > 0 or length > 0:
                # Dropbox doesn't support range requests directly
                # We need to download the whole file and then extract the range
                metadata, response = self.dbx.files_download(file_path)
                content = response.content

                if offset > 0:
                    content = content[offset:]
                if length > 0:
                    content = content[:length]

                return io.BytesIO(content)
            else:
                # Download the whole file
                metadata, response = self.dbx.files_download(file_path)
                return io.BytesIO(response.content)
        except Exception as e:
            frappe.log_error(f"Dropbox download error: {str(e)}")
            raise

    def fget_object(self, folder_path, file_path, local_path):
        """
        Download file from Dropbox to a local path

        Args:
            folder_path (str): Base folder path (not used directly, included for API compatibility)
            file_path (str): Full Dropbox file path
            local_path (str): Local file path to save the file

        Returns:
            bool: True if file was successfully downloaded
        """
        try:
            with open(local_path, "wb") as f:
                metadata, response = self.dbx.files_download(file_path)
                f.write(response.content)
            return True
        except Exception as e:
            frappe.log_error(f"Dropbox download to file error: {str(e)}")
            raise

    def put_object(self, folder_path, file_name, data, metadata=None, length=-1):
        """
        Upload file to Dropbox

        Args:
            folder_path (str): Dropbox folder path to upload to
            file_name (str): Name for the uploaded file
            data: File-like object with data to upload
            metadata (dict): Additional metadata (not used for Dropbox)
            length (int): Data size (optional)

        Returns:
            dict: File metadata for the uploaded file
        """
        try:
            # Ensure folder path starts with /
            if not folder_path.startswith("/"):
                folder_path = "/" + folder_path

            # Create full file path
            full_path = os.path.join(folder_path, file_name).replace("\\", "/")
            if not full_path.startswith("/"):
                full_path = "/" + full_path

            # For small files, we can use simple upload
            if (
                length > 0 and length < 150 * 1024 * 1024
            ):  # 150MB is Dropbox's limit for simple uploads
                file_data = data.read()
                result = self.dbx.files_upload(
                    file_data, full_path, mode=dropbox.files.WriteMode.overwrite
                )
                return result

            # For larger files, use chunked upload
            else:
                # If length not provided, determine it
                if length <= 0:
                    data.seek(0, os.SEEK_END)
                    length = data.tell()
                    data.seek(0)

                chunk_size = 4 * 1024 * 1024  # 4MB chunks

                if length <= chunk_size:
                    # Small enough for simple upload
                    file_data = data.read()
                    result = self.dbx.files_upload(
                        file_data, full_path, mode=dropbox.files.WriteMode.overwrite
                    )
                    return result

                # Start upload session
                upload_session_start_result = self.dbx.files_upload_session_start(
                    data.read(chunk_size)
                )
                cursor = dropbox.files.UploadSessionCursor(
                    session_id=upload_session_start_result.session_id, offset=chunk_size
                )

                # Upload chunks
                bytes_uploaded = chunk_size
                while bytes_uploaded < length:
                    remaining = length - bytes_uploaded
                    this_chunk_size = min(chunk_size, remaining)

                    if remaining <= chunk_size:
                        # Final chunk
                        commit = dropbox.files.CommitInfo(
                            path=full_path, mode=dropbox.files.WriteMode.overwrite
                        )
                        result = self.dbx.files_upload_session_finish(
                            data.read(this_chunk_size), cursor, commit
                        )
                        return result
                    else:
                        # More chunks to upload
                        self.dbx.files_upload_session_append_v2(
                            data.read(this_chunk_size), cursor
                        )
                        bytes_uploaded += this_chunk_size
                        cursor.offset = bytes_uploaded

                # Shouldn't reach here, but just in case
                return None

        except Exception as e:
            frappe.log_error(f"Dropbox upload error: {str(e)}")
            raise

    def list_objects(self, folder_path, recursive=True):
        """
        List files in a Dropbox folder

        Args:
            folder_path (str): Dropbox folder path
            recursive (bool): Whether to list files in subfolders

        Returns:
            generator: Generator yielding file metadata objects
        """
        try:
            # Ensure folder path starts with /
            if not folder_path.startswith("/"):
                folder_path = "/" + folder_path

            result = self.dbx.files_list_folder(folder_path, recursive=recursive)

            has_more = True

            while has_more:
                for entry in result.entries:
                    # Adapt Dropbox response to match S3 format
                    if isinstance(entry, FileMetadata):
                        yield {
                            "object_name": entry.path_display,
                            "size": entry.size,
                            "etag": (
                                entry.content_hash
                                if hasattr(entry, "content_hash")
                                else ""
                            ),
                            "last_modified": entry.server_modified,
                            "is_dir": False,
                            "storage_class": "DROPBOX",
                            "metadata": {
                                "id": entry.id,
                                "rev": entry.rev,
                                "path": entry.path_display,
                            },
                        }
                    elif isinstance(entry, FolderMetadata):
                        yield {
                            "object_name": entry.path_display,
                            "size": 0,
                            "etag": "",
                            "last_modified": None,
                            "is_dir": True,
                            "storage_class": "DROPBOX",
                            "metadata": {"id": entry.id, "path": entry.path_display},
                        }

                # Check if there are more entries
                if result.has_more:
                    result = self.dbx.files_list_folder_continue(result.cursor)
                else:
                    has_more = False

        except Exception as e:
            frappe.log_error(f"Dropbox list error: {str(e)}")
            yield None

    def presigned_get_object(self, folder_path, file_path, expires=timedelta(hours=3)):
        """
        Create a temporary shareable link for a Dropbox file

        Args:
            folder_path (str): Base folder path (not used directly, included for API compatibility)
            file_path (str): Full Dropbox file path
            expires (timedelta): How long the link should be valid

        Returns:
            str: Temporary shareable link
        """
        try:
            # Create a shared link with expiry
            settings = dropbox.sharing.SharedLinkSettings(
                expires=datetime.utcnow() + expires if expires else None,
                requested_visibility=dropbox.sharing.RequestedVisibility.public,
            )

            result = self.dbx.sharing_create_shared_link_with_settings(
                file_path, settings=settings
            )

            # Convert to direct download link if needed
            url = result.url
            if url.endswith("dl=0"):
                url = url.replace("dl=0", "dl=1")

            return url
        except ApiError as e:
            # Check if the shared link already exists
            if e.error.is_shared_link_already_exists():
                # Get existing links
                links = self.dbx.sharing_list_shared_links(
                    path=file_path, direct_only=True
                ).links

                if links:
                    url = links[0].url
                    if url.endswith("dl=0"):
                        url = url.replace("dl=0", "dl=1")
                    return url

            frappe.log_error(f"Dropbox presigned URL error: {str(e)}")
            return None
        except Exception as e:
            frappe.log_error(f"Dropbox presigned URL error: {str(e)}")
            return None


class DropboxOAuth2FlowNoRedirect:
    """
    Helper class for OAuth 2.0 authorization flow without redirect
    Used for command-line or script-based authentication
    """

    def __init__(self, app_key, app_secret):
        self.app_key = app_key
        self.app_secret = app_secret

    def start(self):
        """
        Start the authorization flow, return the URL for authorization

        Returns:
            str: URL for user to visit to authorize the app
        """
        auth_flow = dropbox.DropboxOAuth2FlowNoRedirect(self.app_key, self.app_secret)
        return auth_flow.start()

    def finish(self, auth_code):
        """
        Complete the authorization flow with the code provided by the user

        Args:
            auth_code (str): Authorization code from Dropbox

        Returns:
            dict: OAuth tokens and account information
        """
        auth_flow = dropbox.DropboxOAuth2FlowNoRedirect(self.app_key, self.app_secret)

        oauth_result = auth_flow.finish(auth_code)

        return {
            "access_token": oauth_result.access_token,
            "refresh_token": oauth_result.refresh_token,
            "account_id": oauth_result.account_id,
            "uid": oauth_result.account_id,
            "expires_in": oauth_result.expires_in,
        }


# Helper functions for Dropbox OAuth flow


def get_dropbox_auth_flow(redirect_uri=None):
    """
    Create Dropbox OAuth flow object

    Args:
        redirect_uri (str): OAuth redirect URI

    Returns:
        DropboxOAuth2Flow: OAuth flow object
    """
    if not redirect_uri:
        redirect_uri = get_url(
            "/api/method/dfp_external_storage.dropbox_integration.oauth_callback"
        )

    app_key = frappe.conf.get("dropbox_app_key")
    app_secret = frappe.conf.get("dropbox_app_secret")

    if not app_key or not app_secret:
        cached_values = frappe.cache().get_value(
            f"{DFP_DROPBOX_TOKEN_CACHE_PREFIX}app_creds"
        )
        if cached_values:
            app_key = cached_values.get("app_key")
            app_secret = cached_values.get("app_secret")

    return DropboxOAuth2Flow(
        app_key, app_secret, redirect_uri, frappe.session.sid, "token"
    )


def get_dropbox_oauth_url(app_key, app_secret, redirect_uri=None):
    """
    Generate OAuth URL for Dropbox authentication

    Args:
        app_key (str): Dropbox app key
        app_secret (str): Dropbox app secret
        redirect_uri (str): OAuth redirect URI

    Returns:
        str: OAuth URL for user authorization
    """
    if not redirect_uri:
        redirect_uri = get_url(
            "/api/method/dfp_external_storage.dropbox_integration.oauth_callback"
        )

    try:
        # Store credentials in cache for callback
        frappe.cache().set_value(
            f"{DFP_DROPBOX_TOKEN_CACHE_PREFIX}app_creds",
            {"app_key": app_key, "app_secret": app_secret},
        )

        # Generate state parameter to prevent CSRF
        state = frappe.generate_hash(length=32)
        frappe.cache().set_value(
            f"{DFP_DROPBOX_TOKEN_CACHE_PREFIX}state_{frappe.session.user}", state
        )

        # Create auth flow
        auth_flow = DropboxOAuth2Flow(
            app_key, app_secret, redirect_uri, frappe.session.sid, state
        )

        # Get authorization URL
        authorize_url = auth_flow.start()

        return authorize_url
    except Exception as e:
        frappe.log_error(f"Dropbox OAuth URL generation error: {str(e)}")
        frappe.throw(_("Error generating Dropbox OAuth URL: {0}").format(str(e)))


@frappe.whitelist()
def oauth_callback():
    """Handle OAuth callback from Dropbox"""
    try:
        # Get query parameters
        state = frappe.form_dict.get("state")
        error = frappe.form_dict.get("error")
        error_description = frappe.form_dict.get("error_description")
        code = frappe.form_dict.get("code")

        if error:
            frappe.log_error(f"Dropbox OAuth error: {error} - {error_description}")
            frappe.respond_as_web_page(
                _("Dropbox Authentication Failed"),
                _("An error occurred during authentication: {0} - {1}").format(
                    error, error_description
                ),
                indicator_color="red",
            )
            return

        if not code:
            frappe.throw(_("Missing authorization code"))

        # Validate state
        cached_state = frappe.cache().get_value(
            f"{DFP_DROPBOX_TOKEN_CACHE_PREFIX}state_{frappe.session.user}"
        )
        if not cached_state or cached_state != state:
            frappe.throw(_("Invalid state parameter"))

        # Get app credentials from cache
        cached_values = frappe.cache().get_value(
            f"{DFP_DROPBOX_TOKEN_CACHE_PREFIX}app_creds"
        )
        if not cached_values:
            frappe.throw(_("Missing app credentials"))

        app_key = cached_values.get("app_key")
        app_secret = cached_values.get("app_secret")

        # Complete OAuth flow
        redirect_uri = get_url(
            "/api/method/dfp_external_storage.dropbox_integration.oauth_callback"
        )
        auth_flow = DropboxOAuth2Flow(
            app_key, app_secret, redirect_uri, frappe.session.sid, cached_state
        )

        # Exchange code for tokens
        oauth_result = auth_flow.finish({"code": code, "state": state})

        # Store in session for later use
        session_key = (
            f"{DFP_DROPBOX_TOKEN_CACHE_PREFIX}credentials_{frappe.session.user}"
        )
        frappe.cache().set_value(
            session_key,
            {
                "access_token": oauth_result.access_token,
                "refresh_token": oauth_result.refresh_token,
                "account_id": oauth_result.account_id,
                "uid": oauth_result.account_id,
                "app_key": app_key,
                "app_secret": app_secret,
            },
        )

        # Clean up cache
        frappe.cache().delete_value(
            f"{DFP_DROPBOX_TOKEN_CACHE_PREFIX}state_{frappe.session.user}"
        )

        # Redirect to success page or document
        success_url = frappe.cache().get_value(
            f"{DFP_DROPBOX_TOKEN_CACHE_PREFIX}success_url_{frappe.session.user}"
        )
        if success_url:
            frappe.cache().delete_value(
                f"{DFP_DROPBOX_TOKEN_CACHE_PREFIX}success_url_{frappe.session.user}"
            )
            frappe.local.response["type"] = "redirect"
            frappe.local.response["location"] = success_url
        else:
            # Default success message
            frappe.respond_as_web_page(
                _("Dropbox Authentication Successful"),
                _(
                    "You have successfully authenticated with Dropbox. You can close this window and return to the app."
                ),
                indicator_color="green",
            )
    except Exception as e:
        frappe.log_error(f"Dropbox OAuth callback error: {str(e)}")
        frappe.respond_as_web_page(
            _("Dropbox Authentication Failed"),
            _("An error occurred during authentication: {0}").format(str(e)),
            indicator_color="red",
        )


@frappe.whitelist()
def initiate_dropbox_auth(doc_name, app_key, app_secret):
    """
    Initiate Dropbox OAuth flow from the DFP External Storage document

    Args:
        doc_name (str): DFP External Storage document name
        app_key (str): Dropbox app key
        app_secret (str): Dropbox app secret

    Returns:
        dict: Response with auth_url for redirection
    """
    try:
        # Set success URL in cache
        success_url = get_url(f"/desk#Form/DFP External Storage/{doc_name}")
        frappe.cache().set_value(
            f"{DFP_DROPBOX_TOKEN_CACHE_PREFIX}success_url_{frappe.session.user}",
            success_url,
        )

        # Generate OAuth URL
        auth_url = get_dropbox_oauth_url(app_key, app_secret)

        return {"success": True, "auth_url": auth_url}
    except Exception as e:
        frappe.log_error(f"Error initiating Dropbox auth: {str(e)}")
        return {"success": False, "error": str(e)}


@frappe.whitelist()
def get_auth_credentials():
    """
    Get Dropbox auth credentials from session
    Returns credentials if they exist, None otherwise
    """
    session_key = f"{DFP_DROPBOX_TOKEN_CACHE_PREFIX}credentials_{frappe.session.user}"
    return frappe.cache().get_value(session_key)


@frappe.whitelist()
def test_dropbox_connection(doc_name=None, connection_data=None):
    """
    Test the connection to Dropbox

    Args:
        doc_name (str): DFP External Storage document name
        connection_data (dict): Connection data with app_key, app_secret, refresh_token, folder_path

    Returns:
        dict: Response with success status and message
    """
    try:
        if doc_name and not connection_data:
            # If we have a document name but no connection data, load it from the document
            doc = frappe.get_doc("DFP External Storage", doc_name)

            # Test the connection using document's stored credentials
            app_key = doc.dropbox_app_key
            app_secret = frappe.utils.password.get_decrypted_password(
                "DFP External Storage", doc_name, "dropbox_app_secret"
            )
            refresh_token = frappe.utils.password.get_decrypted_password(
                "DFP External Storage", doc_name, "dropbox_refresh_token"
            )
            folder_path = doc.dropbox_folder_path

        elif connection_data:
            # If connection data is provided, use it directly
            if isinstance(connection_data, str):
                connection_data = json.loads(connection_data)

            app_key = connection_data.get("app_key")
            app_secret = connection_data.get("app_secret")
            refresh_token = connection_data.get("refresh_token")
            folder_path = connection_data.get("folder_path")

        else:
            return {"success": False, "message": "No connection data provided"}

        # Validate required fields
        if not all([app_key, app_secret, refresh_token, folder_path]):
            missing = []
            if not app_key:
                missing.append("App Key")
            if not app_secret:
                missing.append("App Secret")
            if not refresh_token:
                missing.append("Refresh Token")
            if not folder_path:
                missing.append("Folder Path")

            return {
                "success": False,
                "message": f"Missing required fields: {', '.join(missing)}",
            }

        # Create connection and test
        connection = DropboxConnection(
            app_key=app_key, app_secret=app_secret, refresh_token=refresh_token
        )

        if not connection.dbx:
            return {"success": False, "message": "Failed to connect to Dropbox API"}

        # Test folder access
        folder_exists = connection.validate_folder(folder_path)

        if folder_exists:
            return {
                "success": True,
                "message": f"Successfully connected to Dropbox and verified folder access",
            }
        else:
            return {
                "success": False,
                "message": "Connected to Dropbox but folder not found or not accessible",
            }

    except Exception as e:
        frappe.log_error(f"Error testing Dropbox connection: {str(e)}")
        return {"success": False, "message": f"Error testing connection: {str(e)}"}


class DFPExternalStorageDropboxFile:
    """Dropbox implementation for DFP External Storage File"""

    def __init__(self, file_doc):
        self.file_doc = file_doc
        self.file_name = file_doc.file_name
        self.content_hash = file_doc.content_hash
        self.storage_doc = file_doc.dfp_external_storage_doc
        self.client = self._get_dropbox_client()

    def _get_dropbox_client(self):
        """Initialize Dropbox client"""
        try:
            storage_doc = self.storage_doc
            app_key = storage_doc.dropbox_app_key
            app_secret = frappe.utils.password.get_decrypted_password(
                "DFP External Storage", storage_doc.name, "dropbox_app_secret"
            )
            refresh_token = frappe.utils.password.get_decrypted_password(
                "DFP External Storage", storage_doc.name, "dropbox_refresh_token"
            )

            return DropboxConnection(
                app_key=app_key, app_secret=app_secret, refresh_token=refresh_token
            )
        except Exception as e:
            frappe.log_error(f"Failed to initialize Dropbox client: {str(e)}")
            return None

    def upload_file(self, local_file=None):
        """
        Upload file to Dropbox

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

            # Determine folder path
            folder_path = self.storage_doc.dropbox_folder_path
            if not folder_path.startswith("/"):
                folder_path = "/" + folder_path

            # Create destination path in Dropbox
            dropbox_path = f"{folder_path}/{self.file_name}"

            # Upload file
            with open(local_file, "rb") as f:
                # Upload to Dropbox
                result = self.client.put_object(
                    folder_path=folder_path, file_name=self.file_name, data=f
                )

                if not result:
                    raise Exception("Upload failed - no result returned")

                # Update file document with Dropbox file path
                self.file_doc.dfp_external_storage_s3_key = result.path_display
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
            error_msg = _("Error saving file to Dropbox: {0}").format(str(e))
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
        """Delete file from Dropbox"""
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
            # Other files are using this Dropbox file, don't delete
            return False

        # Delete from Dropbox
        try:
            self.client.remove_object(
                folder_path=None,  # Not needed for Dropbox
                file_path=self.file_doc.dfp_external_storage_s3_key,
            )
            return True
        except Exception as e:
            error_msg = _("Error deleting file from Dropbox.")
            frappe.log_error(f"{error_msg}: {self.file_name}", message=str(e))
            frappe.throw(f"{error_msg} {str(e)}")
            return False

    def download_file(self):
        """Download file from Dropbox"""
        try:
            file_content = self.client.get_object(
                folder_path=None,  # Not needed for Dropbox
                file_path=self.file_doc.dfp_external_storage_s3_key,
            )
            return file_content.read()
        except Exception as e:
            error_msg = _("Error downloading file from Dropbox")
            frappe.log_error(title=f"{error_msg}: {self.file_name}")
            frappe.throw(error_msg)
            return b""

    def stream_file(self):
        """Stream file from Dropbox"""
        try:
            from werkzeug.wsgi import wrap_file

            file_content = self.client.get_object(
                folder_path=None,  # Not needed for Dropbox
                file_path=self.file_doc.dfp_external_storage_s3_key,
            )

            # Wrap the file content for streaming
            return wrap_file(
                environ=frappe.local.request.environ,
                file=file_content,
                buffer_size=self.storage_doc.setting_stream_buffer_size,
            )
        except Exception as e:
            frappe.log_error(f"Dropbox streaming error: {str(e)}")
            frappe.throw(_("Failed to stream file from Dropbox"))

    def download_to_local_and_remove_remote(self):
        """Download file from Dropbox and remove the remote file"""
        try:
            # Get file content
            file_content = self.client.get_object(
                folder_path=None,  # Not needed for Dropbox
                file_path=self.file_doc.dfp_external_storage_s3_key,
            )

            # Save content
            self.file_doc._content = file_content.read()

            # Clear storage info
            file_path = self.file_doc.dfp_external_storage_s3_key
            self.file_doc.dfp_external_storage_s3_key = ""
            self.file_doc.dfp_external_storage = ""

            # Save to filesystem
            self.file_doc.save_file_on_filesystem()

            # Delete from Dropbox
            self.client.remove_object(
                folder_path=None, file_path=file_path  # Not needed for Dropbox
            )

            return True
        except Exception as e:
            error_msg = _("Error downloading and removing file from Dropbox.")
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
                folder_path=None,  # Not needed for Dropbox
                file_path=self.file_doc.dfp_external_storage_s3_key,
                expires=self.storage_doc.setting_presigned_url_expiration,
            )
        except Exception as e:
            frappe.log_error(f"Error generating Dropbox presigned URL: {str(e)}")
            return None
