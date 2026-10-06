"""Read-only IMAP reader for customers' tax mailboxes.

Messages are fetched with BODY.PEEK on a read-only INBOX, so nothing is marked as
read, moved or deleted in the customer's mailbox.
"""

import hashlib
import imaplib
import socket
from email.header import decode_header, make_header
from email.utils import parseaddr

import frappe
from frappe import _
from frappe.email.receive import Email
from frappe.utils import add_days, add_to_date, cint, escape_html, get_datetime, getdate, now_datetime, strip_html, today
from frappe.utils.html_utils import clean_email_html
from frappe.utils.password import get_decrypted_password

from accounting_firms.tax_email.rules import apply_rules, get_rules

MONTHS = ("Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec")
ROW_FIELDS = ["name", "parent", "branch", "tax_email", "incoming_server", "port", "enabled"]
CONNECT_TIMEOUT = 30
FAILED_RETRY_HOURS = 6


# ---------------------------------------------------------------------------- helpers
def get_settings():
    doc = frappe.get_cached_doc("Tax Email Settings")
    return frappe._dict(
        enabled=cint(doc.enabled) if doc.enabled is not None else 1,
        initial_sync_days=cint(doc.initial_sync_days) or 30,
        max_messages_per_run=cint(doc.max_messages_per_run) or 50,
        fetch_attachments=cint(doc.fetch_attachments) if doc.fetch_attachments is not None else 1,
        max_attachment_mb=cint(doc.max_attachment_mb) or 10,
        todo_max_age_days=cint(doc.todo_max_age_days) or 7,
    )


def get_row(name, parent=None):
    row = frappe.db.get_value(
        "Tax Email Configuration", {"name": name, "parenttype": "Customer"}, ROW_FIELDS, as_dict=True
    )
    if not row or (parent and row.parent != parent):
        frappe.throw(_("صف الإيميل الضريبي غير موجود. احفظ العميل أولاً."))
    return row


def get_state(row):
    if frappe.db.exists("Tax Mailbox Sync", row.name):
        return frappe.get_doc("Tax Mailbox Sync", row.name)
    state = frappe.new_doc("Tax Mailbox Sync")
    state.update({"config_row": row.name, "customer": row.parent, "tax_email": row.tax_email, "status": "Never"})
    state.flags.ignore_permissions = True
    state.insert(ignore_permissions=True)
    return state


def save_state(state, **values):
    values.setdefault("last_sync", now_datetime())
    frappe.db.set_value("Tax Mailbox Sync", state.name, values, update_modified=True)


def friendly_error(error):
    text = str(error)
    if isinstance(error, imaplib.IMAP4.error):
        if any(word in text.upper() for word in ("AUTH", "LOGIN", "CREDENTIAL", "PASSWORD")):
            return _("فشل تسجيل الدخول: اسم المستخدم أو كلمة المرور غير صحيحة. ({0})").format(text)
        return _("خطأ من سيرفر البريد: {0}").format(text)
    if isinstance(error, socket.gaierror):
        return _("عنوان السيرفر غير صحيح أو غير متاح: {0}").format(text)
    if isinstance(error, (socket.timeout, TimeoutError)):
        return _("انتهت مهلة الاتصال بالسيرفر.")
    if isinstance(error, (ConnectionError, OSError)):
        return _("تعذر الاتصال بالسيرفر: {0}").format(text)
    return text


def connect(row):
    password = get_decrypted_password("Tax Email Configuration", row.name, "email_password", raise_exception=False)
    if not (row.incoming_server and row.tax_email and password):
        frappe.throw(_("بيانات الإيميل ناقصة: السيرفر والإيميل وكلمة المرور مطلوبين."))

    server = frappe.db.get_value("Mail Server", row.incoming_server, ["server_host", "port", "use_ssl"], as_dict=True)
    host = (server.server_host if server else row.incoming_server).strip()
    port = cint(row.port) or cint(server.port if server else 0) or 993
    use_ssl = cint(server.use_ssl) if server else 1

    conn = (
        imaplib.IMAP4_SSL(host, port, timeout=CONNECT_TIMEOUT)
        if use_ssl
        else imaplib.IMAP4(host, port, timeout=CONNECT_TIMEOUT)
    )
    conn.login(row.tax_email, password)
    return conn


def close(conn):
    try:
        conn.logout()
    except Exception:
        pass


def select_inbox(conn):
    status, data = conn.select("INBOX", readonly=True)
    if status != "OK":
        raise imaplib.IMAP4.error(f"cannot open INBOX: {data}")
    total = cint(data[0])
    validity = conn.response("UIDVALIDITY")[1]
    validity = validity[0].decode() if validity and validity[0] else ""
    return total, validity


