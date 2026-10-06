import frappe
from frappe import _
from frappe.model.document import Document


class TaxPlatformAccount(Document):
    pass


def _get_row(name, parent):
    row = frappe.get_doc("Tax Platform Account", name)
    if row.parenttype != "Customer" or row.parent != parent:
        frappe.throw(_("صف غير صالح."), frappe.PermissionError)
    if not frappe.has_permission("Customer", ptype="read", doc=parent):
        frappe.throw(_("ليس لديك صلاحية قراءة بيانات هذا العميل."), frappe.PermissionError)
    return row


def _log_access(parent, platform, action):
    """Keep an audit trail in the Customer timeline of who revealed a password."""
    frappe.get_doc(
        {
            "doctype": "Comment",
            "comment_type": "Info",
            "reference_doctype": "Customer",
            "reference_name": parent,
            "content": _("{0} كلمة مرور منصة {1} بواسطة {2}").format(
                action, frappe.bold(platform), frappe.bold(frappe.session.user)
            ),
        }
    ).insert(ignore_permissions=True)


@frappe.whitelist()
def get_password(name, parent):
    frappe.only_for("System Manager")
    row = _get_row(name, parent)
    _log_access(parent, row.platform, _("تم عرض"))
    return row.get_password("password", raise_exception=False)


@frappe.whitelist()
def get_login_payload(name, parent):
    """Everything the browser needs to open the portal and fill the login form.

    The password is only included for System Managers; everyone else still
    gets the URL and username.
    """
    row = _get_row(name, parent)
    platform = frappe.get_doc("Tax Platform", row.platform)
    payload = {
        "platform": platform.name,
        "login_url": platform.login_url,
        "username": row.username,
        "password": None,
        "username_selector": platform.username_selector,
        "password_selector": platform.password_selector,
        "submit_selector": platform.submit_selector,
        "auto_submit": int(platform.auto_submit or 0),
    }
    if "System Manager" in frappe.get_roles():
        payload["password"] = row.get_password("password", raise_exception=False)
        _log_access(parent, row.platform, _("تم استخدام"))
    return payload
