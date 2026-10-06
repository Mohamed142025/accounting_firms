import frappe
from frappe.utils import getdate, today
from frappe.model.document import Document


class TaxNotification(Document):
    @property
    def is_overdue(self):
        return bool(
            self.due_date
            and self.status in ("جديد", "تحت المراجعة")
            and getdate(self.due_date) < getdate(today())
        )