def search_new_uids(conn, state, validity, settings):
    last_uid = cint(state.last_uid) if state.uid_validity == validity else 0
    if last_uid:
        status, data = conn.uid("search", None, "UID", f"{last_uid + 1}:*")
    else:
        since = add_days(getdate(today()), -settings.initial_sync_days)
        status, data = conn.uid("search", None, "SINCE", f"{since.day:02d}-{MONTHS[since.month - 1]}-{since.year}")
    if status != "OK":
        raise imaplib.IMAP4.error(f"search failed: {data}")
    # "n:*" always returns the newest message even when its UID is below n
    return sorted(uid for uid in (cint(u) for u in (data[0] or b"").split()) if uid > last_uid)


# ---------------------------------------------------------------------------- notifications
def get_accountant_user(customer):
    employee = frappe.db.get_value("Customer", customer, "accountant")
    return frappe.db.get_value("Employee", employee, "user_id") if employee else None


def get_sender(mail):
    """Real sender from the From header (Email() prefers Reply-To, which hides the authority's address)."""
    try:
        name, address = parseaddr(str(make_header(decode_header(mail.mail.get("From") or ""))))
    except Exception:
        name, address = "", ""
    return (address or mail.from_email or "").lower(), name or mail.from_real_name or ""


def make_body(mail):
    if mail.html_content:
        html = clean_email_html(mail.html_content)
        text = mail.text_content or strip_html(mail.html_content)
    else:
        text = mail.text_content or ""
        html = escape_html(text).replace("\n", "<br>")
    return html, text[:200000]


def save_attachments(doc, mail, settings):
    saved = 0
    limit = settings.max_attachment_mb * 1024 * 1024
    for attachment in mail.attachments or []:
        content = attachment.get("fcontent")
        if not content or len(content) > limit:
            continue
        try:
            frappe.get_doc(
                {
                    "doctype": "File",
                    "file_name": attachment.get("fname") or "attachment",
                    "content": content,
                    "attached_to_doctype": doc.doctype,
                    "attached_to_name": doc.name,
                    "is_private": 1,
                }
            ).insert(ignore_permissions=True)
            saved += 1
        except Exception:
            # an unsupported / unsafe attachment must not block the notification itself
            frappe.log_error(title=f"Tax notification attachment skipped: {attachment.get('fname')}")
    return saved


def create_notification(row, uid, raw, settings, rules):
    """Store one message. Returns the new document, or None when it already exists."""
    mail = Email(raw)
    key = mail.message_id or f"{uid}|{mail.date}|{mail.subject}"
    message_hash = hashlib.sha1(f"{row.tax_email}|{key}".encode()).hexdigest()
    if frappe.db.exists("Tax Notification", {"message_hash": message_hash}):
        return None

    html, text = make_body(mail)
    sender, sender_name = get_sender(mail)
    doc = frappe.new_doc("Tax Notification")
    doc.update(
        {
            "subject": (mail.subject or _("بدون عنوان"))[:255],
            "customer": row.parent,
            "branch": row.branch,
            "tax_email": row.tax_email,
            "sender": sender[:255],
            "sender_name": sender_name[:255],
            "received_at": mail.date,
            "body": html,
            "body_text": text,
            "has_attachments": 1 if mail.attachments else 0,
            "message_hash": message_hash,
            "imap_uid": uid,
            "status": "جديد",
            "priority": "متوسطة",
        }
    )

    rule = apply_rules(doc, rules)
    if not rule or cint(rule.assign_to_accountant):
        doc.assigned_to = get_accountant_user(row.parent)

    doc.insert(ignore_permissions=True)

    if settings.fetch_attachments and mail.attachments:
        save_attachments(doc, mail, settings)

    is_recent = getdate(doc.received_at) >= add_days(getdate(today()), -settings.todo_max_age_days)
    if rule and cint(rule.create_todo) and doc.assigned_to and is_recent and doc.status != "مؤرشف":
        create_todo(doc)
    return doc


def create_todo(doc):
    from frappe.desk.form.assign_to import add as assign

    try:
        assign(
            {
                "assign_to": [doc.assigned_to],
                "doctype": doc.doctype,
                "name": doc.name,
                "description": _("إشعار ضريبي للعميل {0}: {1}").format(doc.customer_name or doc.customer, doc.subject),
                "date": doc.due_date,
            }
        )
    except Exception:
        frappe.log_error(title=f"Tax notification ToDo failed: {doc.name}")


