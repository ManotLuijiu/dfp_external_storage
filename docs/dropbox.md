# Dropbox Support for DFP External Storage

DFP External Storage now supports Dropbox as a storage backend! This feature allows you to store your Frappe/ERPNext files in Dropbox, alongside the existing S3-compatible, Google Drive, and OneDrive storage options.

## Features

- Store Frappe files in Dropbox folders
- Automatic OAuth 2.0 authentication flow with Dropbox API
- Support for private and public files
- Streaming large files directly from Dropbox
- Presigned URL support for direct file access
- Folder-based storage configuration
- Support for chunked uploads for large files
- Choice between App folder or Full Dropbox access

## Setup Instructions

### 1. Install Dependencies

Install the required Dropbox Python library:

```bash
pip install dropbox>=11.36.0
```

Or use the provided installation helper:

```bash
bench --site your-site.com execute dfp_external_storage/install_dropbox.py
```

### 2. Set Up Dropbox App

1. Create a new app in the [Dropbox App Console](https://www.dropbox.com/developers/apps)
2. Choose between "App folder" or "Full Dropbox" access
3. Configure the appropriate permissions
4. Set up the redirect URI for authentication

See the [detailed Dropbox Integration Guide](docs/dropbox_integration.md) for step-by-step instructions.

### 3. Configure in Frappe

1. Go to DFP External Storage list and create a new entry
2. Select "Dropbox" as the storage type
3. Enter your Dropbox App Key and App Secret
4. Save the document
5. Click "Authenticate with Dropbox" and complete the OAuth flow
6. Specify a Dropbox folder path (must start with a slash, e.g., "/MyFolder")
7. Save the document again

## Usage

Once configured, the Dropbox storage works just like the other storage options:

1. Select folders to use this storage
2. Upload files normally through Frappe
3. Files will be stored in your Dropbox folder

You can also enable presigned URLs for direct file access, set up caching, and configure other advanced options.

## Benefits of Using Dropbox

- Generous free storage tier (2GB with basic account)
- Easy to access files from multiple devices and platforms
- Excellent sharing and collaboration features
- Simple, user-friendly interface for file management
- Strong versioning and recovery options

## Troubleshooting

If you encounter issues:

1. Check the Frappe error logs for detailed error messages
2. Verify your Dropbox App configuration
3. Make sure your OAuth redirect URIs are correctly configured
4. Check that your Dropbox folder path is correctly formatted
5. Try re-authenticating if your tokens have expired

For more detailed instructions, see the full [Dropbox Integration Guide](docs/dropbox_integration.md).
