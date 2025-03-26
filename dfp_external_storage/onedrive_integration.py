"""
OneDrive Integration for DFP External Storage

This module adds Microsoft OneDrive support to the DFP External Storage app.
It requires the following dependencies:
- msal (Microsoft Authentication Library)
- requests
"""

import io
import os
import re
import json
import frappe
import requests
import time
from frappe import _
from frappe.utils import get_request_site_address, get_url
from datetime import datetime, timedelta
from functools import wraps
import msal

# OneDrive API scopes
SCOPES = ["Files.ReadWrite.All", "offline_access"]

# Cache key prefix for OneDrive tokens
DFP_ONEDRIVE_TOKEN_CACHE_PREFIX = "dfp_onedrive_token:"

# Microsoft Graph API endpoint
GRAPH_API_ENDPOINT = "https://graph.microsoft.com/v1.0"


def retry_on_token_refresh(max_retries=2):
    """Decorator to retry API calls when token refresh is needed"""

    def decorator(func):
        @wraps(func)
        def wrapper(self, *args, **kwargs):
            retries = 0
            while retries < max_retries:
                try:
                    return func(self, *args, **kwargs)
                except requests.HTTPError as e:
                    if e.response.status_code == 401 and retries < max_retries - 1:
                        # Token expired, refresh it
                        self._refresh_token()
                        retries += 1
                    else:
                        raise

        return wrapper

    return decorator


