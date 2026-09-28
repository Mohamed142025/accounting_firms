import frappe


def execute():
    if frappe.db.exists("Custom Field", "Customer-tax_section"):
        frappe.delete_doc("Custom Field", "Customer-tax_section", force=True)
        frappe.clear_cache(doctype="Customer")
