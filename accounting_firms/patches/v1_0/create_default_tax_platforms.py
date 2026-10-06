import frappe

# (name, login url, description) – URLs are editable from the Tax Platform list
DEFAULT_PLATFORMS = (
    ("الفاتورة الإلكترونية", "https://invoicing.eta.gov.eg/", "بوابة الفاتورة الإلكترونية - مصلحة الضرائب"),
    ("الإيصال الإلكتروني", "https://ereceipt.eta.gov.eg/", "بوابة الإيصال الإلكتروني - مصلحة الضرائب"),
    ("منظومة الضرائب الجديدة", "https://profile.eta.gov.eg/", "منظومة الإجراءات الضريبية المميكنة (الدخول بالإيميل)"),
    ("منظومة الضرائب القديمة", "https://eservices.incometax.gov.eg/", "الخدمات الإلكترونية القديمة (الدخول برقم التسجيل الضريبي)"),
    ("ضريبة المرتبات - قطاع خاص", "https://eservices.incometax.gov.eg/", "نموذج القطاع الخاص"),
    ("ضريبة المرتبات - قطاع عام", "https://eservices.incometax.gov.eg/", "نموذج القطاع العام"),
    ("مصر الرقمية", "https://digital.gov.eg/", "بوابة مصر الرقمية"),
    ("وزارة السياحة", "https://mota.gov.eg/", "البرامج السياحية - راجع الرابط"),
    ("نافذة الجمارك", "https://www.nafeza.gov.eg/", "منصة نافذة"),
)


def execute():
    frappe.reload_doc("accounting_firms", "doctype", "tax_platform")
    for name, url, description in DEFAULT_PLATFORMS:
        if frappe.db.exists("Tax Platform", name):
            continue
        frappe.get_doc(
            {
                "doctype": "Tax Platform",
                "platform_name": name,
                "login_url": url,
                "description": description,
                "status": "Active",
            }
        ).insert(ignore_permissions=True)
