#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
DFP External Storage - App Cleanup Utility

This script helps to clean up database entries when regular app uninstallation fails.
Use it when you encounter errors like duplicate module definitions during installation.

Usage:
    bench --site [site-name] execute app_cleanup.py --args '["module_name"]'
    
Example:
    bench --site mysite.localhost execute app_cleanup.py --args '["DFP External Storage"]'
"""

import frappe
import json
import sys

def cleanup_app_module(module_name=None):
    """
    Clean up all database records related to a specific module
    
    Args:
        module_name (str): The exact module name to clean up
    """
    if not module_name:
        print("ERROR: No module name provided.")
        print("Usage: bench --site [site-name] execute app_cleanup.py --args '[\"Module Name\"]'")
        return
    
    print(f"Starting cleanup for module: {module_name}")
    
    # Delete DocTypes
    doctypes = frappe.db.get_all("DocType", filters={"module": module_name}, fields=["name"])
    print(f"Found {len(doctypes)} DocTypes to delete")
    
    for dt in doctypes:
        print(f"Deleting DocType: {dt['name']}")
        try:
            # First delete any documents of this type
            if frappe.db.table_exists(f"tab{dt['name']}"):
                frappe.db.sql(f"DELETE FROM `tab{dt['name']}`")
            
            # Then delete the DocType itself
            frappe.delete_doc("DocType", dt['name'], force=True)
        except Exception as e:
            print(f"Error deleting {dt['name']}: {str(e)}")
    
    # Delete Pages
    pages = frappe.db.get_all("Page", filters={"module": module_name}, fields=["name"])
    print(f"Found {len(pages)} Pages to delete")
    
    for page in pages:
        print(f"Deleting Page: {page['name']}")
        try:
            frappe.delete_doc("Page", page['name'], force=True)
        except Exception as e:
            print(f"Error deleting Page {page['name']}: {str(e)}")
    
    # Delete Reports
    reports = frappe.db.get_all("Report", filters={"module": module_name}, fields=["name"])
    print(f"Found {len(reports)} Reports to delete")
    
    for report in reports:
        print(f"Deleting Report: {report['name']}")
        try:
            frappe.delete_doc("Report", report['name'], force=True)
        except Exception as e:
            print(f"Error deleting Report {report['name']}: {str(e)}")
    
    # Delete Module Def
    print(f"Deleting Module Def: {module_name}")
    if frappe.db.exists("Module Def", module_name):
        try:
            frappe.delete_doc("Module Def", module_name, force=True)
        except Exception as e:
            print(f"Error deleting Module Def {module_name}: {str(e)}")
    
    # Delete Custom Fields
    custom_fields = frappe.db.get_all(
        "Custom Field", 
        filters={"dt": ["in", [d["name"] for d in doctypes]]}, 
        fields=["name"]
    )
    print(f"Found {len(custom_fields)} Custom Fields to delete")
    
    for cf in custom_fields:
        print(f"Deleting Custom Field: {cf['name']}")
        try:
            frappe.delete_doc("Custom Field", cf['name'], force=True)
        except Exception as e:
            print(f"Error deleting Custom Field {cf['name']}: {str(e)}")
    
    # Delete Property Setters
    property_setters = frappe.db.get_all(
        "Property Setter", 
        filters={"doc_type": ["in", [d["name"] for d in doctypes]]}, 
        fields=["name"]
    )
    print(f"Found {len(property_setters)} Property Setters to delete")
    
    for ps in property_setters:
        print(f"Deleting Property Setter: {ps['name']}")
        try:
            frappe.delete_doc("Property Setter", ps['name'], force=True)
        except Exception as e:
            print(f"Error deleting Property Setter {ps['name']}: {str(e)}")
    
    # Commit all changes
    frappe.db.commit()
    print(f"Cleanup complete for module: {module_name}")
    print("You can now try reinstalling the app.")

if __name__ == "__main__":
    args = frappe.flags.args or []
    
    if not args:
        print("No arguments provided.")
        print("Usage: bench --site [site-name] execute app_cleanup.py --args '[\"Module Name\"]'")
        sys.exit(1)
    
    module_name = args[0]
    cleanup_app_module(module_name)