class OneDriveConnection:
    """OneDrive connection handler for DFP External Storage"""

    def __init__(
        self, client_id, client_secret, tenant, refresh_token=None, access_token=None
    ):
        """
        Initialize OneDrive connection

        Args:
            client_id (str): Microsoft application client ID
            client_secret (str): Microsoft application client secret
            tenant (str): Microsoft tenant ID (or 'common' for multi-tenant apps)
            refresh_token (str): OAuth2 refresh token
            access_token (str): OAuth2 access token
        """
        self.client_id = client_id
        self.client_secret = client_secret
        self.tenant = tenant or "common"
        self.refresh_token = refresh_token
        self.access_token = access_token
        self.token_expiry = None

        # Initialize the connection
        self._app = None
        self._connect()

    def _connect(self):
        """Establish connection to Microsoft Graph API"""
        try:
            # Initialize MSAL app
            authority = f"https://login.microsoftonline.com/{self.tenant}"
            self._app = msal.ConfidentialClientApplication(
                client_id=self.client_id,
                client_credential=self.client_secret,
                authority=authority,
            )

            # If we have a refresh token but no access token, refresh it
            if self.refresh_token and not self.access_token:
                self._refresh_token()

            return True
        except Exception as e:
            frappe.log_error(f"OneDrive connection error: {str(e)}")
            return False

    def _refresh_token(self):
        """Refresh the access token using the refresh token"""
        try:
            if not self._app:
                self._connect()

            result = self._app.acquire_token_by_refresh_token(
                self.refresh_token, scopes=SCOPES
            )

            if "error" in result:
                frappe.log_error(
                    f"OneDrive token refresh error: {result.get('error_description')}"
                )
                return False

            self.access_token = result.get("access_token")
            # Update refresh token if provided
            if "refresh_token" in result:
                self.refresh_token = result.get("refresh_token")

            # Set expiry time
            expires_in = result.get("expires_in", 3600)
            self.token_expiry = datetime.now() + timedelta(seconds=expires_in)

            return True
        except Exception as e:
            frappe.log_error(f"OneDrive token refresh error: {str(e)}")
            return False

    def _get_headers(self):
        """Get request headers with authentication"""
        if not self.access_token:
            self._refresh_token()

        return {
            "Authorization": f"Bearer {self.access_token}",
            "Content-Type": "application/json",
        }

    def _make_request(
        self, method, endpoint, data=None, params=None, headers=None, stream=False
    ):
        """Make a request to Microsoft Graph API"""
        try:
            url = f"{GRAPH_API_ENDPOINT}{endpoint}"
            request_headers = self._get_headers()

            if headers:
                request_headers.update(headers)

            response = requests.request(
                method=method,
                url=url,
                json=data,
                params=params,
                headers=request_headers,
                stream=stream,
            )

            response.raise_for_status()
            return response
        except requests.HTTPError as e:
            if e.response.status_code == 401:
                # Token expired, refresh and retry
                self._refresh_token()
                request_headers = self._get_headers()
                if headers:
                    request_headers.update(headers)

                response = requests.request(
                    method=method,
                    url=url,
                    json=data,
                    params=params,
                    headers=request_headers,
                    stream=stream,
                )
                response.raise_for_status()
                return response
            else:
                frappe.log_error(f"OneDrive API error: {str(e)}")
                raise

    def validate_folder(self, folder_id):
        """
        Validate if a OneDrive folder exists and is accessible

        Args:
            folder_id (str): OneDrive folder ID

        Returns:
            bool: True if folder exists and is accessible
        """
        try:
            # Try to get folder metadata
            response = self._make_request(
                method="GET", endpoint=f"/drive/items/{folder_id}"
            )

            folder = response.json()

            # Verify it's a folder
            if folder.get("folder") is None:
                frappe.msgprint(
                    _("The specified OneDrive ID is not a folder"), alert=True
                )
                return False

            frappe.msgprint(
                _("OneDrive folder found: {0}").format(folder.get("name")),
                indicator="green",
                alert=True,
            )
            return True
        except requests.HTTPError as e:
            if e.response.status_code == 404:
                frappe.throw(_("OneDrive folder not found"))
            else:
                frappe.throw(_("Error accessing OneDrive folder: {0}").format(str(e)))
            return False
        except Exception as e:
            frappe.throw(_("Error validating OneDrive folder: {0}").format(str(e)))
            return False

    @retry_on_token_refresh()
    def remove_object(self, folder_id, file_id):
        """
        Remove a file from OneDrive

        Args:
            folder_id (str): Not used for OneDrive (included for API compatibility)
            file_id (str): OneDrive file ID

        Returns:
            bool: True if file was successfully deleted
        """
        try:
            self._make_request(method="DELETE", endpoint=f"/drive/items/{file_id}")
            return True
        except Exception as e:
            frappe.log_error(f"OneDrive delete error: {str(e)}")
            return False

    @retry_on_token_refresh()
    def stat_object(self, folder_id, file_id):
        """
        Get file metadata from OneDrive

        Args:
            folder_id (str): Not used for OneDrive (included for API compatibility)
            file_id (str): OneDrive file ID

        Returns:
            dict: File metadata
        """
        try:
            response = self._make_request(
                method="GET", endpoint=f"/drive/items/{file_id}"
            )
            return response.json()
        except Exception as e:
            frappe.log_error(f"OneDrive stat error: {str(e)}")
            raise

    @retry_on_token_refresh()
    def get_object(self, folder_id, file_id, offset=0, length=0):
        """
        Get file content from OneDrive

        Args:
            folder_id (str): Not used for OneDrive (included for API compatibility)
            file_id (str): OneDrive file ID
            offset (int): Start byte position (not directly supported by OneDrive)
            length (int): Number of bytes to read (not directly supported by OneDrive)

        Returns:
            BytesIO: File content as a file-like object
        """
        try:
            headers = {}
            # Handle range request if offset or length specified
            if offset > 0 or length > 0:
                range_end = "" if length <= 0 else str(offset + length - 1)
                headers["Range"] = f"bytes={offset}-{range_end}"

            # Get download URL
            response = self._make_request(
                method="GET",
                endpoint=f"/drive/items/{file_id}/content",
                headers=headers,
                stream=True,
            )

            # Stream content to BytesIO
            content = io.BytesIO()
            for chunk in response.iter_content(chunk_size=8192):
                if chunk:
                    content.write(chunk)

            # Reset position to beginning
            content.seek(0)
            return content
        except Exception as e:
            frappe.log_error(f"OneDrive download error: {str(e)}")
            raise

    @retry_on_token_refresh()
    def fget_object(self, folder_id, file_id, file_path):
        """
        Download file from OneDrive to a local path

        Args:
            folder_id (str): Not used for OneDrive (included for API compatibility)
            file_id (str): OneDrive file ID
            file_path (str): Local file path to save the file

        Returns:
            bool: True if file was successfully downloaded
        """
        try:
            response = self._make_request(
                method="GET", endpoint=f"/drive/items/{file_id}/content", stream=True
            )

            with open(file_path, "wb") as f:
                for chunk in response.iter_content(chunk_size=8192):
                    if chunk:
                        f.write(chunk)
            return True
        except Exception as e:
            frappe.log_error(f"OneDrive download to file error: {str(e)}")
            raise

    @retry_on_token_refresh()
    def put_object(self, folder_id, file_name, data, metadata=None, length=-1):
        """
        Upload file to OneDrive

        Args:
            folder_id (str): OneDrive folder ID to upload to
            file_name (str): Name for the uploaded file
            data: File-like object with data to upload
            metadata (dict): Additional metadata (not used for OneDrive)
            length (int): Data size (optional)

        Returns:
            dict: File metadata for the uploaded file
        """
        try:
            # For small files (< 4MB), we can use simple upload
            if length > 0 and length < 4 * 1024 * 1024:
                return self._simple_upload(folder_id, file_name, data)

            # For larger files, use resumable upload
            return self._resumable_upload(folder_id, file_name, data, length)
        except Exception as e:
            frappe.log_error(f"OneDrive upload error: {str(e)}")
            raise

    def _simple_upload(self, folder_id, file_name, data):
        """Simple upload for small files (<4MB)"""
        # Create upload URL
        url = f"{GRAPH_API_ENDPOINT}/drive/items/{folder_id}:/{file_name}:/content"

        # Read data into memory
        file_content = data.read()

        # Upload file
        headers = self._get_headers()
        headers.pop("Content-Type", None)  # Let requests set the content type

        response = requests.put(url=url, data=file_content, headers=headers)
        response.raise_for_status()

        return response.json()

    def _resumable_upload(self, folder_id, file_name, data, length):
        """Resumable upload for larger files"""
        # Create upload session
        response = self._make_request(
            method="POST",
            endpoint=f"/drive/items/{folder_id}:/{file_name}:/createUploadSession",
            data={"item": {"@microsoft.graph.conflictBehavior": "replace"}},
        )

        upload_url = response.json().get("uploadUrl")
        if not upload_url:
            raise Exception("Failed to create upload session")

        # Determine file size if not provided
        if length <= 0:
            data.seek(0, os.SEEK_END)
            length = data.tell()
            data.seek(0)

        # Upload file in chunks
        chunk_size = 3 * 1024 * 1024  # 3MB chunks
        bytes_remaining = length
        next_range_start = 0

        while bytes_remaining > 0:
            current_chunk_size = min(chunk_size, bytes_remaining)
            chunk_data = data.read(current_chunk_size)

            start = next_range_start
            end = start + len(chunk_data) - 1
            content_range = f"bytes {start}-{end}/{length}"

            # Upload chunk
            headers = {
                "Content-Length": str(len(chunk_data)),
                "Content-Range": content_range,
            }

            upload_response = requests.put(
                url=upload_url, data=chunk_data, headers=headers
            )

            if upload_response.status_code in (200, 201):
                # Upload complete
                return upload_response.json()
            elif upload_response.status_code == 202:
                # More chunks to upload
                next_range_start = (
                    upload_response.json().get("nextExpectedRanges")[0].split("-")[0]
                )
                next_range_start = int(next_range_start)
                bytes_remaining = length - next_range_start
            else:
                upload_response.raise_for_status()

    @retry_on_token_refresh()
    def list_objects(self, folder_id, recursive=True):
        """
        List files in a OneDrive folder

        Args:
            folder_id (str): OneDrive folder ID
            recursive (bool): Whether to list files in subfolders

        Returns:
            list: List of file metadata objects
        """
        try:
            # Get items in folder
            items = []
            next_link = f"/drive/items/{folder_id}/children"

            while next_link:
                response = self._make_request(method="GET", endpoint=next_link)

                data = response.json()
                for item in data.get("value", []):
                    # Adapt OneDrive response to match S3 format
                    is_folder = item.get("folder") is not None

                    yield {
                        "object_name": item.get("name"),
                        "size": item.get("size", 0),
                        "etag": item.get("eTag", ""),
                        "last_modified": item.get("lastModifiedDateTime"),
                        "is_dir": is_folder,
                        "storage_class": "ONEDRIVE",
                        "metadata": {
                            "id": item.get("id"),
                            "mime_type": (
                                item.get("file", {}).get("mimeType")
                                if not is_folder
                                else "folder"
                            ),
                        },
                    }

                    # If recursive and item is a folder, list its contents too
                    if recursive and is_folder:
                        subfolder_id = item.get("id")
                        try:
                            yield from self.list_objects(subfolder_id, recursive)
                        except Exception as e:
                            frappe.log_error(
                                f"Error listing subfolder {subfolder_id}: {str(e)}"
                            )

                # Check if there are more pages
                next_link = data.get("@odata.nextLink")
                if next_link:
                    # Extract relative path from URL
                    next_link = next_link.replace(GRAPH_API_ENDPOINT, "")
                else:
                    break

        except Exception as e:
            frappe.log_error(f"OneDrive list error: {str(e)}")
            yield None

    @retry_on_token_refresh()
    def presigned_get_object(self, folder_id, file_id, expires=timedelta(hours=3)):
        """
        Create a temporary shareable link for a OneDrive file

        Args:
            folder_id (str): Not used for OneDrive (included for API compatibility)
            file_id (str): OneDrive file ID
            expires (timedelta): How long the link should be valid

        Returns:
            str: Temporary shareable link
        """
        try:
            # Create a sharing link
            expiration_datetime = datetime.now() + expires
            response = self._make_request(
                method="POST",
                endpoint=f"/drive/items/{file_id}/createLink",
                data={
                    "type": "view",
                    "scope": "anonymous",
                    "expirationDateTime": expiration_datetime.isoformat(),
                },
            )

            # Return the shareable link
            return response.json().get("link", {}).get("webUrl")
        except Exception as e:
            frappe.log_error(f"OneDrive presigned URL error: {str(e)}")
            return None


