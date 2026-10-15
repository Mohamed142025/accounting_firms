"""Read-only IMAP reader for customers' tax mailboxes.

Messages are fetched with BODY.PEEK on read-only folders, so nothing is marked as
read, moved or deleted in the customer's mailbox.

Each mailbox reads its INBOX, the Spam / Junk folder (Tax Email Settings) and the extra
folders on its row, each from where it stopped last time. A mailbox is read once every
"fetch_interval_minutes"; the scheduler only checks every 5 minutes which ones are due.
"""

import base64
import hashlib
import imaplib
import json
import re
import socket
from email.header import decode_header, make_header
from email.utils import parseaddr
from html import unescape

import frappe
from frappe import _
from frappe.email.receive import Email
from frappe.utils import (
    add_days,
    add_to_date,
    cint,
    escape_html,
    getdate,
    now_datetime,
    strip_html,
    today,
)
from frappe.utils.html_utils import clean_email_html
from frappe.utils.password import get_decrypted_password

from accounting_firms.tax_email import oauth
from accounting_firms.tax_email.rules import apply_rules, get_rules

MONTHS = ("Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec")
ROW_FIELDS = [
    "name",
    "parent",
    "branch",
    "tax_email",
    "incoming_server",
    "port",
    "enabled",
    "auth_method",
    "connected_app",
    "extra_folders",
]
OAUTH = "OAuth"
INBOX = "INBOX"
CONNECT_TIMEOUT = 30
FAILED_RETRY_HOURS = 6
ARCHIVED = "مؤرشف"
JUNK_NAMES = {"spam", "junk", "junk e-mail", "junk email", "bulk mail", "bulk", "البريد العشوائي", "البريد غير الهام"}
_NON_TEXT = re.compile(r"<(style|script|head|title)\b[^>]*>.*?</\1\s*>", re.IGNORECASE | re.DOTALL)
_LIST_LINE = re.compile(r'^\((?P<flags>[^)]*)\)\s+(?P<delim>"(?:[^"\\]|\\.)*"|NIL)\s+(?P<name>.+)$')


