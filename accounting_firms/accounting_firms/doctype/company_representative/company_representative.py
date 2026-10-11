import frappe
from frappe import _
from frappe.model.document import Document


class CompanyRepresentative(Document):
    pass


@frappe.whitelist()
def create_contact(name, parent):
    """Create (or link) an ERPNext Contact for a representative row of the given customer."""
    if not frappe.has_permission("Customer", ptype="write", doc=parent):
        frappe.throw(_("ليس لديك صلاحية على هذا العميل."), frappe.PermissionError)
    row = frappe.get_doc("Company Representative", name)
    if row.parenttype != "Customer" or row.parent != parent:
        frappe.throw(_("صف غير صالح."), frappe.PermissionError)
    if row.contact and frappe.db.exists("Contact", row.contact):
        return row.contact

    contact = frappe.new_doc("Contact")
    parts = (row.representative_name or "").strip().split(" ", 1)
    contact.first_name = parts[0]
    contact.last_name = parts[1] if len(parts) > 1 else None
    contact.designation = row.designation
    if row.email:
        contact.append("email_ids", {"email_id": row.email, "is_primary": 1})
    if row.mobile:
        contact.append("phone_nos", {"phone": row.mobile, "is_primary_mobile_no": 1})
    contact.append("links", {"link_doctype": "Customer", "link_name": parent})
    contact.insert(ignore_permissions=True)
    frappe.db.set_value("Company Representative", name, "contact", contact.name, update_modified=False)
    return contact.name
