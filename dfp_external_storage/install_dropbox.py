#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
DFP External Storage - Dropbox Integration Installer

This script helps to ensure all dependencies for Dropbox integration
are properly installed.

Usage:
    bench --site [site-name] execute install_dropbox.py
"""

import frappe
import subprocess
import sys
import importlib.util
import os

REQUIRED_PACKAGES = [
    {"name": "dropbox", "import_name": "dropbox", "min_version": "11.36.0"}
]


def check_dependency(package):
    """Check if a Python package is installed and meets minimum version requirements"""
    try:
        # Try to import the package
        spec = importlib.util.find_spec(package["import_name"])
        if spec is None:
            return False, f"Package {package['name']} is not installed"

        # If min_version is specified, check the version
        if package["min_version"]:
            try:
                module = importlib.import_module(package["import_name"])
                if hasattr(module, "__version__"):
                    version = module.__version__
                    if version < package["min_version"]:
                        return (
                            False,
                            f"Package {package['name']} version {version} is lower than required {package['min_version']}",
                        )
            except:
                # Unable to check version, assume it's okay
                pass

        return True, f"Package {package['name']} is installed and meets requirements"
    except Exception as e:
        return False, f"Error checking {package['name']}: {str(e)}"


def install_dependency(package):
    """Attempt to install a package using pip"""
    package_spec = package["name"]
    if package["min_version"]:
        package_spec += f">={package['min_version']}"

    try:
        subprocess.check_call([sys.executable, "-m", "pip", "install", package_spec])
        return True, f"Successfully installed {package_spec}"
    except subprocess.CalledProcessError as e:
        return False, f"Failed to install {package_spec}: {str(e)}"


def ensure_dependencies():
    """Check and install all required dependencies"""
    all_installed = True
    results = []

    print("📋 Checking dependencies for Dropbox integration...")

    for package in REQUIRED_PACKAGES:
        installed, message = check_dependency(package)
        if not installed:
            print(f"⚠️ {message}")
            print(f"🔄 Installing {package['name']}...")
            success, install_message = install_dependency(package)
            results.append(
                f"- {package['name']}: {'✅' if success else '❌'} {install_message}"
            )
            if not success:
                all_installed = False
        else:
            print(f"✅ {message}")
            results.append(f"- {package['name']}: ✅ Already installed")

    return all_installed, results


def check_dropbox_integration():
    """Check if Dropbox integration files are present"""
    dropbox_file = os.path.join(
        frappe.get_app_path("dfp_external_storage"), "dropbox_integration.py"
    )
    if not os.path.exists(dropbox_file):
        return False
    return True


def create_install_log(success, results):
    """Create a log file with installation results"""
    log_dir = os.path.join(frappe.get_site_path(), "logs")
    if not os.path.exists(log_dir):
        os.makedirs(log_dir)

    log_file = os.path.join(log_dir, "dfp_dropbox_install.log")
    with open(log_file, "w") as f:
        f.write("DFP External Storage - Dropbox Integration Installation Log\n")
        f.write(f"Timestamp: {frappe.utils.now()}\n")
        f.write(f"Status: {'SUCCESS' if success else 'FAILED'}\n\n")
        f.write("Dependency Check Results:\n")
        for result in results:
            f.write(f"{result}\n")

    return log_file


def main():
    """Main function to prepare for Dropbox integration"""
    if not check_dropbox_integration():
        print("❌ Dropbox integration files not found.")
        print(
            "🔷 Please make sure you have added the dropbox_integration.py file to your app."
        )
        return

    dependencies_ok, results = ensure_dependencies()
    log_file = create_install_log(dependencies_ok, results)

    if dependencies_ok:
        print(
            "\n✅ All dependencies for Dropbox integration are installed successfully."
        )
        print("🔷 You can now use Dropbox storage in DFP External Storage.")

        # Update site_config.json to add OAuth redirect URI
        try:
            site_url = frappe.utils.get_url()
            oauth_redirect_uri = f"{site_url}/api/method/dfp_external_storage.dropbox_integration.oauth_callback"

            print(
                f"\n🔷 Make sure to add the following OAuth redirect URI to your site_config.json:"
            )
            print(f"   {oauth_redirect_uri}")

            print(
                "\n🔷 Also add this URI to your Dropbox App Console in the OAuth 2 Redirect URIs section."
            )
        except:
            print(
                "\n⚠️ Could not determine site URL. Please manually configure OAuth redirect URIs."
            )
    else:
        print("\n❌ Some dependencies could not be installed.")
        print(f"📝 Check the log file for details: {log_file}")
        print("🔶 Try installing the dependencies manually:")
        print("   pip install dropbox>=11.36.0")


if __name__ == "__main__":
    main()
