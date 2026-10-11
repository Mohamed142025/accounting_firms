"""Number card sources for the Accounting Firms dashboard."""

import frappe
from frappe.utils import add_days, today

from accounting_firms.accounting_firms.report.document_expiry_monitor.document_expiry_monitor import (
    get_expiry_rows,
    get_status,
)


def _expiry_count(status, threshold=30):
    from frappe.utils import date_diff, getdate

    rows = get_expiry_rows()
    return sum(1 for r in rows if get_status(date_diff(getdate(r.expiry_date), getdate(today())), threshold) == status)


@frappe.whitelist()
def expired_documents(filters=None):
    return {
        "value": _expiry_count("Expired"),
        "fieldtype": "Int",
        "route": ["query-report", "Document Expiry Monitor"],
        "route_options": {"status": "Expired"},
    }


@frappe.whitelist()
def due_soon_documents(filters=None):
    return {
        "value": _expiry_count("Due Soon"),
        "fieldtype": "Int",
        "route": ["query-report", "Document Expiry Monitor"],
        "route_options": {"status": "Due Soon"},
    }


@frappe.whitelist()
def new_notifications(filters=None):
    return {
        "value": frappe.db.count("Tax Notification", {"status": "جديد"}),
        "fieldtype": "Int",
        "route": ["tax-notification"],
        "route_options": {"status": "جديد"},
    }


@frappe.whitelist()
def overdue_notifications(filters=None):
    return {
        "value": frappe.db.count(
            "Tax Notification",
            {"status": ["in", ["جديد", "تحت المراجعة"]], "due_date": ["<", today()]},
        ),
        "fieldtype": "Int",
        "route": ["query-report", "Tax Notifications Monitor"],
        "route_options": {"status": "متأخر", "from_date": add_days(today(), -365)},
    }
