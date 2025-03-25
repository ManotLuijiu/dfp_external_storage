from . import __version__ as app_version

app_name = "dfp_external_storage"
app_title = "DFP External Storage"
app_publisher = "DFP"
app_description = "S3 compatible external storage for Frappe and ERPNext"
app_email = "developmentforpeople@gmail.com"
app_license = "MIT"

# Includes in <head>
# ------------------

# include js, css files in header of desk.html
app_include_js = "dfp_external_storage.app.bundle.js"
app_include_css = "dfp_external_storage.app.bundle.css"

override_doctype_class = {
    "File": "dfp_external_storage.dfp_external_storage.doctype.dfp_external_storage.dfp_external_storage.DFPExternalStorageFile",
}

page_renderer = [
    "dfp_external_storage.dfp_external_storage.doctype.dfp_external_storage.dfp_external_storage.DFPExternalStorageFileRenderer",
]

# Installation hooks
after_install = "dfp_external_storage.install_hooks.after_install"
after_sync = "dfp_external_storage.install_hooks.after_sync"

# Uninstallation hook
before_uninstall = "dfp_external_storage.uninstall.before_uninstall"

# DFP: More info about doc event hooks: https://frappeframework.com/docs/v13/user/en/basics/doctypes/controllers
doc_events = {
    "File": {
        # TODO: Remove below line after 2025.01.01
        # "on_update": "dfp_external_storage.dfp_external_storage.doctype.dfp_external_storage.dfp_external_storage.hook_file_on_update",
        "before_save": "dfp_external_storage.dfp_external_storage.doctype.dfp_external_storage.dfp_external_storage.hook_file_before_save",
        "after_delete": "dfp_external_storage.dfp_external_storage.doctype.dfp_external_storage.dfp_external_storage.hook_file_after_delete",
    }
}

# Translation
# --------------------------------

# Make link fields search translated document names for these DocTypes
# Recommended only for DocTypes which have limited documents with untranslated names
# For example: Role, Gender, etc.
# translated_search_doctypes = []
