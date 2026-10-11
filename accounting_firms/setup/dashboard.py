"""Creates the Accounting Firms dashboard (number cards + report charts). Idempotent."""

import json

import frappe

DASHBOARD = "مكتب المحاسبة"
MODULE = "Accounting Firms"
YEAR_TO_DATE = json.dumps(
    {"from_date": "frappe.datetime.year_start()", "to_date": "frappe.datetime.get_today()"}
)

CARDS = (
    ("مستندات منتهية", "accounting_firms.setup.cards.expired_documents", "Customer", "#e24c4c"),
    ("تنتهي خلال 30 يوم", "accounting_firms.setup.cards.due_soon_documents", "Customer", "#f0a040"),
    ("إشعارات ضريبية جديدة", "accounting_firms.setup.cards.new_notifications", "Tax Notification", "#3b82f6"),
    ("إشعارات ضريبية متأخرة", "accounting_firms.setup.cards.overdue_notifications", "Tax Notification", "#e24c4c"),
)

CHARTS = (
    {
        "chart_name": "انتهاء المستندات حسب الشهر (من أول السنة)",
        "report_name": "Document Expiry Monitor",
        "filters_json": json.dumps({"status": "All", "days_threshold": 30}),
        "custom_options": json.dumps({"colors": ["#e24c4c", "#f0a040", "#29a37a"], "barOptions": {"stacked": 1}}),
    },
    {
        "chart_name": "الإشعارات الضريبية حسب الشهر (من أول السنة)",
        "report_name": "Tax Notifications Monitor",
        "filters_json": json.dumps({"status": "الكل"}),
        "custom_options": json.dumps(
            {"colors": ["#3b82f6", "#e24c4c", "#f0a040", "#29a37a", "#8b5cf6", "#9ca3af"], "barOptions": {"stacked": 1}}
        ),
    },
)


def ensure_cards():
    names = []
    for label, method, document_type, color in CARDS:
        name = frappe.db.get_value("Number Card", {"label": label, "type": "Custom"})
        values = {
            "label": label,
            "type": "Custom",
            "method": method,
            "document_type": document_type,
            "function": "Count",
            "color": color,
            "is_public": 1,
            "is_standard": 0,
            "module": MODULE,
            "show_percentage_stats": 0,
            # plain counts: no currency symbol, and the full number (the shortener turns 0 into NaN)
            "currency": "",
            "show_full_number": 1,
        }
        if name:
            doc = frappe.get_doc("Number Card", name)
            doc.update(values)
            doc.save(ignore_permissions=True)
        else:
            doc = frappe.get_doc({"doctype": "Number Card", **values}).insert(ignore_permissions=True)
        names.append(doc.name)
    return names


def ensure_charts():
    names = []
    for spec in CHARTS:
        values = {
            "chart_type": "Report",
            "use_report_chart": 1,
            "type": "Bar",
            "timeseries": 0,
            "is_public": 1,
            "is_standard": 0,
            "module": MODULE,
            "dynamic_filters_json": YEAR_TO_DATE,
            **spec,
        }
        name = frappe.db.get_value("Dashboard Chart", {"chart_name": spec["chart_name"]})
        if name:
            doc = frappe.get_doc("Dashboard Chart", name)
            doc.update(values)
            doc.save(ignore_permissions=True)
        else:
            doc = frappe.get_doc({"doctype": "Dashboard Chart", **values}).insert(ignore_permissions=True)
        names.append(doc.name)
    return names


def ensure_dashboard():
    cards = ensure_cards()
    charts = ensure_charts()
    if frappe.db.exists("Dashboard", DASHBOARD):
        doc = frappe.get_doc("Dashboard", DASHBOARD)
    else:
        doc = frappe.new_doc("Dashboard")
        doc.dashboard_name = DASHBOARD
    doc.module = MODULE
    doc.is_standard = 0
    doc.set("cards", [{"card": name} for name in cards])
    doc.set("charts", [{"chart": name, "width": "Full"} for name in charts])
    doc.save(ignore_permissions=True)
    return doc.name
