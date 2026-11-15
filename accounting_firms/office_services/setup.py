"""Fields the office services add to standard doctypes (kept here, not in the Customer
fixtures, which only hold the Customer layout)."""

import frappe
from frappe.custom.doctype.custom_field.custom_field import create_custom_fields

MODULE = "Accounting Firms"

FIELDS = {
    "Item": [
        {
            "fieldname": "is_office_service",
            "label": "خدمة مكتب",
            "fieldtype": "Check",
            "insert_after": "is_stock_item",
            "in_standard_filter": 1,
            "description": "تظهر في شجرة خدمات العميل وفي خرائط المهام.",
            "module": MODULE,
        },
    ],
    "Department": [
        {
            "fieldname": "af_manager",
            "label": "مدير القسم",
            "fieldtype": "Link",
            "options": "Employee",
            "insert_after": "parent_department",
            "description": "مهام الخدمات المسندة لـ«مدير قسم» بتروح له.",
            "module": MODULE,
        },
    ],
}


def setup():
    create_custom_fields(FIELDS, update=True)


def after_migrate():
    try:
        setup()
    except Exception:
        frappe.log_error(title="accounting_firms: office services setup failed")
