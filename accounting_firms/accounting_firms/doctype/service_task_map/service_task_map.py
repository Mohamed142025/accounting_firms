"""The tasks of an office service: what is done, in which order, and who is assigned.

Rows are numbered "1", "2", "1.1"...: "1.1" is a subtask of "1". Each row is assigned to a
department (everyone in it), a department's manager, a role (everyone holding it) or one
employee; a row may apply to some legal entities only.
"""

import re

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import cint

TASK_NO = re.compile(r"^\d+(\.\d+)*$")
ASSIGN_DEPARTMENT, ASSIGN_MANAGER, ASSIGN_ROLE, ASSIGN_EMPLOYEE = "قسم", "مدير قسم", "رول", "موظف"
MANAGER_FIELD = "af_manager"


def task_key(task_no):
    return tuple(int(p) for p in task_no.split("."))


def parent_no(task_no):
    return task_no.rsplit(".", 1)[0] if "." in task_no else None


def legal_entities():
    options = frappe.get_meta("Customer").get_options("legal_entity") or ""
    return [o.strip() for o in options.split("\n") if o.strip()]


def split_entities(value):
    return [v.strip() for v in re.split(r"[\n,،]", value or "") if v.strip()]


class ServiceTaskMap(Document):
    def validate(self):
        if not frappe.db.get_value("Item", self.service, "is_office_service"):
            frappe.throw(_("الصنف {0} مش «خدمة مكتب».").format(frappe.bold(self.service)))
        self._validate_numbers()
        entities = legal_entities()
        for row in self.tasks:
            self._validate_assignment(row)
            self._validate_entities(row, entities)

    def _validate_numbers(self):
        seen = set()
        for row in self.tasks:
            row.task_no = (row.task_no or "").strip().replace("،", ".").replace(",", ".")
            row.task_title = (row.task_title or "").strip()
            if not TASK_NO.match(row.task_no):
                frappe.throw(_("رقم المهمة «{0}» غير صحيح (صف {1}). استخدم 1، 2 أو 1.1، 1.2.").format(row.task_no, row.idx))
            if row.task_no in seen:
                frappe.throw(_("رقم المهمة {0} مكرر.").format(frappe.bold(row.task_no)))
            seen.add(row.task_no)
        for row in self.tasks:
            parent = parent_no(row.task_no)
            if parent and parent not in seen:
                frappe.throw(
                    _("المهمة {0} فرعية من {1}، والمهمة {1} مش موجودة.").format(frappe.bold(row.task_no), frappe.bold(parent))
                )
        # parents before their subtasks, in number order
        self.tasks.sort(key=lambda r: task_key(r.task_no))
        for i, row in enumerate(self.tasks, start=1):
            row.idx = i

    def _validate_assignment(self, row):
        label = _("المهمة {0}").format(frappe.bold(row.task_no))
        kind = row.assign_to_type
        if kind in (ASSIGN_DEPARTMENT, ASSIGN_MANAGER) and not row.department:
            frappe.throw(_("{0}: اختار القسم.").format(label))
        if kind == ASSIGN_MANAGER and not frappe.db.get_value("Department", row.department, MANAGER_FIELD):
            frappe.msgprint(
                _("{0}: القسم {1} مالوش مدير. حدده في شاشة القسم قبل ما تتعمل مهام على الخدمة.").format(label, frappe.bold(row.department)),
                indicator="orange",
                alert=True,
            )
        if kind == ASSIGN_ROLE:
            if not row.role:
                frappe.throw(_("{0}: اختار الرول.").format(label))
        else:
            row.role = None
        if kind == ASSIGN_EMPLOYEE:
            if not row.employee:
                frappe.throw(_("{0}: اختار الموظف.").format(label))
            employee = frappe.db.get_value("Employee", row.employee, ["user_id", "department", "employee_name"], as_dict=True)
            if not employee.user_id:
                frappe.throw(_("{0}: الموظف {1} مالوش مستخدم على النظام، فالمهمة مش هتوصله.").format(label, frappe.bold(employee.employee_name)))
            row.department = row.department or employee.department
        else:
            row.employee = None
        if cint(row.expected_days) < 0:
            row.expected_days = 0

    def _validate_entities(self, row, entities):
        chosen = split_entities(row.applies_to)
        unknown = [e for e in chosen if e not in entities]
        if unknown:
            frappe.throw(
                _("المهمة {0}: «{1}» مش من الكيانات القانونية ({2}).").format(
                    frappe.bold(row.task_no), "، ".join(unknown), "، ".join(entities)
                )
            )
        row.applies_to = "\n".join(chosen)


@frappe.whitelist()
def get_legal_entities():
    return legal_entities()
