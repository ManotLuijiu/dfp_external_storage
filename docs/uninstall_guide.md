# Safe Uninstallation Guide for DFP External Storage

When uninstalling DFP External Storage, you need to consider what happens to your files stored in external cloud storage services (S3, Google Drive, OneDrive, Dropbox). This guide explains the options and steps for a safe uninstallation process.

## Understanding the Impact

When you uninstall the DFP External Storage app:

- **Files stored in cloud services remain there** - Nothing is automatically deleted from your S3 buckets, Google Drive, OneDrive, or Dropbox.
- **Connection to those files is lost** - Frappe/ERPNext will no longer be able to access those external files.
- **File references will be broken** - Documents that reference these files will show missing attachments.

## Uninstallation Options

You have three main options when uninstalling:

1. **Move files back to local storage** - Download all external files to your local Frappe server before uninstalling.
2. **Keep files in cloud storage** - Uninstall while leaving files in the cloud (file access will be broken).
3. **Generate a report only** - Get information about your external files without uninstalling.

## Uninstallation Helper Tool

We provide an uninstall helper script that guides you through these options:

```bash
# Basic usage - interactive prompts
bench --site your-site.com execute dfp_external_storage/uninstall_helper.py

# Move all files to local storage automatically
bench --site your-site.com execute dfp_external_storage/uninstall_helper.py --move-all

# Keep files in cloud storage and proceed with uninstall
bench --site your-site.com execute dfp_external_storage/uninstall_helper.py --keep-all

# Just generate a report of external files without taking action
bench --site your-site.com execute dfp_external_storage/uninstall_helper.py --report-only

# Dry run - show what would happen without making changes
bench --site your-site.com execute dfp_external_storage/uninstall_helper.py --dry-run
```

## Step-by-Step Guide

### Option 1: Moving Files Back to Local Storage

This is the safest option if you want to maintain access to all your files:

1. Run the uninstall helper in interactive mode:

   ```bash
   bench --site your-site.com execute dfp_external_storage/uninstall_helper.py
   ```

2. Choose option 1 when prompted:

   ```bash
   Please choose an option:
   1. Move all files back to local storage before uninstalling
   2. Keep files in cloud storage and proceed with uninstall
   3. Cancel uninstallation
   ```

3. The script will:
   - Download all files from external storage to your local Frappe server
   - Update file records to point to the local files
   - Remove the files from external storage (optional)
   - Proceed with uninstallation after confirmation

4. After successful migration, confirm the uninstallation.

### Option 2: Keeping Files in Cloud Storage

If you want to leave files in cloud storage (understanding that access will be broken):

1. Run the uninstall helper with the keep-all flag:

   ```bash
   bench --site your-site.com execute dfp_external_storage/uninstall_helper.py --keep-all
   ```

2. The script will:
   - Generate a report of all externally stored files
   - Warn you about the consequences
   - Proceed with uninstallation after confirmation

### Option 3: Generate Report Only

If you just want to see what files would be affected:

```bash
bench --site your-site.com execute dfp_external_storage/uninstall_helper.py --report-only
```

This generates a CSV report in your site's `private/files/dfp_external_storage_reports` directory with details about all externally stored files.

## After Uninstallation

After uninstalling, depending on your chosen option:

- **If you moved files to local storage**: All files should remain accessible within Frappe/ERPNext.
- **If you kept files in cloud storage**: File references will be broken. You'll need to manually handle any important files.

The uninstallation report (generated in either case) provides a record of all file locations that can be used for reference later.

## Reinstalling After Uninstallation

If you need to reinstall the app later:

1. For files that were moved to local storage, everything should work normally.
2. For files left in cloud storage, you'll need to:
   - Recreate your storage configurations
   - Manually update file records to reconnect them to external storage

## Troubleshooting

If you encounter issues during the uninstallation process:

- Check the log file generated in your site's `logs` directory.
- For errors with specific files, try moving them individually or in smaller batches.
- If the uninstallation process gets interrupted, you can safely run the helper script again.
