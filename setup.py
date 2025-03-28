from setuptools import setup, find_packages
import subprocess
import sys
import os

# Get version from __init__.py
with open(
    os.path.join(os.path.dirname(__file__), "dfp_external_storage", "__init__.py"), "r"
) as f:
    for line in f:
        if line.startswith("__version__"):
            version = line.strip().split("=")[1].strip(" '\"")
            break
    else:
        version = "0.0.1"


# Check and install dependencies
def check_and_install_deps():
    required_packages = ["minio", "boto3>=1.34.0"]
    for package in required_packages:
        package_name = package.split(">=")[0].split("==")[0]
        try:
            __import__(package_name)
            print(f"✅ {package_name} is already installed")
        except ImportError:
            print(f"⚠️ {package_name} is not installed. Installing...")
            try:
                subprocess.check_call([sys.executable, "-m", "pip", "install", package])
                print(f"✅ Successfully installed {package}")
            except subprocess.CalledProcessError:
                print(f"❌ Failed to install {package}. Please install it manually.")
                print(f"   Run: pip install {package}")


# Run dependency check
check_and_install_deps()

setup(
    name="dfp_external_storage",
    version=version,
    description="S3 compatible, Google Drive, OneDrive, and Dropbox external storage for Frappe and ERPNext",
    author="Manot L.",
    author_email="moocoding@gmail.com",
    packages=find_packages(),
    zip_safe=False,
    include_package_data=True,
    install_requires=[
        # "frappe~=15.0.0" # Installed and managed by bench.
        "boto3>=1.34.0",  # Add this line for AWS S3 support
        "minio",
        # Google Drive API requirements for DFP External Storage
        "google-api-python-client>=2.86.0",
        "google-auth>=2.17.3",
        "google-auth-oauthlib>=1.0.0",
        "google-auth-httplib2>=0.1.0",
        # OneDrive API requirements for DFP External Storage
        "msal>=1.20.0",
        "requests>=2.28.0",
        # Dropbox API requirements for DFP External Storage
        "dropbox>=11.36.0",
    ],
)
