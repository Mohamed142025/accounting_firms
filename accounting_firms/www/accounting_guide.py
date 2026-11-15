"""The office guide (/accounting-guide): for logged-in users only."""

import frappe

no_cache = 1


def get_context(context):
    if frappe.session.user == "Guest":
        frappe.local.flags.redirect_location = "/login?redirect-to=/accounting-guide"
        raise frappe.Redirect
    context.no_cache = 1
