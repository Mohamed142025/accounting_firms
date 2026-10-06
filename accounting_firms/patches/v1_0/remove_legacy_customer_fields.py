import frappe

LEGACY_FIELDS = (
    "insurance_accounting_section",
    "insurance_number",
    "custom_column_break_oeef4",
    "additional_data_tab",
    "branches_tab",
    "branches_section",
    "customer_branches",
)


def execute():
    """Drop Customer custom fields replaced by the standalone Customer Branch doctype
    and the new Social Insurance table (branches / insurance number data were empty)."""
    for fieldname in LEGACY_FIELDS:
        name = frappe.db.get_value("Custom Field", {"dt": "Customer", "fieldname": fieldname})
        if name:
            frappe.delete_doc("Custom Field", name, force=True, ignore_permissions=True)

    # Customer Branch used to be a child table; make sure stale rows don't linger.
    if frappe.db.table_exists("Customer Branch"):
        frappe.db.sql("DELETE FROM `tabCustomer Branch` WHERE parenttype = 'Customer'")

    frappe.clear_cache(doctype="Customer")
