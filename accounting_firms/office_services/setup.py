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
    "Task": [
        {"fieldname": "af_section", "label": "خدمة المكتب", "fieldtype": "Section Break", "insert_after": "parent_task",
         "depends_on": "eval:doc.af_service", "module": MODULE},
        {"fieldname": "af_customer", "label": "العميل", "fieldtype": "Link", "options": "Customer", "insert_after": "af_section",
         "in_standard_filter": 1, "search_index": 1, "read_only": 1, "module": MODULE},
        {"fieldname": "af_service", "label": "الخدمة", "fieldtype": "Link", "options": "Item", "insert_after": "af_customer",
         "in_standard_filter": 1, "search_index": 1, "read_only": 1, "module": MODULE},
        {"fieldname": "af_period", "label": "الفترة", "fieldtype": "Data", "insert_after": "af_service", "read_only": 1, "module": MODULE},
        {"fieldname": "af_column_1", "fieldtype": "Column Break", "insert_after": "af_period", "module": MODULE},
        {"fieldname": "af_assign_type", "label": "إسناد إلى", "fieldtype": "Data", "insert_after": "af_column_1", "read_only": 1, "module": MODULE},
        {"fieldname": "af_role", "label": "الرول", "fieldtype": "Link", "options": "Role", "insert_after": "af_assign_type", "read_only": 1,
         "depends_on": "eval:doc.af_role", "module": MODULE},
        {"fieldname": "af_assign_user", "label": "مسندة لشخص محدد", "fieldtype": "Link", "options": "User", "insert_after": "af_role",
         "read_only": 1, "depends_on": "eval:doc.af_assign_user", "module": MODULE},
        {"fieldname": "af_claimed_by", "label": "استلمها", "fieldtype": "Link", "options": "User", "insert_after": "af_assign_user",
         "read_only": 1, "depends_on": "eval:doc.af_claimed_by", "module": MODULE},
        {"fieldname": "af_column_2", "fieldtype": "Column Break", "insert_after": "af_claimed_by", "module": MODULE},
        {"fieldname": "af_waiting_reason", "label": "سبب الانتظار", "fieldtype": "Select", "options": "\nمنتظر الجهة\nمنتظر العميل",
         "insert_after": "af_column_2", "depends_on": "eval:!doc.is_group", "module": MODULE},
        {"fieldname": "af_execution", "label": "التنفيذ", "fieldtype": "Data", "insert_after": "af_waiting_reason", "read_only": 1, "module": MODULE},
        {"fieldname": "af_mandatory", "label": "إجبارية", "fieldtype": "Check", "insert_after": "af_execution", "read_only": 1, "module": MODULE},
        {"fieldname": "af_requires_attachment", "label": "تحتاج مرفق", "fieldtype": "Check", "insert_after": "af_mandatory", "read_only": 1, "module": MODULE},
        {"fieldname": "af_ready", "label": "بدأت", "fieldtype": "Check", "insert_after": "af_requires_attachment", "read_only": 1,
         "description": "المهمة بتبدأ (وتتسند) لما المهام اللي قبلها تخلص.", "module": MODULE},
        {"fieldname": "af_pool", "label": "مسندة لمجموعة", "fieldtype": "Check", "insert_after": "af_ready", "read_only": 1, "hidden": 1, "module": MODULE},
        {"fieldname": "af_task_no", "label": "رقم المهمة في الخريطة", "fieldtype": "Data", "insert_after": "af_pool", "read_only": 1, "hidden": 1, "module": MODULE},
        {"fieldname": "af_expected_days", "label": "المدة (يوم)", "fieldtype": "Int", "insert_after": "af_task_no", "read_only": 1, "hidden": 1, "module": MODULE},
        {"fieldname": "af_root", "label": "المهمة الرئيسية للخدمة", "fieldtype": "Link", "options": "Task", "insert_after": "af_expected_days",
         "read_only": 1, "hidden": 1, "search_index": 1, "module": MODULE},
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
