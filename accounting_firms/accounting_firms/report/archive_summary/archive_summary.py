import frappe
from frappe import _
from frappe.utils import add_days


def execute(filters=None):
    filters = frappe._dict(filters or {})
    conditions = {}
    if filters.get("customer"):
        conditions["customer"] = filters.customer
    if filters.get("from_date") and filters.get("to_date"):
        conditions["uploaded_on"] = ["between", [filters.from_date, add_days(filters.to_date, 1)]]
    elif filters.get("from_date"):
        conditions["uploaded_on"] = [">=", filters.from_date]
    elif filters.get("to_date"):
        conditions["uploaded_on"] = ["<", add_days(filters.to_date, 1)]

    where, values = ["1=1"], {}
    if conditions.get("customer"):
        where.append("customer = %(customer)s"); values["customer"] = conditions["customer"]
    if filters.get("from_date"):
        where.append("uploaded_on >= %(from_date)s"); values["from_date"] = filters.from_date
    if filters.get("to_date"):
        where.append("uploaded_on < %(to_date)s"); values["to_date"] = add_days(filters.to_date, 1)
    rows = frappe.db.sql(
        f"""
        SELECT customer, customer_name, folder, folder_name,
               COUNT(name) AS files, SUM(file_size) AS size, MAX(uploaded_on) AS last_upload
        FROM `tabCustomer Document`
        WHERE {' AND '.join(where)}
        GROUP BY customer, folder
        ORDER BY customer ASC, files DESC
        """,
        values,
        as_dict=True,
    )
    for r in rows:
        r.size_mb = round((r.size or 0) / (1024 * 1024), 2)
    columns = [
        {"fieldname": "customer", "label": _("العميل"), "fieldtype": "Link", "options": "Customer", "width": 140},
        {"fieldname": "customer_name", "label": _("اسم العميل"), "fieldtype": "Data", "width": 200},
        {"fieldname": "folder", "label": _("المجلد"), "fieldtype": "Link", "options": "Customer Archive Folder", "width": 120},
        {"fieldname": "folder_name", "label": _("اسم المجلد"), "fieldtype": "Data", "width": 220},
        {"fieldname": "files", "label": _("عدد الملفات"), "fieldtype": "Int", "width": 100},
        {"fieldname": "size_mb", "label": _("الحجم (ميجابايت)"), "fieldtype": "Float", "precision": 2, "width": 120},
        {"fieldname": "last_upload", "label": _("آخر رفع"), "fieldtype": "Datetime", "width": 160},
    ]
    return columns, rows
