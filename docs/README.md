# Installation and Uninstallation Guide

DFP External Storage includes special tools to safely handle installation, uninstallation, and reinstallation while preserving your cloud storage connections.

## Installation

Standard installation:

```bash
# Get the app
cd ~/frappe-bench
bench get-app https://github.com/developmentforpeople/dfp_external_storage.git

# Install the app on your site
bench --site your-site.com install-app dfp_external_storage
```

## Uninstallation

When uninstalling DFP External Storage, you have options for handling your cloud files:

```bash
# Interactive uninstallation helper
bench --site your-site.com execute dfp_external_storage/uninstall_helper.py

# Move all files to local storage before uninstalling
bench --site your-site.com execute dfp_external_storage/uninstall_helper.py --move-all

# Keep files in cloud storage (file access will be broken until reinstallation)
bench --site your-site.com execute dfp_external_storage/uninstall_helper.py --keep-all

# Just generate a report without uninstalling
bench --site your-site.com execute dfp_external_storage/uninstall_helper.py --report-only
```

## Reinstallation and Reconnection

When you reinstall DFP External Storage after previously uninstalling it:

1. The app will automatically detect previous cloud storage configurations
2. You'll be prompted to reconnect your files to cloud storage
3. Storage configurations will be recreated with placeholder values
4. You'll need to update the configurations with your actual credentials

### Manual Reconnection

If automatic reconnection doesn't work or you want more control:

```bash
# Run reconnection tool with the most recent report
bench --site your-site.com execute dfp_external_storage/reconnect.py

# Specify a particular report file
bench --site your-site.com execute dfp_external_storage/reconnect.py \
    private/files/dfp_external_storage_reports/external_files_report_20240324_120000.csv

# Skip confirmation prompts
bench --site your-site.com execute dfp_external_storage/reconnect.py --yes

# Dry run (show what would be done without making changes)
bench --site your-site.com execute dfp_external_storage/reconnect.py --dry-run
```

After reconnection, you'll need to update the storage configurations with your actual credentials.

## Safe Migration Practices

When working with DFP External Storage across different environments:

1. **Before migration**: Generate a report of external files

   ```bash
   bench --site source-site.com execute dfp_external_storage/uninstall_helper.py --report-only
   ```

2. **After migration**: Use the report to reconnect files

   ```bash
   bench --site target-site.com execute dfp_external_storage/reconnect.py /path/to/report.csv
   ```

For detailed instructions, see:

<!-- - [Installation Guide](installation_guide.md) -->
- [Safe Uninstallation Guide](docs/uninstall_guide.md)
- [Cloud Storage Reconnection Guide](reconnect_guide.md)
