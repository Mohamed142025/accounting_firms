import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import cint


class TaxEmailSettings(Document):
    @property
    def oauth_redirect_uri(self):
        from accounting_firms.tax_email.oauth import redirect_uri

        return redirect_uri()

    def validate(self):
        for fieldname in ("initial_sync_days", "max_messages_per_run", "max_attachment_mb", "todo_max_age_days", "archive_older_than_days", "failure_alert_after"):
            if cint(self.get(fieldname)) < 0:
                frappe.throw(_("القيمة في «{0}» لا يمكن أن تكون سالبة.").format(_(self.meta.get_label(fieldname))))
        if self.default_assignee and not frappe.db.get_value("User", self.default_assignee, "enabled"):
            frappe.throw(_("المستخدم {0} غير مفعّل.").format(frappe.bold(self.default_assignee)))
