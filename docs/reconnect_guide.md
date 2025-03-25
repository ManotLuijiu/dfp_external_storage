# Cloud Storage Reconnection Guide

If you've previously uninstalled DFP External Storage while keeping your files in cloud storage, you can use our reconnection tools to restore access to those files after reinstalling the app.

## Automatic Reconnection

When you reinstall DFP External Storage, the app will **automatically detect** if:

1. Cloud storage reports exist from a previous installation
2. There are files that appear to be disconnected from their cloud storage

If both conditions are met, you'll see a notification with reconnection options:

![Reconnection Notification](../images/reconnect-notification.png)

You can either:

- Let the automatic reconnection process run
- Run the reconnection tool manually with more control

## Manual Reconnection Process

To manually reconnect your files to cloud storage:

```bash
bench --site your-site.com execute dfp_external_storage/reconnect.py
```

The tool will:

1. Find the most recent cloud storage report
2. Create placeholder storage configurations
3. Update file records to connect them to cloud storage
4. Show a summary of reconnected files

### Command Options

The reconnection tool supports several options:

```bash
# Specify a specific report file
bench --site your-site.com execute dfp_external_storage/reconnect.py \
    private/files/dfp_external_storage_reports/external_files_report_20240324_120000.csv

# Skip confirmation prompts
bench --site your-site.com execute dfp_external_storage/reconnect.py --yes

# Dry run (show what would be done without making changes)
bench --site your-site.com execute dfp_external_storage/reconnect.py --dry-run
```

## After Reconnection

After running the reconnection tool:

1. **Update Storage Configurations**:

   - Go to "DFP External Storage" in your Frappe Desk
   - Open each created configuration
   - Replace "RECONNECT_NEEDED" placeholders with your actual credentials:
     - For S3: endpoint, access key, secret key, etc.
     - For Google Drive: client ID, client secret, etc.
     - For OneDrive: client ID, client secret, etc.
     - For Dropbox: app key, app secret, etc.

2. **Test Connections**:
   - After updating credentials, test each connection
   - Verify that you can access your files

3. **Authenticate OAuth Services**:
   - For Google Drive, OneDrive, and Dropbox, complete the authentication flow
   - Click the "Authenticate with..." button after updating credentials

## Troubleshooting

If you encounter issues during reconnection:

### Missing Report File

If you don't have a report file from the previous installation:

1. Check in the `private/files/dfp_external_storage_reports` directory
2. If no report exists, you'll need to manually create storage configurations and update file records

### Authentication Failures

If you can't authenticate with cloud services:

1. Ensure your API credentials are correct and still valid
2. For OAuth services (Google Drive, OneDrive, Dropbox), check if you need to recreate the app registrations

### File Access Issues

If files are reconnected but still inaccessible:

1. Check the file paths in the "DFP External Storage S3 Key" field
2. Verify that files still exist at the specified paths in cloud storage
3. Ensure your storage service hasn't changed permissions or structure

## For Developers

If you need to programmatically reconnect files:

```python
import frappe
from dfp_external_storage.reconnect import run_auto_reconnect

# Run reconnection with specific report
run_auto_reconnect("/path/to/report.csv")

# Or let it find the most recent report
run_auto_reconnect()
```

For more details, see the source code in `dfp_external_storage/reconnect.py`.