# Helper functions for OneDrive OAuth flow


def get_onedrive_oauth_url(client_id, tenant="common", redirect_uri=None):
    """
    Generate OAuth URL for OneDrive authentication

    Args:
        client_id (str): Microsoft application client ID
        tenant (str): Microsoft tenant ID
        redirect_uri (str): OAuth redirect URI

    Returns:
        str: OAuth URL for user authorization
    """
    if not redirect_uri:
        redirect_uri = get_url(
            "/api/method/dfp_external_storage.onedrive_integration.oauth_callback"
        )

    try:
        # Store state in cache for callback validation
        state = frappe.generate_hash(length=32)
        cache_key = f"{DFP_ONEDRIVE_TOKEN_CACHE_PREFIX}state_{frappe.session.user}"
        frappe.cache().set_value(cache_key, state, expires_in_sec=3600)

        # Create auth URL
        params = {
            "client_id": client_id,
            "response_type": "code",
            "redirect_uri": redirect_uri,
            "scope": " ".join(SCOPES),
            "state": state,
            "response_mode": "query",
        }

        query_string = "&".join(
            [f"{k}={requests.utils.quote(str(v))}" for k, v in params.items()]
        )
        auth_url = f"https://login.microsoftonline.com/{tenant}/oauth2/v2.0/authorize?{query_string}"

        return auth_url
    except Exception as e:
        frappe.log_error(f"OneDrive OAuth URL generation error: {str(e)}")
        frappe.throw(_("Error generating OneDrive OAuth URL: {0}").format(str(e)))


