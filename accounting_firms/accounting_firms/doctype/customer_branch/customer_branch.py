import frappe
from frappe import _
from frappe.model.document import Document


class CustomerBranch(Document):
    def before_insert(self):
        # runs before autoname so the document name uses the normalized code
        self._normalize_code()

    def validate(self):
        self._normalize_code()
        if not self.branch_name:
            self.branch_name = self.branch_code

        duplicate = frappe.db.exists(
            "Customer Branch",
            {"customer": self.customer, "branch_code": self.branch_code, "name": ["!=", self.name]},
        )
        if duplicate:
            frappe.throw(_("كود الفرع مستخدم بالفعل لهذا العميل."))

    def _normalize_code(self):
        code = (self.branch_code or "").strip().upper()
        if not code:
            frappe.throw(_("كود الفرع مطلوب."))
        self.branch_code = code