# ---------------------------------------------------------------------------- helpers
def get_settings():
    doc = frappe.get_cached_doc("Tax Email Settings")

    def value(fieldname, default):
        # an empty Int reads as 0; only None (never saved) falls back
        return cint(doc.get(fieldname)) if doc.get(fieldname) is not None else default

    return frappe._dict(
        enabled=value("enabled", 1),
        initial_sync_days=cint(doc.initial_sync_days) or 30,
        max_messages_per_run=cint(doc.max_messages_per_run) or 50,
        fetch_attachments=value("fetch_attachments", 1),
        max_attachment_mb=cint(doc.max_attachment_mb) or 10,
        todo_max_age_days=cint(doc.todo_max_age_days) or 7,
        fetch_interval_minutes=cint(doc.get("fetch_interval_minutes")) or 30,
        read_junk_folder=value("read_junk_folder", 1),
        archive_older_than_days=value("archive_older_than_days", 30),
        default_assignee=doc.get("default_assignee"),
        failure_alert_after=value("failure_alert_after", 2),
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
    if isinstance(error, oauth.OAuthError):
        return text
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


def open_connection(host, port, use_ssl):
    if use_ssl:
        return imaplib.IMAP4_SSL(host, port, timeout=CONNECT_TIMEOUT)
    return imaplib.IMAP4(host, port, timeout=CONNECT_TIMEOUT)


def connect(row):
    use_oauth = row.auth_method == OAUTH
    password = None
    if not use_oauth:
        password = get_decrypted_password("Tax Email Configuration", row.name, "email_password", raise_exception=False)
    if not (row.incoming_server and row.tax_email and (use_oauth or password)):
        frappe.throw(_("بيانات الإيميل ناقصة: السيرفر والإيميل وكلمة المرور مطلوبين."))

    server = frappe.db.get_value("Mail Server", row.incoming_server, ["server_host", "port", "use_ssl"], as_dict=True)
    host = (server.server_host if server else row.incoming_server).strip()
    port = cint(row.port) or cint(server.port if server else 0) or 993
    use_ssl = cint(server.use_ssl) if server else 1

    if use_oauth:
        # the token is fetched before connecting, so a revoked link fails without a login attempt
        token = oauth.get_access_token(row)
        conn = open_connection(host, port, use_ssl)
        try:
            conn.authenticate("XOAUTH2", lambda _challenge: oauth.xoauth2(row.tax_email, token))
        except imaplib.IMAP4.error:
            oauth.forget_access_token(row.name)
            close(conn)
            raise
        return conn

    conn = open_connection(host, port, use_ssl)
    conn.login(row.tax_email, password)
    return conn


def close(conn):
    try:
        conn.logout()
    except Exception:
        pass


# ---------------------------------------------------------------------------- folders
def decode_folder_name(name):
    """IMAP modified UTF-7 (RFC 3501) to text."""
    out, i = [], 0
    while i < len(name):
        if name[i] == "&":
            end = name.find("-", i)
            if end == -1:
                out.append(name[i:])
                break
            chunk = name[i + 1 : end]
            if not chunk:
                out.append("&")
            else:
                chunk = chunk.replace(",", "/")
                chunk += "=" * (-len(chunk) % 4)
                try:
                    out.append(base64.b64decode(chunk).decode("utf-16-be"))
                except Exception:
                    out.append(name[i : end + 1])
            i = end + 1
        else:
            out.append(name[i])
            i += 1
    return "".join(out)


def _unquote(value):
    if len(value) >= 2 and value[0] == value[-1] == '"':
        return value[1:-1].replace('\\"', '"').replace("\\\\", "\\")
    return value


def _quote(name):
    return '"' + name.replace("\\", "\\\\").replace('"', '\\"') + '"'


def list_folders(conn):
    """[{raw, name, junk}] of the mailbox's folders."""
    status, data = conn.list()
    if status != "OK":
        return []
    folders = []
    for line in data or []:
        if not isinstance(line, bytes):
            continue  # literals ({n}) are not used for folder names in practice
        match = _LIST_LINE.match(line.decode(errors="replace"))
        if not match:
            continue
        flags = match.group("flags").lower()
        if "\\noselect" in flags or "\\nonexistent" in flags:
            continue
        raw = _unquote(match.group("name").strip())
        delim = _unquote(match.group("delim")) if match.group("delim") != "NIL" else ""
        name = decode_folder_name(raw)
        leaf = (name.rsplit(delim, 1)[-1] if delim else name).strip().lower()
        folders.append(frappe._dict(raw=raw, name=name, junk="\\junk" in flags or leaf in JUNK_NAMES))
    return folders


def mailbox_folders(conn, row, settings):
    """The folders to read, INBOX first, and a warning for each extra folder that is not there."""
    wanted = [line.strip() for line in (row.extra_folders or "").splitlines() if line.strip()]
    if not (settings.read_junk_folder or wanted):
        return [frappe._dict(raw=INBOX, name=INBOX)], []

    available = list_folders(conn)
    folders = [frappe._dict(raw=INBOX, name=INBOX)]
    seen = {INBOX.lower()}

    def take(folder):
        if folder.raw.lower() not in seen:
            seen.add(folder.raw.lower())
            folders.append(folder)

    if settings.read_junk_folder:
        for folder in available:
            if folder.junk:
                take(folder)
    warnings = []
    for name in wanted:
        match = next((f for f in available if name.lower() in (f.name.lower(), f.raw.lower())), None)
        if match:
            take(match)
        else:
            warnings.append(_("الفولدر «{0}» غير موجود في الإيميل.").format(name))
    return folders, warnings


def select_folder(conn, folder=INBOX):
    status, data = conn.select(INBOX if folder == INBOX else _quote(folder), readonly=True)
    if status != "OK":
        raise imaplib.IMAP4.error(f"cannot open {folder}: {data}")
    total = cint(data[0])
    validity = conn.response("UIDVALIDITY")[1]
    validity = validity[0].decode() if validity and validity[0] else ""
    return total, validity


# kept for callers of the INBOX-only API
def select_inbox(conn):
    return select_folder(conn, INBOX)


def search_new_uids(conn, last_uid, settings):
    last_uid = cint(last_uid)
    if last_uid:
        status, data = conn.uid("search", None, "UID", f"{last_uid + 1}:*")
    else:
        since = add_days(getdate(today()), -settings.initial_sync_days)
        status, data = conn.uid("search", None, "SINCE", f"{since.day:02d}-{MONTHS[since.month - 1]}-{since.year}")
    if status != "OK":
        raise imaplib.IMAP4.error(f"search failed: {data}")
    # "n:*" always returns the newest message even when its UID is below n
    return sorted(uid for uid in (cint(u) for u in (data[0] or b"").split()) if uid > last_uid)


def load_folder_state(state):
    try:
        return json.loads(state.get("folder_state") or "{}") or {}
    except ValueError:
        return {}


# ---------------------------------------------------------------------------- notifications
def get_accountant_user(customer):
    employee = frappe.db.get_value("Customer", customer, "accountant")
    return frappe.db.get_value("Employee", employee, "user_id") if employee else None


def get_assignee(customer, settings=None):
    """The customer's accountant, or the default assignee when they have none."""
    settings = settings or get_settings()
    user = get_accountant_user(customer)
    if user and frappe.db.get_value("User", user, "enabled"):
        return user
    return settings.default_assignee or None


def get_sender(mail):
    """Real sender from the From header (Email() prefers Reply-To, which hides the authority's address)."""
    try:
        name, address = parseaddr(str(make_header(decode_header(mail.mail.get("From") or ""))))
    except Exception:
        name, address = "", ""
    return (address or mail.from_email or "").lower(), name or mail.from_real_name or ""


def html_to_text(html):
    """Readable text of an HTML body, without its stylesheet / scripts."""
    return strip_html(_NON_TEXT.sub(" ", html or ""))


def make_body(mail):
    if mail.html_content:
        html = clean_email_html(mail.html_content)
        text = mail.text_content or html_to_text(mail.html_content)
    else:
        text = mail.text_content or ""
        html = escape_html(text).replace("\n", "<br>")
    text = unescape(text).replace("\xa0", " ")
    return html, text[:200000]


def real_attachments(mail):
    """Attachments without the inline images (logos, signatures) referenced from the HTML body."""
    inline = set(mail.cid_map or {})
    return [
        a
        for a in (mail.attachments or [])
        if not (a.get("fname") in inline and (a.get("content_type") or "").startswith("image/"))
    ]


def save_attachments(doc, mail, settings):
    saved = 0
    limit = settings.max_attachment_mb * 1024 * 1024
    for attachment in real_attachments(mail):
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


def is_old(received_at, settings):
    """Older than the archive age: such a message is history, not something to act on."""
    days = cint(settings.archive_older_than_days)
    return bool(days and received_at and getdate(received_at) < add_days(getdate(today()), -days))


def create_notification(row, uid, raw, settings, rules):
    """Store one message. Returns the new document, or None when it already exists."""
    mail = Email(raw)
    # some senders reuse Message-IDs across different mails, so the date and subject are part of the key
    key = f"{mail.message_id or uid}|{mail.date}|{mail.subject}"
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
            "has_attachments": 1 if real_attachments(mail) else 0,
            "message_hash": message_hash,
            "imap_uid": uid,
            "status": "جديد",
            "priority": "متوسطة",
        }
    )

    rule = apply_rules(doc, rules)
    if not rule or cint(rule.assign_to_accountant):
        doc.assigned_to = get_assignee(row.parent, settings)
    if is_old(doc.received_at, settings):
        # e.g. the first sync of a year of mail: kept for reference, never overdue
        doc.status = ARCHIVED
        doc.due_date = None

    doc.flags.from_fetch = True
    doc.insert(ignore_permissions=True)

    if settings.fetch_attachments and doc.has_attachments:
        save_attachments(doc, mail, settings)

    is_recent = getdate(doc.received_at) >= add_days(getdate(today()), -settings.todo_max_age_days)
    if rule and cint(rule.create_todo) and doc.assigned_to and is_recent and doc.status != ARCHIVED:
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


