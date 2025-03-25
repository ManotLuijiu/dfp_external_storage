# Dropbox Integration Guide for DFP External Storage

This guide provides step-by-step instructions for integrating Dropbox support into the DFP External Storage app.

## 1. Install Required Dependencies

First, install the required Python package for Dropbox API access:

```bash
pip install dropbox>=11.36.0
```

Or use the provided installation helper:

```bash
bench --site your-site.com execute dfp_external_storage/install_dropbox.py
```

## 2. Set Up Dropbox App

1. Go to the [Dropbox App Console](https://www.dropbox.com/developers/apps) and sign in
2. Click "Create app"
3. Choose "Scoped access" API
4. Choose the type of access your app needs:
   - "App folder" - Access to a single folder created specifically for your app
   - "Full Dropbox" - Access to all files and folders in the user's Dropbox
5. Enter a name for your app (e.g., "DFP External Storage")
6. Click "Create app"
7. In the app settings:
   - Note your "App key" and "App secret"
   - Under "OAuth 2", add a redirect URI:
     `https://your-site.com/api/method/dfp_external_storage.dropbox_integration.oauth_callback`
   - Set the permissions to include "files.content.read" and "files.content.write"
8. Save changes

## 3. Configure Dropbox in DFP External Storage

1. Go to DFP External Storage list and create a new entry
2. Select "Dropbox" as the storage type
3. Enter your Dropbox App details:
   - Dropbox App Key
   - Dropbox App Secret
4. Save the document

## 4. Authenticate with Dropbox

1. Click the "Authenticate with Dropbox" button
2. Complete the OAuth flow in the popup window:
   - Sign in with your Dropbox account
   - Grant the requested permissions
3. After successful authentication, you'll return to the document
4. Click "Apply Authentication" to set the refresh token

## 5. Set Up Dropbox Folder

1. Specify a Dropbox folder path:
   - Use a full path format like "/MyFolder" (it must start with a slash)
   - You can use an existing folder or create a new one
2. Click "Test Connection" to verify access

## 6. Complete Configuration

1. Add Frappe folders that should use Dropbox storage
2. Configure advanced settings as needed:
   - Presigned URLs
   - Cache settings
   - Ignored DocTypes
3. Save the document

## 7. Usage

Once configured, files uploaded to the selected folders will be stored in Dropbox. You can:

- View files in Dropbox through the Dropbox web interface
- Access files through Frappe/ERPNext as usual
- Move files between storage providers using the DFP External Storage interface

## 8. Troubleshooting

### Authentication Issues

- Check that your redirect URI is correctly configured in both the Dropbox App Console and your site's config
- Ensure you've granted all the required permissions
- Try clearing your browser cache or using incognito mode

### File Upload/Download Issues

- Check the Frappe error logs for detailed error messages
- Verify the Dropbox folder path is correct and accessible
- Ensure your refresh token is valid (you may need to re-authenticate)

### Path Issues

- Ensure folder paths always start with a slash (/)
- Check for proper path formatting (e.g., "/Folder/Subfolder")
- Verify you have the correct permissions for the folder

## 9. Security Considerations

- App keys and secrets have significant access to your Dropbox files - keep them secure
- Consider using a dedicated Dropbox account rather than a personal account
- Use the "App folder" permission when possible instead of "Full Dropbox" access
- Regularly review the permissions granted to the app
