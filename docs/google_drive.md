# Google Drive Support for DFP External Storage

DFP External Storage now supports Google Drive as a storage backend! This feature allows you to store your Frappe/ERPNext files in Google Drive, alongside the existing S3-compatible storage options.

## Features

- Store Frappe files in Google Drive folders
- Automatic OAuth 2.0 authentication flow
- Support for private and public files
- Streaming large files directly from Google Drive
- Presigned URL support for direct file access
- Folder-based storage configuration
- Extensive integration with existing DFP External Storage features

## Setup Instructions

### 1. Install Dependencies

Install the required Google API libraries:

```bash
pip install google-api-python-client google-auth google-auth-oauthlib google-auth-httplib2
```

Or use the provided installation helper:

```bash
bench --site your-site.com execute dfp_external_storage/install_gdrive.py
```

### 2. Set Up Google Cloud Project

1. Create a new project in the [Google Cloud Console](https://console.cloud.google.com/)
2. Enable the Google Drive API for your project
3. Create OAuth 2.0 credentials:
   - Application type: Web application
   - Authorized JavaScript origins: Your site URL (e.g., https://your-site.com)
   - Authorized redirect URIs: Your callback URL (e.g., https://your-site.com/api/method/dfp_external_storage.gdrive_integration.oauth_callback)

### 3. Configure in Frappe

1. Go to DFP External Storage list and create a new entry
2. Select "Google Drive" as the storage type
3. Enter your Google Client ID and Client Secret
4. Save the document
5. Click "Authenticate with Google Drive" and complete the OAuth flow
6. Find a Google Drive folder ID (from the folder's URL) and enter it
7. Save the document again

## Usage

Once configured, the Google Drive storage works just like the S3 options:

1. Select folders to use this storage
2. Upload files normally through Frappe
3. Files will be stored in your Google Drive folder

You can also enable presigned URLs for direct file access, set up caching, and configure other advanced options just like with S3 storage.

## Troubleshooting

If you encounter issues:

1. Check the Frappe error logs for detailed error messages
2. Verify your Google Cloud project has the Drive API enabled
3. Make sure your OAuth redirect URIs are correctly configured
4. Check that your Google Drive folder exists and is accessible
5. Try re-authenticating if your refresh token has expired

For more detailed instructions, see the full [Google Drive Integration Guide](integration-guide.md).