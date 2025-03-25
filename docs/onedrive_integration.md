# OneDrive Integration Guide for DFP External Storage

This guide provides step-by-step instructions for integrating Microsoft OneDrive support into the DFP External Storage app.

## 1. Install Required Dependencies

First, install the required Python packages for Microsoft Graph API access:

```bash
pip install msal requests
```

Or use the provided installation helper:

```bash
bench --site your-site.com execute dfp_external_storage/install_onedrive.py
```

## 2. Set Up Microsoft Azure App Registration

1. Go to the [Azure Portal](https://portal.azure.com/) and sign in
2. Navigate to "Azure Active Directory" > "App registrations"
3. Click "New registration"
4. Enter a name for your application (e.g., "DFP External Storage")
5. Select the appropriate account type:
   - "Accounts in this organizational directory only" for single tenant
   - "Accounts in any organizational directory" for multi-tenant
   - "Accounts in any organizational directory and Microsoft personal accounts" for both
6. Add a redirect URI:
   - Select "Web" as the platform
   - Enter your callback URL: `https://your-site.com/api/method/dfp_external_storage.onedrive_integration.oauth_callback`
7. Click "Register"
8. Note your "Application (client) ID" and "Directory (tenant) ID"
9. Navigate to "Certificates & secrets"
10. Click "New client secret"
11. Add a description and select an expiry time
12. Click "Add" and note the client secret value (you won't be able to see it again)
13. Navigate to "API permissions"
14. Click "Add a permission"
15. Select "Microsoft Graph"
16. Select "Delegated permissions"
17. Add the following permissions:
    - Files.ReadWrite.All
    - offline_access
18. Click "Add permissions"
19. Click "Grant admin consent" if you have admin rights

## 3. Configure OneDrive in DFP External Storage

1. Go to DFP External Storage list and create a new entry
2. Select "OneDrive" as the storage type
3. Enter your Azure App details:
   - Microsoft Application (Client) ID
   - Microsoft Client Secret
   - Microsoft Tenant ID (use 'common' for multi-tenant apps)
4. Save the document

## 4. Authenticate with OneDrive

1. Click the "Authenticate with OneDrive" button
2. Complete the OAuth flow in the popup window:
   - Sign in with your Microsoft account
   - Grant the requested permissions
3. After successful authentication, you'll return to the document
4. Click "Apply Authentication" to set the refresh token

## 5. Set Up OneDrive Folder

1. Find a OneDrive folder ID:
   - Navigate to the folder in OneDrive web interface
   - The URL will look like: `https://onedrive.live.com/?id=root&cid=FOLDER_ID`
   - Or extract it from Microsoft Graph Explorer by making a GET request to `/me/drive/root/children`
2. Enter the folder ID in the "OneDrive Folder ID" field
3. Click "Test Connection" to verify access

## 6. Complete Configuration

1. Add Frappe folders that should use OneDrive storage
2. Configure advanced settings as needed:
   - Presigned URLs
   - Cache settings
   - Ignored DocTypes
3. Save the document

## 7. Usage

Once configured, files uploaded to the selected folders will be stored in OneDrive. You can:

- View files in OneDrive through the OneDrive web interface
- Access files through Frappe/ERPNext as usual
- Move files between storage providers using the DFP External Storage interface

## 8. Troubleshooting

### Authentication Issues

- Check that your redirect URI is correctly configured in both Azure and your site's config
- Ensure you've granted all the required permissions
- If using a custom tenant, make sure your account has access to it

### File Upload/Download Issues

- Check the Frappe error logs for detailed error messages
- Verify the OneDrive folder ID is correct and accessible
- Ensure your refresh token is valid (you may need to re-authenticate)

### CORS Issues

If you encounter CORS errors:

1. Go to your Azure app registration
2. Navigate to "Authentication"
3. Add your Frappe site URL to the allowed CORS origins

## 9. Security Considerations

- Client secrets have significant access to your OneDrive files - keep them secure
- Consider using a dedicated OneDrive account rather than a personal account
- Regularly review the permissions granted to the app
- Set up audit logging in Azure for sensitive operations