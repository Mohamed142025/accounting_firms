import frappe

from accounting_firms.setup.dashboard import ensure_dashboard
from accounting_firms.setup.sidebar import sync_sidebar


def execute():
    for doctype in ("number_card", "dashboard_chart", "dashboard"):
        frappe.reload_doc("desk", "doctype", doctype)
    ensure_dashboard()
    sync_sidebar()