def alert_failure(row, failures, error, settings):
    """Tell the customer's accountant and the default assignee (or the System Managers)."""
    from frappe.desk.doctype.notification_log.notification_log import enqueue_create_notification
    from frappe.utils.user import get_system_managers

    users = {u for u in (get_accountant_user(row.parent), settings.default_assignee) if u}
    users = [u for u in users if frappe.db.get_value("User", u, "enabled")] or get_system_managers(only_name=True)
    if not users:
        return
    customer_name = frappe.db.get_value("Customer", row.parent, "customer_name") or row.parent
    enqueue_create_notification(
        users,
        {
            "type": "Alert",
            "document_type": "Customer",
            "document_name": row.parent,
            "from_user": "Administrator",
            "subject": _("قراءة الإيميل الضريبي {0} للعميل {1} فشلت {2} مرات متتالية").format(
                row.tax_email, customer_name, failures
            ),
            "email_content": escape_html(error),
        },
    )


# ---------------------------------------------------------------------------- fetching
def fetch_folder(conn, row, state, folder, folder_state, settings, rules, budget, summary):
    """Read one folder from where it stopped. Returns the number of messages handled."""
    _total, validity = select_folder(conn, folder.raw)
    if folder.raw == INBOX:
        last_uid = cint(state.last_uid) if state.uid_validity == validity else 0
    else:
        saved = folder_state.get(folder.raw) or {}
        last_uid = cint(saved.get("uid")) if saved.get("validity") == validity else 0

    uids = search_new_uids(conn, last_uid, settings)
    batch = uids[:budget]
    summary.remaining += max(len(uids) - budget, 0)

    for uid in batch:
        status, data = conn.uid("fetch", str(uid), "(BODY.PEEK[])")
        raw = next((part[1] for part in data or [] if isinstance(part, tuple)), None)
        if status != "OK" or not raw:
            summary.skipped += 1
        else:
            try:
                if create_notification(row, uid, raw, settings, rules):
                    summary.fetched += 1
                else:
                    summary.skipped += 1
            except Exception:
                frappe.db.rollback()
                frappe.log_error(title=f"Tax notification parse failed: {row.tax_email} {folder.name} UID {uid}")
                summary.skipped += 1
        last_uid = max(last_uid, uid)
        # commit per message so a later failure never loses stored mail
        if folder.raw == INBOX:
            state.last_uid, state.uid_validity = last_uid, validity
            save_state(state, last_uid=last_uid, uid_validity=validity)
        else:
            folder_state[folder.raw] = {"uid": last_uid, "validity": validity}
            save_state(state, folder_state=json.dumps(folder_state, ensure_ascii=False))
        frappe.db.commit()

    if not batch:
        # remember the folder's validity even when nothing new came, so a later reset is noticed
        if folder.raw == INBOX:
            state.last_uid, state.uid_validity = last_uid, validity
        else:
            folder_state.setdefault(folder.raw, {"uid": last_uid, "validity": validity})
    return len(batch)