# ---------------------------------------------------------------------------- fetching
def fetch_mailbox(config_name, limit=None):
    """Fetch new messages of one mailbox. Returns a summary dict and never raises."""
    settings = get_settings()
    row = get_row(config_name)
    state = get_state(row)
    limit = cint(limit) or settings.max_messages_per_run
    summary = frappe._dict(ok=False, fetched=0, skipped=0, remaining=0, error=None)
    conn = None
    last_uid = cint(state.last_uid)

    try:
        conn = connect(row)
        _total, validity = select_inbox(conn)
        if state.uid_validity != validity:
            last_uid = 0
        uids = search_new_uids(conn, state, validity, settings)
        batch, summary.remaining = uids[:limit], max(len(uids) - limit, 0)
        rules = get_rules()

        for uid in batch:
            status, data = conn.uid("fetch", str(uid), "(BODY.PEEK[])")
            raw = next((part[1] for part in data or [] if isinstance(part, tuple)), None)
            if status != "OK" or not raw:
                summary.skipped += 1
                continue
            try:
                if create_notification(row, uid, raw, settings, rules):
                    summary.fetched += 1
                else:
                    summary.skipped += 1
            except Exception:
                frappe.db.rollback()
                frappe.log_error(title=f"Tax notification parse failed: {row.tax_email} UID {uid}")
                summary.skipped += 1
            last_uid = max(last_uid, uid)
            # commit per message so a later failure never loses stored mail
            save_state(state, last_uid=last_uid, uid_validity=validity)
            frappe.db.commit()

        save_state(
            state,
            status="Success",
            last_error="",
            last_uid=last_uid,
            uid_validity=validity,
            customer=row.parent,
            tax_email=row.tax_email,
            total_fetched=cint(state.total_fetched) + summary.fetched,
        )
        summary.ok = True
    except Exception as error:
        frappe.db.rollback()
        summary.error = friendly_error(error)
        save_state(state, status="Failed", last_error=summary.error[:1000], customer=row.parent, tax_email=row.tax_email)
    finally:
        if conn:
            close(conn)
        frappe.db.commit()
    return summary


def fetch_all():
    """Scheduler entry point: one background job per enabled mailbox."""
    if not get_settings().enabled:
        return
    rows = frappe.db.sql(
        """
        SELECT cfg.name
        FROM `tabTax Email Configuration` cfg
        INNER JOIN `tabCustomer` customer ON customer.name = cfg.parent
        LEFT JOIN `tabTax Mailbox Sync` state ON state.name = cfg.name
        WHERE cfg.parenttype = 'Customer'
          AND cfg.enabled = 1
          AND IFNULL(cfg.tax_email, '') != ''
          AND IFNULL(cfg.incoming_server, '') != ''
          AND customer.disabled = 0
          -- back off after a failure (e.g. wrong password) so the mail provider does not lock the account
          AND NOT (IFNULL(state.status, '') = 'Failed' AND state.last_sync > %(retry_after)s)
        """,
        {"retry_after": add_to_date(now_datetime(), hours=-FAILED_RETRY_HOURS)},
        pluck=True,
    )
    for name in rows:
        frappe.enqueue(
            "accounting_firms.tax_email.fetch.fetch_mailbox",
            queue="long",
            timeout=900,
            job_id=f"tax_mailbox::{name}",
            deduplicate=True,
            config_name=name,
        )


# ---------------------------------------------------------------------------- form actions
def _check_customer(parent):
    if not frappe.has_permission("Customer", ptype="write", doc=parent):
        frappe.throw(_("ليس لديك صلاحية على هذا العميل."), frappe.PermissionError)


@frappe.whitelist()
def test_connection(name, parent):
    _check_customer(parent)
    row = get_row(name, parent)
    conn = None
    try:
        conn = connect(row)
        total, _validity = select_inbox(conn)
        return {"ok": True, "messages": total}
    except frappe.ValidationError:
        raise
    except Exception as error:
        return {"ok": False, "error": friendly_error(error)}
    finally:
        if conn:
            close(conn)


@frappe.whitelist()
def fetch_now(name, parent):
    _check_customer(parent)
    row = get_row(name, parent)
    # keep the request short; the scheduler picks up whatever remains
    return fetch_mailbox(row.name, limit=15)


@frappe.whitelist()
def get_customer_summary(customer):
    if not frappe.has_permission("Customer", ptype="read", doc=customer):
        frappe.throw(_("ليس لديك صلاحية قراءة بيانات هذا العميل."), frappe.PermissionError)
    open_filters = {"customer": customer, "status": ["in", ["جديد", "تحت المراجعة"]]}
    return {
        "new": frappe.db.count("Tax Notification", {"customer": customer, "status": "جديد"}),
        "overdue": frappe.db.count("Tax Notification", {**open_filters, "due_date": ["<", today()]}),
        "high": frappe.db.count("Tax Notification", {**open_filters, "priority": "عالية"}),
    }
