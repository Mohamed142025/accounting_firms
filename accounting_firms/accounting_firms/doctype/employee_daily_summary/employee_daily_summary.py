import frappe
from frappe import _
from frappe.utils import date_diff, flt, getdate, today
from frappe.model.document import Document


class EmployeeDailySummary(Document):
    MANAGER_ROLES = ("System Manager", "HR Manager", "Accounts Manager")
    EDIT_WINDOW_DAYS = 2

    def validate(self):
        self._validate_employee()
        self._validate_unique_day()
        self._validate_edit_window()
        self.total_hours = flt(sum(flt(row.hours) for row in self.work_items), 1)
        if self.total_hours > 24:
            frappe.throw(_("إجمالي ساعات اليوم لا يمكن أن يتجاوز 24 ساعة."))

    def _is_manager(self):
        return any(role in frappe.get_roles() for role in self.MANAGER_ROLES)

    def _validate_employee(self):
        if self._is_manager():
            return
        own = frappe.db.get_value("Employee", {"user_id": frappe.session.user}, "name")
        if own and self.employee != own:
            frappe.throw(_("يمكنك تسجيل ملخص يومك فقط."))

    def _validate_unique_day(self):
        duplicate = frappe.db.exists(
            "Employee Daily Summary",
            {"employee": self.employee, "summary_date": self.summary_date, "name": ["!=", self.name]},
        )
        if duplicate:
            frappe.throw(_("يوجد ملخص مسجل بالفعل لهذا الموظف في {0}.").format(frappe.format(self.summary_date)))

    def _validate_edit_window(self):
        if self.is_new() or self._is_manager():
            return
        if date_diff(today(), self.summary_date) > self.EDIT_WINDOW_DAYS:
            frappe.throw(
                _("لا يمكن تعديل الملخص بعد مرور {0} يوم من تاريخه. تواصل مع المدير.").format(self.EDIT_WINDOW_DAYS)
            )
