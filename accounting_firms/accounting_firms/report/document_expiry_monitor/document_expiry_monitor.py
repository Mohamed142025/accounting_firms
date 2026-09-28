import frappe
from frappe import _
from frappe.utils import date_diff, getdate, today


EXPIRY_SOURCES = (
    ("Tax Card", "tabTax Card", "expiry_date"),
    ("VAT Registration", "tabVAT Registration", "expiry_date"),
    ("License", "tabLicense", "expiry_date"),
    ("Construction Federation Membership", "tabConstruction Federation Membership", "expiry_date"),
    ("Token Data", "tabToken Data", "expiry_date"),
    ("Facilitation", "tabFacilitation", "to_date"),
    ("Advance Payment", "tabAdvance Payment", "subscription_end_date"),
)


def execute(filters=None):
    filters = frappe._dict(filters or {})
    threshold = max(int(filters.get("days_threshold") or 30), 0)
    rows = get_expiry_rows(filters.get("customer"))

    for row in rows:
        row.days_remaining = date_diff(getdate(row.expiry_date), getdate(today()))
        row.status = get_status(row.days_remaining, threshold)
        row.indicator = get_indicator(row.status)

    rows = [row for row in rows if filters.get("status") in (None, "", "All") or row.status == filters.status]
    rows.sort(key=lambda row: (row.expiry_date, row.customer_name, row.document_type))

    return get_columns(), rows, None, None, get_summary(rows)


@frappe.whitelist()
def get_customer_expiry_summary(customer):
    if not frappe.has_permission("Customer", ptype="read", doc=customer):
        frappe.throw(_("ليس لديك صلاحية قراءة بيانات هذا العميل."), frappe.PermissionError)

    rows = get_expiry_rows(customer)
    threshold = 30
    summary = {"expired": 0, "due_soon": 0, "valid": 0}
    alerts = []

    for row in rows:
        row.days_remaining = date_diff(getdate(row.expiry_date), getdate(today()))
        row.status = get_status(row.days_remaining, threshold)
        summary[{"Expired": "expired", "Due Soon": "due_soon", "Valid": "valid"}[row.status]] += 1
        if row.status != "Valid":
            alerts.append(
                {
                    "document_type": row.document_type,
                    "expiry_date": row.expiry_date,
                    "days_remaining": row.days_remaining,
                    "status": row.status,
                }
            )

    return {"summary": summary, "alerts": alerts}


def get_expiry_rows(customer=None):
    rows = []
    params = {}
    customer_clause = ""
    if customer:
        customer_clause = " AND child.parent = %(customer)s"
        params["customer"] = customer

    for document_type, table_name, expiry_field in EXPIRY_SOURCES:
        rows.extend(
            frappe.db.sql(
                f"""
                SELECT
                    child.parent AS customer,
                    customer.customer_name,
                    %(document_type)s AS document_type,
                    child.name AS document_row,
                    child.`{expiry_field}` AS expiry_date
                FROM `{table_name}` child
                INNER JOIN `tabCustomer` customer ON customer.name = child.parent
                WHERE child.parenttype = 'Customer'
                  AND child.`{expiry_field}` IS NOT NULL
                  AND child.`{expiry_field}` != ''
                  {customer_clause}
                """,
                {**params, "document_type": document_type},
                as_dict=True,
            )
        )

    return rows


def get_status(days_remaining, threshold):
    if days_remaining < 0:
        return "Expired"
    if days_remaining <= threshold:
        return "Due Soon"
    return "Valid"


def get_indicator(status):
    return {"Expired": "Red", "Due Soon": "Orange", "Valid": "Green"}[status]


def get_columns():
    return [
        {"fieldname": "customer", "label": _("العميل"), "fieldtype": "Link", "options": "Customer", "width": 210},
        {"fieldname": "customer_name", "label": _("اسم العميل"), "fieldtype": "Data", "width": 200},
        {"fieldname": "document_type", "label": _("نوع المستند"), "fieldtype": "Data", "width": 230},
        {"fieldname": "expiry_date", "label": _("تاريخ الانتهاء"), "fieldtype": "Date", "width": 130},
        {"fieldname": "days_remaining", "label": _("الأيام المتبقية"), "fieldtype": "Int", "width": 130},
        {"fieldname": "status", "label": _("الحالة"), "fieldtype": "Data", "width": 120},
        {"fieldname": "indicator", "label": _("المؤشر"), "fieldtype": "Data", "hidden": 1},
    ]


def get_summary(rows):
    counts = {"Expired": 0, "Due Soon": 0, "Valid": 0}
    for row in rows:
        counts[row.status] += 1

    return [
        {"value": counts["Expired"], "indicator": "Red", "label": _("منتهي"), "datatype": "Int"},
        {"value": counts["Due Soon"], "indicator": "Orange", "label": _("قريب الانتهاء"), "datatype": "Int"},
        {"value": counts["Valid"], "indicator": "Green", "label": _("ساري"), "datatype": "Int"},
    ]
