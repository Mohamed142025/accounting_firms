import frappe


CUSTOM_FIELD_ANCHORS = {
    "Customer-company_profile_section": "customer_type",
    "Customer-insurance_accounting_section": "parent_company_group",
    "Customer-tax_file_number": "tax_withholding_category",
    "Customer-tax_office": "tax_file_number",
    "Customer-tax_accounting_law": "tax_office",
    "Customer-subject_to_law": "tax_accounting_law",
}


def execute():
    if frappe.db.exists("Custom Field", "Customer-details_tab"):
        frappe.delete_doc("Custom Field", "Customer-details_tab", force=True)

    for field_name in ("Customer-tax_custom_section", "Customer-tax_custom_section_2"):
        if frappe.db.exists("Custom Field", field_name):
            frappe.delete_doc("Custom Field", field_name, force=True)

    for field_name, insert_after in CUSTOM_FIELD_ANCHORS.items():
        if frappe.db.exists("Custom Field", field_name):
            frappe.db.set_value("Custom Field", field_name, "insert_after", insert_after)

    if frappe.db.exists("Custom Field", "Customer-tax_section"):
        frappe.delete_doc("Custom Field", "Customer-tax_section", force=True)

    frappe.clear_cache(doctype="Customer")