@frappe.whitelist()
def oauth_callback():
    """Handle OAuth callback from Microsoft"""
    try:
        # Get authorization code and state from request
        code = frappe.request.args.get("code")
        state = frappe.request.args.get("state")
        error = frappe.request.args.get("error")
        error_description = frappe.request.args.get("error_description")

        if error:
            frappe.log_error(f"OneDrive OAuth error: {error} - {error_description}")
            frappe.respond_as_web_page(
                _("OneDrive Authentication Failed"),
                _("An error occurred during authentication: {0} - {1}").format(
                    error, error_description
                ),
                indicator_color="red",
            )
            return

        if not code:
            frappe.throw(_("Missing authorization code"))

        # Validate state to prevent CSRF
        cache_key = f"{DFP_ONEDRIVE_TOKEN_CACHE_PREFIX}state_{frappe.session.user}"
        stored_state = frappe.cache().get_value(cache_key)
        if not stored_state or stored_state != state:
            frappe.throw(_("Invalid authentication state"))

        # Get client details from session
        session_key = (
            f"{DFP_ONEDRIVE_TOKEN_CACHE_PREFIX}client_details_{frappe.session.user}"
        )
        client_details = frappe.cache().get_value(session_key)
        if not client_details:
            frappe.throw(_("Authentication session expired"))

        # Exchange code for tokens
        redirect_uri = get_url(
            "/api/method/dfp_external_storage.onedrive_integration.oauth_callback"
        )
        token_endpoint = f"https://login.microsoftonline.com/{client_details.get('tenant', 'common')}/oauth2/v2.0/token"

        token_data = {
            "client_id": client_details.get("client_id"),
            "client_secret": client_details.get("client_secret"),
            "code": code,
            "redirect_uri": redirect_uri,
            "grant_type": "authorization_code",
        }

        response = requests.post(token_endpoint, data=token_data)
        response.raise_for_status()

        tokens = response.json()

        # Store tokens in session for later use
        credentials_key = (
            f"{DFP_ONEDRIVE_TOKEN_CACHE_PREFIX}credentials_{frappe.session.user}"
        )
        frappe.cache().set_value(
            credentials_key,
            {
                "access_token": tokens.get("access_token"),
                "refresh_token": tokens.get("refresh_token"),
                "expires_in": tokens.get("expires_in"),
                "client_id": client_details.get("client_id"),
                "client_secret": client_details.get("client_secret"),
                "tenant": client_details.get("tenant", "common"),
            },
        )

        # Clean up cache
        frappe.cache().delete_value(cache_key)
        frappe.cache().delete_value(session_key)

        # Redirect to success page or document
        success_url = frappe.cache().get_value(
            f"{DFP_ONEDRIVE_TOKEN_CACHE_PREFIX}success_url_{frappe.session.user}"
        )
        if success_url:
            frappe.cache().delete_value(
                f"{DFP_ONEDRIVE_TOKEN_CACHE_PREFIX}success_url_{frappe.session.user}"
            )
            frappe.local.response["type"] = "redirect"
            frappe.local.response["location"] = success_url
        else:
            # Default success message
            frappe.respond_as_web_page(
                _("OneDrive Authentication Successful"),
                _(
                    "You have successfully authenticated with OneDrive. You can close this window and return to the app."
                ),
                indicator_color="green",
            )
    except Exception as e:
        frappe.log_error(f"OneDrive OAuth callback error: {str(e)}")
        frappe.respond_as_web_page(
            _("OneDrive Authentication Failed"),
            _("An error occurred during authentication: {0}").format(str(e)),
            indicator_color="red",
        )


