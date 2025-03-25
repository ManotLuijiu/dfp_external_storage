# Microsoft OneDrive Support for DFP External Storage

DFP External Storage now supports Microsoft OneDrive as a storage backend! This feature allows you to store your Frappe/ERPNext files in OneDrive, alongside the existing S3-compatible and Google Drive storage options.

## Features

- Store Frappe files in OneDrive folders
- Automatic OAuth 2.0 authentication flow with Microsoft Graph API
- Support for private and public files
- Streaming large files directly from OneDrive
- Presigned URL support for direct file access
- Folder-based storage configuration
- Support for both personal and organizational accounts
- Support for multi-tenant applications

## Setup Instructions

### 1. Install Dependencies

Install the required Microsoft API libraries:

```bash
pip install msal requests
```

Or use the provided installation helper:

```bash
bench --site your-site.com execute dfp_external_storage/install_onedrive.py
```

### 2. Set Up Microsoft Azure App Registration

1. Create a new App Registration in the Azure Portal
2. Configure the appropriate permissions (Files.ReadWrite.All, offline_access)
3. Set up the redirect URI for authentication
4. Create a client secret

See the [detailed OneDrive Integration Guide](docs/onedrive_integration.md) for step-by-step instructions.

### 3. Configure in Frappe

1. Go to DFP External Storage list and create a new entry
2. Select "OneDrive" as the storage type
3. Enter your Azure App details (Client ID, Client Secret, Tenant ID)
4. Save the document
5. Click "Authenticate with OneDrive" and complete the OAuth flow
6. Find a OneDrive folder ID and enter it
7. Save the document again

## Usage

Once configured, the OneDrive storage works just like the other storage options:

1. Select folders to use this storage
2. Upload files normally through Frappe
3. Files will be stored in your OneDrive folder

You can also enable presigned URLs for direct file access, set up caching, and configure other advanced options.

## Troubleshooting

If you encounter issues:

1. Check the Frappe error logs for detailed error messages
2. Verify your Azure App configuration
3. Make sure your OAuth redirect URIs are correctly configured
4. Check that your OneDrive folder exists and is accessible
5. Try re-authenticating if your tokens have expired

For more detailed instructions, see the full [OneDrive Integration Guide](docs/onedrive_integration.md).