import frappe


def execute():
    for field_name in ("Customer-tax_custom_section", "Customer-tax_custom_section_2"):
        if frappe.db.exists("Custom Field", field_name):
            frappe.delete_doc("Custom Field", field_name, force=True)

    frappe.clear_cache(doctype="Customer")
