import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import format_datetime

OAUTH = "OAuth"


class TaxEmailConfiguration(Document):
    def _sync(self):
        if not hasattr(self, "_sync_state"):
            self._sync_state = (
                frappe.db.get_value(
                    "Tax Mailbox Sync",
                    self.name,
                    ["status", "last_sync", "last_error", "total_fetched", "consecutive_failures"],
                    as_dict=True,
                )
                if self.name and not self.is_new()
                else None
            )
        return self._sync_state

    def _oauth_missing(self):
        from accounting_firms.tax_email.oauth import has_refresh_token

        return self.auth_method == OAUTH and not (self.name and has_refresh_token(self.name))

    @property
    def sync_status(self):
        if self._oauth_missing():
            return _("⚠ OAuth غير مربوط")
        state = self._sync()
        if not self.enabled:
            return _("موقوف")
        if not state or state.status == "Never":
            return _("لم تتم بعد")
        if state.status == "Failed":
            return _("✗ فشل ({0})").format(state.consecutive_failures or 1)
        return _("✓ {0}").format(format_datetime(state.last_sync, "dd-MM HH:mm"))

    @property
    def sync_details(self):
        state = self._sync()
        lines = []
        if self._oauth_missing():
            lines.append(_("حساب OAuth غير مربوط: اضغط «ربط حساب OAuth»."))
        if not state or state.status == "Never":
            lines.append(_("لم تتم أي مزامنة بعد."))
            return "\n".join(lines)
        status = {"Success": _("ناجحة"), "Failed": _("فشلت")}.get(state.status, state.status)
        lines.append(_("آخر مزامنة: {0} ({1})").format(format_datetime(state.last_sync), status))
        lines.append(_("إجمالي الرسائل المجلوبة: {0}").format(state.total_fetched or 0))
        if state.status == "Failed":
            lines.append(_("مرات فشل متتالية: {0}").format(state.consecutive_failures or 1))
        if state.last_error:
            lines.append(state.last_error)
        return "\n".join(lines)


@frappe.whitelist()
def get_password(name, parent):
    frappe.only_for("System Manager")

    row = frappe.get_doc("Tax Email Configuration", name)
    if row.parenttype != "Customer" or row.parent != parent:
        frappe.throw("Invalid tax email configuration row.", frappe.PermissionError)

    if not frappe.has_permission("Customer", ptype="read", doc=parent):
        frappe.throw("Not permitted to read this Customer.", frappe.PermissionError)

    return row.get_password("email_password", raise_exception=False)