def fetch_mailbox(config_name, limit=None):
    """Fetch new messages of one mailbox. Returns a summary dict and never raises."""
    settings = get_settings()
    row = get_row(config_name)
    state = get_state(row)
    budget = cint(limit) or settings.max_messages_per_run
    summary = frappe._dict(ok=False, fetched=0, skipped=0, remaining=0, error=None, warnings=[], folders=[])
    folder_state = load_folder_state(state)
    conn = None

    try:
        conn = connect(row)
        rules = get_rules()
        folders, summary.warnings = mailbox_folders(conn, row, settings)
        for folder in folders:
            try:
                handled = fetch_folder(conn, row, state, folder, folder_state, settings, rules, budget, summary)
            except imaplib.IMAP4.error as error:
                if folder.raw == INBOX:
                    raise
                # a Spam / extra folder that cannot be read does not fail the mailbox
                summary.warnings.append(_("تعذر قراءة الفولدر «{0}»: {1}").format(folder.name, error))
                continue
            summary.folders.append(folder.name)
            budget = max(budget - handled, 0)

        save_state(
            state,
            status="Success",
            last_error="\n".join(summary.warnings)[:1000],
            last_uid=cint(state.last_uid),
            uid_validity=state.uid_validity,
            folder_state=json.dumps(folder_state, ensure_ascii=False),
            customer=row.parent,
            tax_email=row.tax_email,
            total_fetched=cint(state.total_fetched) + summary.fetched,
            consecutive_failures=0,
        )
        summary.ok = True
    except Exception as error:
        frappe.db.rollback()
        summary.error = friendly_error(error)
        failures = cint(frappe.db.get_value("Tax Mailbox Sync", state.name, "consecutive_failures")) + 1
        save_state(
            state,
            status="Failed",
            last_error=summary.error[:1000],
            customer=row.parent,
            tax_email=row.tax_email,
            consecutive_failures=failures,
        )
        # once, when the count is reached: the back-off keeps retrying, it does not re-alert
        if cint(settings.failure_alert_after) and failures == cint(settings.failure_alert_after):
            try:
                alert_failure(row, failures, summary.error, settings)
            except Exception:
                frappe.log_error(title=f"Tax mailbox failure alert: {row.tax_email}")
    finally:
        if conn:
            close(conn)
        frappe.db.commit()
    return summary


