import frappe
from frappe import _
from frappe.model.document import Document


class TaxPlatform(Document):
    def validate(self):
        url = (self.login_url or "").strip()
        if url and not url.lower().startswith(("http://", "https://")):
            frappe.throw(_("رابط صفحة الدخول يجب أن يبدأ بـ http:// أو https://"))
        self.login_url = url
