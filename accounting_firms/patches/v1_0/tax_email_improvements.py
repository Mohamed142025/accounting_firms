"""Tax email improvements (2026-10):

- notifications of the first sync older than the archive age are archived without a due
  date, so a year of old mail is not "overdue";
- the stored plain text of HTML mail no longer carries the mail's stylesheet;
- rules that read the message body, and the Gmail / Microsoft 365 mail servers.
"""

from html import unescape

import frappe
from frappe.utils import add_days, cint

from accounting_firms.tax_email.fetch import html_to_text
from accounting_firms.tax_email.rules import ensure_rules

# (name, sequence, sender, subject keywords, body keywords, category, tax type, priority,
#  due days, create todo, assign, auto archive)
BODY_RULES = (
    ("مساهمة تكافلية", 17, "", "", "المساهمة التكافلية\nالتأمين الصحي الشامل", "مطالبات وسداد", "أخرى", "عالية", 7, 1, 1, 0),
    ("فحص ضريبي (من نص الرسالة)", 86, "", "", "نموذج 19\nنموذج 15\nلجنة داخلية\nلجنة الطعن\nإخطار بالفحص\nإخطار فحص", "فحص ضريبي", "", "عالية", 7, 1, 1, 0),
    ("مطالبات وسداد (من نص الرسالة)", 87, "", "", "يتوجب عليكم سداد\nمقابل التأخير\nحجز إداري\nمديونية مستحقة\nمستحقات متأخرة", "مطالبات وسداد", "", "عالية", 5, 1, 1, 0),
    ("إقرارات ضريبية (من نص الرسالة)", 88, "", "", "موعد تقديم الإقرار\nعدم تقديم الإقرار\nتقديم الإقرار الضريبي", "إقرارات ضريبية", "", "متوسطة", 10, 1, 1, 0),
)

MAIL_SERVERS = ("imap.gmail.com", "outlook.office365.com")


def execute():
    frappe.reload_doc("accounting_firms", "doctype", "tax_notification")
    frappe.reload_doc("accounting_firms", "doctype", "tax_email_settings")
    frappe.reload_doc("accounting_firms", "doctype", "tax_mailbox_sync")

    days = cint(frappe.db.get_single_value("Tax Email Settings", "archive_older_than_days"))
    if not days:
        days = 30
        frappe.db.set_single_value("Tax Email Settings", "archive_older_than_days", days)

    # a message that was already old when it was fetched
    old = frappe.db.sql(
        """select name from `tabTax Notification`
        where status in ('جديد', 'تحت المراجعة') and received_at is not null
          and date(received_at) < date(creation) - interval %s day""",
        days,
        pluck=True,
    )
    for name in old:
        frappe.db.set_value("Tax Notification", name, {"status": "مؤرشف", "due_date": None}, update_modified=False)
        frappe.db.set_value(
            "ToDo", {"reference_type": "Tax Notification", "reference_name": name, "status": "Open"}, "status", "Closed"
        )

    for name, body in frappe.db.sql("select name, body from `tabTax Notification` where ifnull(body, '') != ''"):
        text = unescape(html_to_text(body)).replace("\xa0", " ")[:200000]
        frappe.db.set_value("Tax Notification", name, "body_text", text, update_modified=False)

    ensure_rules(BODY_RULES)

    for host in MAIL_SERVERS:
        if not frappe.db.exists("Mail Server", host):
            frappe.get_doc(
                {"doctype": "Mail Server", "server_host": host, "port": 993, "use_ssl": 1, "status": "Active"}
            ).insert(ignore_permissions=True)
