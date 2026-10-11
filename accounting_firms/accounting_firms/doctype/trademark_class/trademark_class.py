import frappe
from frappe import _
from frappe.model.document import Document


class TrademarkClass(Document):
    def validate(self):
        if not (1 <= (self.class_number or 0) <= 45):
            frappe.throw(_("رقم الفئة يجب أن يكون بين 1 و 45 (تصنيف نيس)."))
