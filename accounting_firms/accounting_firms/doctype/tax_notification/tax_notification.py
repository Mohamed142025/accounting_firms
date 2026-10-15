import frappe
from frappe.desk.form.assign_to import close_all_assignments
from frappe.model.document import Document
from frappe.utils import getdate, now_datetime, today

OPEN_STATUSES = ("جديد", "تحت المراجعة")


class TaxNotification(Document):
    @property
    def is_overdue(self):
        return bool(
            self.due_date
            and self.status in OPEN_STATUSES
            and getdate(self.due_date) < getdate(today())
        )

    def validate(self):
        self._track_handling()

    def _track_handling(self):
        """Who closed the notification and when; reopening clears it."""
        if self.status in OPEN_STATUSES:
            self.handled_by = self.handled_at = None
        elif self.is_new() or self.has_value_changed("status"):
            # notifications archived by a rule while fetching were not handled by anyone
            if not self.flags.from_fetch:
                self.handled_by = frappe.session.user
                self.handled_at = now_datetime()

    def on_update(self):
        if self.status not in OPEN_STATUSES and self.has_value_changed("status"):
            close_all_assignments(self.doctype, self.name, ignore_permissions=True)


@frappe.whitelist()
def set_status(names, status):
    """List / form action: move notifications to a status."""
    if status not in (*OPEN_STATUSES, "تم التعامل", "مؤرشف"):
        frappe.throw(frappe._("حالة غير صحيحة."))
    names = frappe.parse_json(names) if isinstance(names, str) and names.startswith("[") else names
    names = [names] if isinstance(names, str) else names
    changed = 0
    for name in names:
        doc = frappe.get_doc("Tax Notification", name)
        doc.check_permission("write")
        if doc.status != status:
            doc.status = status
            doc.save()
            changed += 1
    return {"changed": changed}
