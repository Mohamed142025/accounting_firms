import frappe
from frappe.model.document import Document


class TaxEmailConfiguration(Document):
    pass


@frappe.whitelist()
def get_password(name, parent):
    frappe.only_for("System Manager")

    row = frappe.get_doc("Tax Email Configuration", name)
    if row.parenttype != "Customer" or row.parent != parent:
        frappe.throw("Invalid tax email configuration row.", frappe.PermissionError)

    if not frappe.has_permission("Customer", ptype="read", doc=parent):
        frappe.throw("Not permitted to read this Customer.", frappe.PermissionError)

    return row.get_password("email_password", raise_exception=False)
