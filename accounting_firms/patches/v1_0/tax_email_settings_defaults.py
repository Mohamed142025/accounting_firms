"""Tax Email Settings saved before the new fields existed have them empty: give them their defaults."""

import frappe

DEFAULTS = {
    "fetch_interval_minutes": "30",
    "read_junk_folder": 1,
    "archive_older_than_days": 30,
    "failure_alert_after": 2,
}


def execute():
    frappe.reload_doc("accounting_firms", "doctype", "tax_email_settings")
    for field, value in DEFAULTS.items():
        if not frappe.db.exists("Singles", {"doctype": "Tax Email Settings", "field": field}):
            frappe.db.set_single_value("Tax Email Settings", field, value)
    frappe.clear_document_cache("Tax Email Settings", "Tax Email Settings")
