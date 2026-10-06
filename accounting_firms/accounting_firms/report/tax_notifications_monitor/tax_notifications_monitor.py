import frappe
from frappe import _
from frappe.utils import add_days, date_diff, getdate, today

OPEN_STATUSES = ("جديد", "تحت المراجعة")


def execute(filters=None):
    filters = frappe._dict(filters or {})
    rows = get_rows(filters)
    return get_columns(), rows, None, None, get_summary(rows)


def get_rows(filters):
    conditions = {}
    for field in ("customer", "assigned_to", "category"):
        if filters.get(field):
            conditions[field] = filters[field]

    status = filters.get("status") or "المفتوحة"
    if status in ("المفتوحة", "متأخر"):
        conditions["status"] = ["in", OPEN_STATUSES]
    elif status != "الكل":
        conditions["status"] = status
    if status == "متأخر":
        conditions["due_date"] = ["<", today()]

    if filters.get("from_date") and filters.get("to_date"):
        conditions["received_at"] = ["between", [filters.from_date, add_days(filters.to_date, 1)]]
    elif filters.get("from_date"):
        conditions["received_at"] = [">=", filters.from_date]
    elif filters.get("to_date"):
        conditions["received_at"] = ["<", add_days(filters.to_date, 1)]

    rows = frappe.get_list(
        "Tax Notification",
        filters=conditions,
        fields=[
            "name",
            "customer",
            "customer_name",
            "subject",
            "category",
            "tax_type",
            "priority",
            "received_at",
            "due_date",
            "status",
            "assigned_to",
            "sender",
        ],
        order_by="received_at desc",
        limit_page_length=5000,
    )

    current = getdate(today())
    for row in rows:
        overdue = row.due_date and row.status in OPEN_STATUSES and getdate(row.due_date) < current
        row.days_overdue = date_diff(current, getdate(row.due_date)) if overdue else 0
    return rows


def get_columns():
    return [
        {"fieldname": "name", "label": _("الإشعار"), "fieldtype": "Link", "options": "Tax Notification", "width": 150},
        {"fieldname": "customer", "label": _("العميل"), "fieldtype": "Link", "options": "Customer", "width": 130},
        {"fieldname": "customer_name", "label": _("اسم العميل"), "fieldtype": "Data", "width": 180},
        {"fieldname": "subject", "label": _("العنوان"), "fieldtype": "Data", "width": 300},
        {"fieldname": "category", "label": _("التصنيف"), "fieldtype": "Data", "width": 160},
        {"fieldname": "tax_type", "label": _("نوع الضريبة"), "fieldtype": "Data", "width": 130},
        {"fieldname": "priority", "label": _("الأولوية"), "fieldtype": "Data", "width": 90},
        {"fieldname": "received_at", "label": _("تاريخ الاستلام"), "fieldtype": "Datetime", "width": 160},
        {"fieldname": "due_date", "label": _("تاريخ الاستحقاق"), "fieldtype": "Date", "width": 120},
        {"fieldname": "days_overdue", "label": _("أيام التأخير"), "fieldtype": "Int", "width": 100},
        {"fieldname": "status", "label": _("الحالة"), "fieldtype": "Data", "width": 110},
        {"fieldname": "assigned_to", "label": _("المسؤول"), "fieldtype": "Link", "options": "User", "width": 180},
        {"fieldname": "sender", "label": _("المرسل"), "fieldtype": "Data", "width": 200},
    ]


def get_summary(rows):
    new = sum(1 for r in rows if r.status == "جديد")
    review = sum(1 for r in rows if r.status == "تحت المراجعة")
    overdue = sum(1 for r in rows if r.days_overdue)
    high = sum(1 for r in rows if r.priority == "عالية" and r.status in OPEN_STATUSES)
    unclassified = sum(1 for r in rows if not r.category)
    return [
        {"value": new, "indicator": "Blue", "label": _("جديد"), "datatype": "Int"},
        {"value": review, "indicator": "Orange", "label": _("تحت المراجعة"), "datatype": "Int"},
        {"value": overdue, "indicator": "Red", "label": _("متأخر"), "datatype": "Int"},
        {"value": high, "indicator": "Red", "label": _("أولوية عالية"), "datatype": "Int"},
        {"value": unclassified, "indicator": "Grey", "label": _("غير مصنف"), "datatype": "Int"},
    ]
