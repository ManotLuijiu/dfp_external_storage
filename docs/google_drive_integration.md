# Google Drive Integration Guide for DFP External Storage

This guide provides step-by-step instructions for integrating Google Drive support into the DFP External Storage app.

## 1. Install Required Dependencies

First, install the required Python packages for Google Drive API access:

```bash
pip install google-api-python-client google-auth google-auth-oauthlib
```

## 2. Add Google Drive Integration Module

1. Create a new file `dfp_external_storage/gdrive_integration.py` with the code from the "Google Drive Integration for DFP External Storage" artifact.

## 3. Update DocType Definition

1. Use Frappe's DocType editor to modify the "DFP External Storage" DocType, adding the new fields for Google Drive support:

   - Add "Google Drive" to the "Type" Select field options
   - Create a new Section Break "Google Drive Settings" with `depends_on: eval:doc.type=='Google Drive'`
   - Add fields for Google Client ID, Google Client Secret, Google Refresh Token, and Google Folder ID
   - Add an HTML field for the Google Auth Button

   Alternatively, you can import the JSON definition from the "Modified DFP External Storage DocType" artifact.

## 4. Update JavaScript Client Code

1. Replace or update the file `dfp_external_storage/dfp_external_storage/doctype/dfp_external_storage/dfp_external_storage.js` with the code from the "Modified DFP External Storage JavaScript" artifact.

## 5. Update the DFP External Storage File Class

1. Modify the `dfp_external_storage/dfp_external_storage/doctype/dfp_external_storage/dfp_external_storage.py` file to integrate the Google Drive file handling code.

2. Add the following methods to handle Google Drive files:

   ```python
   # At the top of the file, add:
   from dfp_external_storage.gdrive_integration import GoogleDriveConnection
   
   # Add the DFPExternalStorageGoogleDriveFile class from the "DFP External Storage File Class Update" artifact
   
   # Then update the following methods in DFPExternalStorageFile class:
   ```

3. In the existing `dfp_external_storage_upload_file` method, add Google Drive support:

   ```python
   def dfp_external_storage_upload_file(self, local_file=None):
       """Upload file to external storage"""
       # Check if this is a Google Drive storage
       if self.dfp_external_storage_doc and self.dfp_external_storage_doc.type == "Google Drive":
           gdrive_handler = DFPExternalStorageGoogleDriveFile(self)
           return gdrive_handler.upload_file(local_file)
           
       # Existing S3 upload logic
       # [...]
   ```

4. Similarly update the other methods to check for Google Drive storage type and call the appropriate handler.

## 6. Add OAuth Callback URL to Your Site Config

1. Edit your `site_config.json` file to enable the OAuth callback URL:

   ```json
   {
     "host_name": "your-frappe-site.com",
     "oauth_redirect_uris": [
       "https://your-frappe-site.com/api/method/dfp_external_storage.gdrive_integration.oauth_callback"
     ]
   }
   ```

## 7. Set Up Google Cloud Project

1. Go to the [Google Cloud Console](https://console.cloud.google.com/) and create a new project.

2. Enable the Google Drive API:
   - Navigate to "APIs & Services" > "Library"
   - Search for "Google Drive API" and enable it

3. Create OAuth 2.0 Credentials:
   - Go to "APIs & Services" > "Credentials"
   - Click "Create Credentials" > "OAuth client ID"
   - Select "Web application" as the Application type
   - Add your site's URL to the authorized JavaScript origins
   - Add the OAuth callback URL to the authorized redirect URIs:
     `https://your-frappe-site.com/api/method/dfp_external_storage.gdrive_integration.oauth_callback`
   - Click "Create" and note your Client ID and Client Secret

## 8. Testing Google Drive Integration

1. Create a new DFP External Storage entry:
   - Select "Google Drive" as the Type
   - Enter your Google Client ID and Client Secret
   - Save the document

2. Authenticate with Google Drive:
   - Click the "Authenticate with Google Drive" button
   - Complete the OAuth flow in the popup window
   - After successful authentication, you'll return to the document
   - Click "Apply Authentication" to apply the refresh token

3. Enter a Google Drive Folder ID:
   - To find a folder ID, navigate to the folder in Google Drive
   - The folder ID is in the URL: `https://drive.google.com/drive/folders/FOLDER_ID`

4. Test the connection:
   - The system will verify that it can access the specified folder

5. Save the document and try uploading files

## 9. Troubleshooting

### OAuth Issues

- Ensure your redirect URIs in the Google Cloud Console match exactly with your site's callback URL
- Check browser console for any popup blocking issues
- Verify that your site is using HTTPS (required for OAuth)

### File Upload/Download Issues

- Check the error logs in Frappe for detailed error messages
- Verify that your Google API credentials have the correct permissions
- Ensure the Google Drive folder ID is correct and accessible to your account

### Connection Issues

- Check if your refresh token is valid and not expired
- Verify that the Google Drive API is enabled for your project
- Ensure your site can make outbound HTTPS connections

## 10. Advanced Configuration

### Customizing Google Drive File Structure

You can modify the `DFPExternalStorageGoogleDriveFile` class to implement a custom folder structure in Google Drive. For example, you might want to create subfolders based on file types or Frappe DocTypes.

### Implementing File Versioning

Google Drive supports file versioning. You could extend the integration to leverage this feature by:

1. Modifying the `upload_file` method to check for existing files with the same name
2. Using Google Drive's versioning API to update existing files instead of creating new ones

### Adding Team Drive Support

To support Google Team Drives (Shared Drives):

1. Update the OAuth scope to include 'https://www.googleapis.com/auth/drive'
2. Modify the API calls to include the `supportsTeamDrives=True` parameter

### Synchronization Features

You could implement background synchronization features:

1. Create a scheduled task to check for files that need to be synchronized
2. Add a UI to show synchronization status and history
3. Implement conflict resolution for files modified both locally and in Google Drive