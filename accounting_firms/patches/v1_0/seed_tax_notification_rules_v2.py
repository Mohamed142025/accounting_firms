import frappe

from accounting_firms.tax_email.rules import ensure_rules

# Rules derived from real ETA mail: e-invoicing status digests, registration request
# decisions (SAP workflow), payment confirmations and "important alert" mails.
RULES = (
    ("رفض طلب", 15, "", "تم رفض\nرفض طلب\nمرفوض", "", "إخطارات مصلحة الضرائب", "", "عالية", 7, 1, 1, 0),
    ("قبول طلب", 16, "", "تم قبول\nقبول طلب", "", "إخطارات مصلحة الضرائب", "", "منخفضة", 0, 0, 1, 0),
    ("تنبيه هام من المصلحة", 18, "", "تنبيه هام\nتبيه هام", "", "إخطارات مصلحة الضرائب", "", "عالية", 3, 1, 1, 0),
    ("تأكيد سداد", 25, "", "payment successfully\nتم السداد\nتأكيد السداد\nإيصال سداد", "", "مطالبات وسداد", "", "منخفضة", 0, 0, 1, 0),
    ("الفاتورة الإلكترونية - تحديث حالة المستندات", 45, "invoicing.eta.gov.eg", "", "",
     "الفاتورة الإلكترونية", "الفاتورة الإلكترونية", "منخفضة", 0, 0, 1, 0),
)


def execute():
    frappe.reload_doc("accounting_firms", "doctype", "tax_notification_rule")
    ensure_rules(RULES)
