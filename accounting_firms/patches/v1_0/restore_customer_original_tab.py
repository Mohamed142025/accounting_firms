import frappe


def execute():
    if frappe.db.exists("Custom Field", "Customer-details_tab"):
        frappe.delete_doc("Custom Field", "Customer-details_tab", force=True)

    for field_name in ("Customer-tax_custom_section", "Customer-tax_custom_section_2"):
        if frappe.db.exists("Custom Field", field_name):
            frappe.delete_doc("Custom Field", field_name, force=True)

    if frappe.db.exists("Custom Field", "Customer-company_profile_section"):
        frappe.db.set_value(
            "Custom Field",
            "Customer-company_profile_section",
            "insert_after",
            "customer_type",
        )

    frappe.clear_cache(doctype="Customer")
