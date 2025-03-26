#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
DFP External Storage - Installation Helper

This script helps to ensure all dependencies are properly installed
before attempting to install the app with bench.

Usage:
    bench --site [site-name] execute install.py
"""

import frappe
import subprocess
import sys
import importlib.util
import json
import os

REQUIRED_PACKAGES = [
    {'name': 'minio', 'import_name': 'minio', 'min_version': None},
    {'name': 'boto3', 'import_name': 'boto3', 'min_version': '1.34.0'}
]

def check_dependency(package):
    """Check if a Python package is installed and meets minimum version requirements"""
    try:
        # Try to import the package
        spec = importlib.util.find_spec(package['import_name'])
        if spec is None:
            return False, f"Package {package['name']} is not installed"
        
        # If min_version is specified, check the version
        if package['min_version']:
            module = importlib.import_module(package['import_name'])
            if hasattr(module, '__version__'):
                version = module.__version__
                if version < package['min_version']:
                    return False, f"Package {package['name']} version {version} is lower than required {package['min_version']}"
        
        return True, f"Package {package['name']} is installed and meets requirements"
    except Exception as e:
        return False, f"Error checking {package['name']}: {str(e)}"

def install_dependency(package):
    """Attempt to install a package using pip"""
    package_spec = package['name']
    if package['min_version']:
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
    
    print("📋 Checking dependencies for DFP External Storage...")
    
    for package in REQUIRED_PACKAGES:
        installed, message = check_dependency(package)
        if not installed:
            print(f"⚠️ {message}")
            print(f"🔄 Installing {package['name']}...")
            success, install_message = install_dependency(package)
            results.append(f"- {package['name']}: {'✅' if success else '❌'} {install_message}")
            if not success:
                all_installed = False
        else:
            print(f"✅ {message}")
            results.append(f"- {package['name']}: ✅ Already installed")
    
    return all_installed, results

def check_app_installed():
    """Check if DFP External Storage is already installed"""
    try:
        installed_apps = frappe.get_installed_apps()
        if 'dfp_external_storage' in installed_apps:
            return True
        return False
    except:
        return False

def create_install_log(success, results):
    """Create a log file with installation results"""
    log_dir = os.path.join(frappe.get_site_path(), 'logs')
    if not os.path.exists(log_dir):
        os.makedirs(log_dir)
    
    log_file = os.path.join(log_dir, 'dfp_external_storage_install.log')
    with open(log_file, 'w') as f:
        f.write("DFP External Storage Installation Log\n")
        f.write(f"Timestamp: {frappe.utils.now()}\n")
        f.write(f"Status: {'SUCCESS' if success else 'FAILED'}\n\n")
        f.write("Dependency Check Results:\n")
        for result in results:
            f.write(f"{result}\n")
    
    return log_file

def main():
    """Main function to prepare for app installation"""
    if check_app_installed():
        print("🟢 DFP External Storage is already installed.")
        return
    
    dependencies_ok, results = ensure_dependencies()
    log_file = create_install_log(dependencies_ok, results)
    
    if dependencies_ok:
        print("\n✅ All dependencies are installed successfully.")
        print("🔷 You can now install the app with:")
        print("   bench --site [site-name] install-app dfp_external_storage")
    else:
        print("\n❌ Some dependencies could not be installed.")
        print(f"📝 Check the log file for details: {log_file}")
        print("🔶 Try installing the dependencies manually and then run:")
        print("   bench --site [site-name] install-app dfp_external_storage")

if __name__ == "__main__":
    main()