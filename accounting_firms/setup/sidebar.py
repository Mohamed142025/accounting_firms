"""Keeps the Accounting Firms links in the Selling sidebar (the sidebar shown on the Customer screens).

Standard sidebars are re-imported from ERPNext on migrate, so this runs from `after_migrate`.
"""

import frappe

SIDEBAR = "Selling"
DASHBOARD_LINK = {"label": "لوحة مكتب المحاسبة", "type": "Link", "link_type": "Dashboard", "link_to": "مكتب المحاسبة"}
REPORT_LINKS = (
    {"label": "تقرير انتهاء المستندات", "type": "Link", "link_type": "Report", "link_to": "Document Expiry Monitor"},
    {"label": "تقرير الإشعارات الضريبية", "type": "Link", "link_type": "Report", "link_to": "Tax Notifications Monitor"},
    {"label": "الإشعارات الضريبية", "type": "Link", "link_type": "DocType", "link_to": "Tax Notification"},
    {"label": "ملخص اليوم", "type": "Link", "link_type": "DocType", "link_to": "Employee Daily Summary"},
    {"label": "تقرير ساعات العمل", "type": "Link", "link_type": "Report", "link_to": "Daily Work Hours"},
)
OWN_LINKS = {(d["link_type"], d["link_to"]) for d in (DASHBOARD_LINK, *REPORT_LINKS)}


def _item(spec, child=0):
    return {**spec, "child": child, "indent": 0, "collapsible": 0, "keep_closed": 0, "show_arrow": 0}


def sync_sidebar():
    if not frappe.db.exists("Workspace Sidebar", SIDEBAR):
        return
    if not frappe.db.exists("Dashboard", DASHBOARD_LINK["link_to"]):
        return

    sidebar = frappe.get_doc("Workspace Sidebar", SIDEBAR)
    items = [row for row in sidebar.items if (row.link_type, row.link_to) not in OWN_LINKS]
    rows = [row.as_dict() for row in items]

    # dashboard link right after the standard "Dashboard" entry (or at the top)
    pos = next((i + 1 for i, r in enumerate(rows) if r.get("link_type") == "Dashboard"), 1)
    rows.insert(pos, _item(DASHBOARD_LINK))

    # report links at the beginning of the "Reports" section (or at the end)
    section = next(
        (i + 1 for i, r in enumerate(rows) if r.get("type") == "Section Break" and (r.get("label") or "").lower() == "reports"),
        None,
    )
    pos = section if section is not None else len(rows)
    for offset, spec in enumerate(REPORT_LINKS):
        rows.insert(pos + offset, _item(spec, child=1 if section is not None else 0))

    sidebar.set("items", [])
    for idx, row in enumerate(rows, start=1):
        row = {k: v for k, v in row.items() if k not in ("name", "idx", "creation", "modified", "owner", "modified_by", "parent", "parentfield", "parenttype", "docstatus")}
        sidebar.append("items", {**row, "idx": idx})
    sidebar.flags.ignore_permissions = True
    sidebar.save(ignore_permissions=True)
    frappe.db.commit()


def after_migrate():
    try:
        sync_sidebar()
    except Exception:
        frappe.log_error(title="accounting_firms: sidebar sync failed")