@frappe.whitelist()
def initiate_onedrive_auth(doc_name, client_id, client_secret, tenant="common"):
    """
    Initiate OneDrive OAuth flow from the DFP External Storage document

    Args:
        doc_name (str): DFP External Storage document name
        client_id (str): Microsoft application client ID
        client_secret (str): Microsoft application client secret
        tenant (str): Microsoft tenant ID

    Returns:
        dict: Response with auth_url for redirection
    """
    try:
        # Set success URL in cache
        success_url = get_url(f"/desk#Form/DFP External Storage/{doc_name}")
        frappe.cache().set_value(
            f"{DFP_ONEDRIVE_TOKEN_CACHE_PREFIX}success_url_{frappe.session.user}",
            success_url,
        )

        # Store client details in cache for callback
        client_details_key = (
            f"{DFP_ONEDRIVE_TOKEN_CACHE_PREFIX}client_details_{frappe.session.user}"
        )
        frappe.cache().set_value(
            client_details_key,
            {"client_id": client_id, "client_secret": client_secret, "tenant": tenant},
        )

        # Generate OAuth URL
        auth_url = get_onedrive_oauth_url(client_id, tenant)

        return {"success": True, "auth_url": auth_url}
    except Exception as e:
        frappe.log_error(f"Error initiating OneDrive auth: {str(e)}")
        return {"success": False, "error": str(e)}


@frappe.whitelist()
def get_auth_credentials():
    """
    Get OneDrive auth credentials from session
    Returns credentials if they exist, None otherwise
    """
    session_key = f"{DFP_ONEDRIVE_TOKEN_CACHE_PREFIX}credentials_{frappe.session.user}"
    return frappe.cache().get_value(session_key)


@frappe.whitelist()
def test_onedrive_connection(doc_name=None, connection_data=None):
    """
    Test the connection to OneDrive

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
            client_id = doc.onedrive_client_id
            client_secret = frappe.utils.password.get_decrypted_password(
                "DFP External Storage", doc_name, "onedrive_client_secret"
            )
            refresh_token = frappe.utils.password.get_decrypted_password(
                "DFP External Storage", doc_name, "onedrive_refresh_token"
            )
            tenant = doc.onedrive_tenant or "common"
            folder_id = doc.onedrive_folder_id

        elif connection_data:
            # If connection data is provided, use it directly
            if isinstance(connection_data, str):
                connection_data = json.loads(connection_data)

            client_id = connection_data.get("client_id")
            client_secret = connection_data.get("client_secret")
            refresh_token = connection_data.get("refresh_token")
            tenant = connection_data.get("tenant", "common")
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
        connection = OneDriveConnection(
            client_id=client_id,
            client_secret=client_secret,
            tenant=tenant,
            refresh_token=refresh_token,
        )

        if not connection.access_token:
            return {"success": False, "message": "Failed to connect to OneDrive API"}

        # Test folder access
        folder_exists = connection.validate_folder(folder_id)

        if folder_exists:
            return {
                "success": True,
                "message": f"Successfully connected to OneDrive and verified folder access",
            }
        else:
            return {
                "success": False,
                "message": "Connected to OneDrive but folder not found or not accessible",
            }

    except Exception as e:
        frappe.log_error(f"Error testing OneDrive connection: {str(e)}")
        return {"success": False, "message": f"Error testing connection: {str(e)}"}
