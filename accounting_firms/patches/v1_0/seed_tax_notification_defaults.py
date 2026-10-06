import frappe

CATEGORIES = (
    "فحص ضريبي",
    "مطالبات وسداد",
    "إقرارات ضريبية",
    "الفاتورة الإلكترونية",
    "الإيصال الإلكتروني",
    "بيانات الدخول ورموز التحقق",
    "إخطارات مصلحة الضرائب",
    "أخرى",
)

# name, sequence, sender, subject keywords, body keywords, category, tax type, priority, due days, todo, assign, archive
RULES = (
    ("رموز التحقق وكلمات المرور", 10, "", "رمز التحقق\nكلمة المرور\nكلمة السر\nOTP\nverification code\npassword\nreset", "",
     "بيانات الدخول ورموز التحقق", "", "منخفضة", 0, 0, 0, 0),
    ("فحص ضريبي", 20, "", "فحص\nنموذج 19\nنموذج 15\nلجنة داخلية\nلجنة الطعن", "", "فحص ضريبي", "", "عالية", 7, 1, 1, 0),
    ("مطالبات وسداد", 30, "", "مطالبة\nسداد\nمديونية\nمتأخرات\nحجز\nغرامة\nمقابل التأخير", "", "مطالبات وسداد", "", "عالية", 5, 1, 1, 0),
    ("إقرارات ضريبية", 40, "", "إقرار\nالإقرار الضريبي\nتقديم الإقرار", "", "إقرارات ضريبية", "", "متوسطة", 10, 1, 1, 0),
    ("الفاتورة الإلكترونية", 50, "", "فاتورة إلكترونية\nالفاتورة الإلكترونية\ne-invoice\neinvoice\ninvoicing", "",
     "الفاتورة الإلكترونية", "الفاتورة الإلكترونية", "متوسطة", 0, 0, 1, 0),
    ("الإيصال الإلكتروني", 60, "", "إيصال إلكتروني\nالإيصال الإلكتروني\ne-receipt\nereceipt", "",
     "الإيصال الإلكتروني", "الإيصال الإلكتروني", "متوسطة", 0, 0, 1, 0),
    ("نوع الضريبة: المرتبات", 70, "", "مرتبات\nالأجور\nكسب العمل\npayroll", "", "", "المرتبات", "متوسطة", 0, 0, 1, 0),
    ("نوع الضريبة: القيمة المضافة", 80, "", "القيمة المضافة\nVAT", "", "", "القيمة المضافة", "متوسطة", 0, 0, 1, 0),
    ("نوع الضريبة: الخصم والتحصيل", 85, "", "الخصم والتحصيل\nخصم وتحصيل\nنموذج 41", "", "", "الخصم والتحصيل", "متوسطة", 0, 0, 1, 0),
    ("رسائل مصلحة الضرائب", 90, "eta.gov.eg\nincometax.gov.eg\ntax.gov.eg", "", "", "إخطارات مصلحة الضرائب", "", "متوسطة", 0, 0, 1, 0),
)

MAIL_SERVERS = (("mail.inmotionhosting.com", 993, 1),)


def execute():
    for doctype in (
        "mail_server",
        "tax_notification_category",
        "tax_notification_rule",
        "tax_email_settings",
    ):
        frappe.reload_doc("accounting_firms", "doctype", doctype)

    for name in CATEGORIES:
        if not frappe.db.exists("Tax Notification Category", name):
            frappe.get_doc({"doctype": "Tax Notification Category", "category_name": name}).insert(ignore_permissions=True)

    for name, seq, sender, subject, body, category, tax_type, priority, due, todo, assign, archive in RULES:
        if frappe.db.exists("Tax Notification Rule", name):
            continue
        frappe.get_doc(
            {
                "doctype": "Tax Notification Rule",
                "rule_name": name,
                "enabled": 1,
                "sequence": seq,
                "sender_contains": sender,
                "subject_keywords": subject,
                "body_keywords": body,
                "category": category or None,
                "tax_type": tax_type,
                "priority": priority,
                "due_in_days": due,
                "create_todo": todo,
                "assign_to_accountant": assign,
                "auto_archive": archive,
            }
        ).insert(ignore_permissions=True)

    for host, port, use_ssl in MAIL_SERVERS:
        if not frappe.db.exists("Mail Server", host):
            frappe.get_doc(
                {"doctype": "Mail Server", "server_host": host, "port": port, "use_ssl": use_ssl}
            ).insert(ignore_permissions=True)

    settings = frappe.get_doc("Tax Email Settings")
    if not settings.initial_sync_days:
        settings.update(
            {
                "enabled": 1,
                "initial_sync_days": 30,
                "max_messages_per_run": 50,
                "fetch_attachments": 1,
                "max_attachment_mb": 10,
                "todo_max_age_days": 7,
            }
        )
        settings.save(ignore_permissions=True)
