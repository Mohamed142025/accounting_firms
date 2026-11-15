"""Office services of a customer: the service tree shown on the Customer form."""

import frappe
from frappe import _


def _check(customer, ptype="read"):
    if not frappe.has_permission("Customer", ptype=ptype, doc=customer):
        frappe.throw(_("ليس لديك صلاحية على هذا العميل."), frappe.PermissionError)


def office_services():
    return frappe.get_all(
        "Item",
        filters={"is_office_service": 1, "disabled": 0},
        fields=["name", "item_name", "item_group"],
        order_by="item_name asc",
    )


@frappe.whitelist()
def get_service_tree(customer=None):
    """Item groups that hold office services (with their ancestors), the services, and,
    for a saved customer, the open / last done service tasks of each service."""
    if customer:
        _check(customer)
    services = office_services()
    used = {s.item_group for s in services}
    groups = {g.name: g for g in frappe.get_all("Item Group", fields=["name", "parent_item_group", "lft"], order_by="lft asc")}
    wanted = set()
    for name in used:
        while name and name in groups and name not in wanted:
            wanted.add(name)
            name = groups[name].parent_item_group
    # "All Item Groups" says nothing on its own: its children are the top of the tree
    top = "All Item Groups"
    tree_groups = [
        {"name": g.name, "parent": None if g.parent_item_group in (None, "", top) else g.parent_item_group}
        for g in groups.values()
        if g.name in wanted and g.name != top
    ]
    return {"groups": tree_groups, "services": services, "stats": service_stats(customer) if customer else {}}


def service_stats(customer):
    """{service: {open, last_done}} of the customer's service tasks (main tasks only)."""
    if not frappe.get_meta("Task").has_field("af_service"):
        return {}
    stats = {}
    rows = frappe.get_all(
        "Task",
        filters={"af_customer": customer, "af_service": ["is", "set"], "parent_task": ["is", "not set"]},
        fields=["af_service", "status", "completed_on"],
    )
    for row in rows:
        s = stats.setdefault(row.af_service, {"open": 0, "last_done": None})
        if row.status in ("Completed", "Cancelled"):
            if row.completed_on and (not s["last_done"] or row.completed_on > s["last_done"]):
                s["last_done"] = row.completed_on
        else:
            s["open"] += 1
    return stats