def due_mailboxes(settings=None):
    """Enabled mailboxes whose interval has passed (and that are not backing off after a failure)."""
    settings = settings or get_settings()
    now = now_datetime()
    # the scheduler ticks every 5 minutes and a run takes a while: a little early is on time
    due_before = add_to_date(now, minutes=-max(settings.fetch_interval_minutes - 2, 1))
    return frappe.db.sql(
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
          AND (state.last_sync IS NULL OR state.last_sync <= %(due_before)s)
          -- back off after a failure (e.g. wrong password) so the mail provider does not lock the account
          AND NOT (IFNULL(state.status, '') = 'Failed' AND state.last_sync > %(retry_after)s)
        """,
        {"due_before": due_before, "retry_after": add_to_date(now, hours=-FAILED_RETRY_HOURS)},
        pluck=True,
    )


def fetch_all():
    """Scheduler entry point (every 5 minutes): one background job per mailbox that is due."""
    settings = get_settings()
    if not settings.enabled:
        return
    for name in due_mailboxes(settings):
        frappe.enqueue(
            "accounting_firms.tax_email.fetch.fetch_mailbox",
            queue="long",
            timeout=900,
            job_id=f"tax_mailbox::{name}",
            deduplicate=True,
            config_name=name,
        )


# ---------------------------------------------------------------------------- form actions
def check_customer(parent):
    if not frappe.has_permission("Customer", ptype="write", doc=parent):
        frappe.throw(_("ليس لديك صلاحية على هذا العميل."), frappe.PermissionError)


@frappe.whitelist()
def test_connection(name, parent):
    check_customer(parent)
    row = get_row(name, parent)
    conn = None
    try:
        conn = connect(row)
        total, _validity = select_folder(conn, INBOX)
        folders = list_folders(conn)
        return {
            "ok": True,
            "messages": total,
            "folders": [f.name for f in folders],
            "junk": [f.name for f in folders if f.junk],
        }
    except frappe.ValidationError:
        raise
    except Exception as error:
        return {"ok": False, "error": friendly_error(error)}
    finally:
        if conn:
            close(conn)


@frappe.whitelist()
def fetch_now(name, parent):
    check_customer(parent)
    row = get_row(name, parent)
    # keep the request short; the scheduler picks up whatever remains
    return fetch_mailbox(row.name, limit=15)


@frappe.whitelist()
def get_customer_summary(customer):
    if not frappe.has_permission("Customer", ptype="read", doc=customer):
        frappe.throw(_("ليس لديك صلاحية قراءة بيانات هذا العميل."), frappe.PermissionError)
    open_filters = {"customer": customer, "status": ["in", ["جديد", "تحت المراجعة"]]}
    has_mailbox = frappe.db.exists(
        "Tax Email Configuration", {"parent": customer, "parenttype": "Customer", "enabled": 1}
    )
    return {
        "new": frappe.db.count("Tax Notification", {"customer": customer, "status": "جديد"}),
        "overdue": frappe.db.count("Tax Notification", {**open_filters, "due_date": ["<", today()]}),
        "high": frappe.db.count("Tax Notification", {**open_filters, "priority": "عالية"}),
        # notifications of this customer would reach nobody
        "no_assignee": bool(has_mailbox and not get_assignee(customer)),
        "has_accountant_user": bool(get_accountant_user(customer)),
    }
