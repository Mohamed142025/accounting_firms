import frappe
from frappe import _
from frappe.utils import date_diff, getdate, today


# (label, child table, expiry field, parentfield restriction or None)
EXPIRY_SOURCES = (
    ("البطاقة الضريبية", "tabTax Card", "expiry_date", None),
    ("القيمة المضافة", "tabVAT Registration", "expiry_date", None),
    ("الرخص", "tabLicense", "expiry_date", None),
    ("اتحاد التشييد والبناء", "tabConstruction Federation Membership", "expiry_date", None),
    ("البطاقة الاستيرادية", "tabImport Export Card", "expiry_date", "import_cards"),
    ("البطاقة التصديرية", "tabImport Export Card", "expiry_date", "export_cards"),
    ("بيانات التوكن", "tabToken Data", "expiry_date", None),
    ("التيسرات", "tabFacilitation", "to_date", None),
    ("الدفعات المقدمة", "tabAdvance Payment", "subscription_end_date", None),
)


def execute(filters=None):
    filters = frappe._dict(filters or {})
    threshold = max(int(filters.get("days_threshold") or 30), 0)
    rows = get_expiry_rows(filters.get("customer"), filters.get("branch"))

    for row in rows:
        row.days_remaining = date_diff(getdate(row.expiry_date), getdate(today()))
        row.status = get_status(row.days_remaining, threshold)
        row.indicator = get_indicator(row.status)

    rows = [row for row in rows if filters.get("status") in (None, "", "All") or row.status == filters.status]
    if filters.get("from_date"):
        rows = [row for row in rows if getdate(row.expiry_date) >= getdate(filters.from_date)]
    if filters.get("to_date"):
        rows = [row for row in rows if getdate(row.expiry_date) <= getdate(filters.to_date)]
    rows.sort(key=lambda row: (row.expiry_date, row.customer_name or "", row.document_type))

    return get_columns(), rows, None, get_chart(rows, filters), get_summary(rows)


def get_chart(rows, filters):
    """Stacked bars per month of expiry (Expired / Due Soon / Valid)."""
    statuses = (("Expired", _("منتهي")), ("Due Soon", _("قريب الانتهاء")), ("Valid", _("ساري")))
    months = month_labels(filters.get("from_date"), filters.get("to_date"), [r.expiry_date for r in rows])
    counts = {status: {m: 0 for m in months} for status, _label in statuses}
    for row in rows:
        key = month_key(row.expiry_date)
        if key in counts[row.status]:
            counts[row.status][key] += 1
    return {
        "data": {
            "labels": months,
            "datasets": [{"name": label, "values": [counts[status][m] for m in months]} for status, label in statuses],
        },
        "type": "bar",
        "fieldtype": "Int",
    }


def month_key(value):
    d = getdate(value)
    return f"{d.month:02d}/{d.year}"


def month_labels(from_date, to_date, dates):
    """Consecutive month labels covering the filter range (or the data range)."""
    from frappe.utils import add_months

    valid = [getdate(d) for d in dates if d]
    start = getdate(from_date) if from_date else (min(valid) if valid else getdate(today()))
    end = getdate(to_date) if to_date else (max(valid) if valid else getdate(today()))
    labels = []
    current = start.replace(day=1)
    while current <= end and len(labels) < 36:
        labels.append(month_key(current))
        current = add_months(current, 1)
    return labels or [month_key(today())]


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
                    "branch": row.branch,
                    "expiry_date": row.expiry_date,
                    "days_remaining": row.days_remaining,
                    "status": row.status,
                }
            )

    return {"summary": summary, "alerts": alerts}


def get_expiry_rows(customer=None, branch=None):
    rows = []
    params = {}
    extra_clause = ""
    if customer:
        extra_clause += " AND child.parent = %(customer)s"
        params["customer"] = customer
    if branch:
        extra_clause += " AND child.branch = %(branch)s"
        params["branch"] = branch

    for document_type, table_name, expiry_field, parentfield in EXPIRY_SOURCES:
        parentfield_clause = ""
        query_params = {**params, "document_type": document_type}
        if parentfield:
            parentfield_clause = " AND child.parentfield = %(parentfield)s"
            query_params["parentfield"] = parentfield

        rows.extend(
            frappe.db.sql(
                f"""
                SELECT
                    child.parent AS customer,
                    customer.customer_name,
                    %(document_type)s AS document_type,
                    child.branch AS branch,
                    branch.branch_name AS branch_name,
                    child.name AS document_row,
                    child.`{expiry_field}` AS expiry_date
                FROM `{table_name}` child
                INNER JOIN `tabCustomer` customer ON customer.name = child.parent
                LEFT JOIN `tabCustomer Branch` branch ON branch.name = child.branch
                WHERE child.parenttype = 'Customer'
                  AND child.`{expiry_field}` IS NOT NULL
                  AND child.`{expiry_field}` != ''
                  {parentfield_clause}
                  {extra_clause}
                """,
                query_params,
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
        {"fieldname": "customer", "label": _("العميل"), "fieldtype": "Link", "options": "Customer", "width": 180},
        {"fieldname": "customer_name", "label": _("اسم العميل"), "fieldtype": "Data", "width": 200},
        {"fieldname": "branch", "label": _("الفرع"), "fieldtype": "Link", "options": "Customer Branch", "width": 150},
        {"fieldname": "branch_name", "label": _("اسم الفرع"), "fieldtype": "Data", "width": 150},
        {"fieldname": "document_type", "label": _("نوع المستند"), "fieldtype": "Data", "width": 200},
        {"fieldname": "expiry_date", "label": _("تاريخ الانتهاء"), "fieldtype": "Date", "width": 130},
        {"fieldname": "days_remaining", "label": _("الأيام المتبقية"), "fieldtype": "Int", "width": 120},
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
