"""Every service item of the office's service guide is an office service."""

import frappe

from accounting_firms.office_services.setup import setup

GUIDE_ROOTS = ("دليل الحدمات", "دليل الخدمات")


def execute():
    setup()
    for root in GUIDE_ROOTS:
        bounds = frappe.db.get_value("Item Group", root, ["lft", "rgt"])
        if not bounds:
            continue
        groups = frappe.get_all("Item Group", filters={"lft": [">=", bounds[0]], "rgt": ["<=", bounds[1]]}, pluck="name")
        frappe.db.set_value(
            "Item",
            {"item_group": ["in", groups], "is_stock_item": 0, "is_office_service": 0},
            "is_office_service",
            1,
            update_modified=False,
        )
