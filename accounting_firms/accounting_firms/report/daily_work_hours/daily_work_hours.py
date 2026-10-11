import frappe
from frappe import _

GROUPS = {
    "الموظف": ("employee", "employee_name", "Employee"),
    "العميل": ("customer", "customer", "Customer"),
    "نوع العمل": ("work_type", "work_type", None),
}


def execute(filters=None):
    filters = frappe._dict(filters or {})
    group_by = filters.get("group_by") or "الموظف"
    key, label_field, link = GROUPS.get(group_by, GROUPS["الموظف"])

    conditions = ["summary.summary_date BETWEEN %(from_date)s AND %(to_date)s"]
    if filters.get("employee"):
        conditions.append("summary.employee = %(employee)s")
    if filters.get("customer"):
        conditions.append("item.customer = %(customer)s")
    # employees only see their own summaries
    if not any(r in frappe.get_roles() for r in ("System Manager", "HR Manager", "Accounts Manager")):
        conditions.append("summary.owner = %(user)s")
        filters["user"] = frappe.session.user

    rows = frappe.db.sql(
        f"""
        SELECT
            summary.{'employee' if key == 'employee' else 'employee'} AS employee,
            summary.employee_name,
            item.customer,
            item.work_type,
            COUNT(DISTINCT summary.name) AS days,
            COUNT(item.name) AS entries,
            SUM(item.hours) AS hours
        FROM `tabDaily Summary Item` item
        INNER JOIN `tabEmployee Daily Summary` summary ON summary.name = item.parent
        WHERE {' AND '.join(conditions)}
        GROUP BY {'summary.employee' if key == 'employee' else 'item.' + key}
        ORDER BY hours DESC
        """,
        filters,
        as_dict=True,
    )

    columns = [
        {"fieldname": key, "label": _(group_by), "fieldtype": "Link" if link else "Data", "options": link, "width": 220},
    ]
    if key == "employee":
        columns.append({"fieldname": "employee_name", "label": _("اسم الموظف"), "fieldtype": "Data", "width": 200})
    columns += [
        {"fieldname": "days", "label": _("أيام"), "fieldtype": "Int", "width": 90},
        {"fieldname": "entries", "label": _("عدد الأعمال"), "fieldtype": "Int", "width": 110},
        {"fieldname": "hours", "label": _("الساعات"), "fieldtype": "Float", "precision": 1, "width": 110},
    ]
    for r in rows:
        if key == "work_type":
            r.work_type = _(r.work_type or "")
    return columns, rows
