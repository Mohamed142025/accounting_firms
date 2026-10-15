"""Rule-based classification of tax notifications."""

import re
from functools import lru_cache

import frappe
from frappe import _
from frappe.utils import add_days, cint, getdate

_TASHKEEL = re.compile(r"[ً-ْـ]")
_ARABIC_MAP = str.maketrans({"أ": "ا", "إ": "ا", "آ": "ا", "ى": "ي", "ة": "ه", "ؤ": "و", "ئ": "ي"})
_ARABIC = re.compile(r"[\u0600-\u06FF]")
# a keyword is a whole word, which in Arabic may carry a leading و/ف/ب/ل/ك and ال, and a
# trailing pronoun / plural ("فحص" matches "الفحص", "بالفحص", "فحصها"; not "تفحص")
_PREFIX = "(?:[وفبلك]?(?:ال|لل)?)"
_SUFFIX = "(?:ه|ها|هم|هما|هن|ات|ين|ون|ان|يه|ي|ا)?"


def normalize(text):
    """Lowercase and fold common Arabic spelling variants so keywords match reliably."""
    text = _TASHKEEL.sub("", (text or "").lower())
    return text.translate(_ARABIC_MAP)


def _keywords(value):
    return [normalize(k).strip() for k in re.split(r"[\n,،]", value or "") if k.strip()]


_ARABIC_LETTERS = "\u0621-\u064a\u0671-\u06d3"
_DIGITS = "0-9\u0660-\u0669\u06f0-\u06f9"


def _edge(char):
    """Characters that may not touch a keyword edge ending in `char`: a word goes on in its
    own script, so "1تحديث" holds the word "تحديث" and "نموذج 190" does not hold "19"."""
    if re.match(f"[{_ARABIC_LETTERS}]", char):
        return _ARABIC_LETTERS
    if re.match(f"[{_DIGITS}]", char):
        return _DIGITS
    if char.isalpha():
        return "a-z"
    return None


@lru_cache(maxsize=2048)
def _word_pattern(keyword):
    words = keyword.split()
    parts = []
    for word in words:
        escaped = re.escape(word)
        parts.append(f"{_PREFIX}{escaped}{_SUFFIX}" if _ARABIC.search(word) else escaped)
    before, after = _edge(keyword[0]), _edge(keyword[-1])
    return re.compile(
        (f"(?<![{before}])" if before else "") + r"\s+".join(parts) + (f"(?![{after}])" if after else "")
    )


def _matches(keywords, haystack, whole_words=True):
    if not keywords:
        return True
    if not whole_words:
        return any(k in haystack for k in keywords)
    return any(_word_pattern(k).search(haystack) for k in keywords)


def get_rules():
    return frappe.get_all(
        "Tax Notification Rule",
        filters={"enabled": 1},
        fields=[
            "name",
            "sequence",
            "sender_contains",
            "subject_keywords",
            "body_keywords",
            "category",
            "tax_type",
            "priority",
            "due_in_days",
            "assign_to_accountant",
            "create_todo",
            "auto_archive",
        ],
        order_by="sequence asc, creation asc",
    )


def rule_matches(rule, sender, subject, body):
    """sender / subject / body already normalized. A rule without conditions matches nothing."""
    conditions = (_keywords(rule.sender_contains), _keywords(rule.subject_keywords), _keywords(rule.body_keywords))
    if not any(conditions):
        return False  # a rule without conditions would swallow everything
    # the sender is an address: any part of it (a domain) counts
    return (
        _matches(conditions[0], sender, whole_words=False)
        and _matches(conditions[1], subject)
        and _matches(conditions[2], body)
    )


def _texts(doc):
    return (
        normalize(f"{doc.sender or ''} {doc.sender_name or ''}"),
        normalize(doc.subject),
        normalize(doc.body_text),
    )


def find_rules(doc, rules=None):
    """All matching rules, in sequence order."""
    sender, subject, body = _texts(doc)
    return [rule for rule in (rules if rules is not None else get_rules()) if rule_matches(rule, sender, subject, body)]


def apply_rules(doc, rules=None):
    """Set category / tax type / priority / due date on the notification. Returns the matched rule.

    The first matching rule decides; later matching rules only fill in a tax type
    or category the first one left empty (e.g. "إقرار" + "القيمة المضافة").
    """
    matched = find_rules(doc, rules)
    if not matched:
        return None

    rule = matched[0]
    doc.matched_rule = rule.name
    doc.category = rule.category or next((r.category for r in matched if r.category), None) or doc.category
    doc.tax_type = rule.tax_type or next((r.tax_type for r in matched if r.tax_type), None) or doc.tax_type
    doc.priority = rule.priority or doc.priority
    if cint(rule.due_in_days) and doc.received_at:
        doc.due_date = add_days(getdate(doc.received_at), cint(rule.due_in_days))
    if cint(rule.auto_archive):
        doc.status = "مؤرشف"
    return rule


@frappe.whitelist()
def reclassify(names=None):
    """Re-run the rules on existing notifications (all open ones when `names` is empty)."""
    from accounting_firms.tax_email.fetch import get_assignee, get_settings

    frappe.only_for(("System Manager", "Accounts Manager"))
    if isinstance(names, str):
        names = frappe.parse_json(names)
    filters = {"name": ["in", names]} if names else {"status": ["in", ["جديد", "تحت المراجعة"]]}
    rules = get_rules()
    settings = get_settings()
    changed = 0
    for name in frappe.get_all("Tax Notification", filters=filters, pluck="name"):
        doc = frappe.get_doc("Tax Notification", name)
        before = (doc.category, doc.tax_type, doc.priority, doc.due_date, doc.matched_rule, doc.status, doc.assigned_to)
        rule = apply_rules(doc, rules)
        # one that reached nobody goes to the accountant / default assignee now
        if not doc.assigned_to and (not rule or cint(rule.assign_to_accountant)):
            doc.assigned_to = get_assignee(doc.customer, settings)
        if before != (doc.category, doc.tax_type, doc.priority, doc.due_date, doc.matched_rule, doc.status, doc.assigned_to):
            doc.flags.from_fetch = True
            doc.save(ignore_permissions=True)
            changed += 1
    return {"changed": changed}


@frappe.whitelist()
def test_rule(rule, limit=500):
    """What a rule (saved or not) would match among the latest notifications, and where it
    would be the deciding rule given the other enabled rules."""
    frappe.has_permission("Tax Notification Rule", "read", throw=True)
    rule = frappe._dict(frappe.parse_json(rule) if isinstance(rule, str) else rule)
    rule.name = rule.name or rule.rule_name or "__new__"
    if not any(_keywords(rule.get(f)) for f in ("sender_contains", "subject_keywords", "body_keywords")):
        frappe.throw(_("القاعدة مفيهاش شروط: اكتب المرسل أو كلمات العنوان أو النص."))

    others = [r for r in get_rules() if r.name != rule.name]
    candidate = frappe._dict({**rule, "sequence": cint(rule.sequence)})
    ordered = sorted(others + [candidate], key=lambda r: cint(r.sequence))
    if not cint(rule.get("enabled", 1)):
        ordered = others

    notifications = frappe.get_all(
        "Tax Notification",
        fields=["name", "subject", "customer", "received_at", "status", "matched_rule", "sender", "sender_name", "body_text"],
        order_by="received_at desc",
        limit=cint(limit) or 500,
    )
    matches, deciding = [], 0
    for n in notifications:
        texts = _texts(n)
        if not rule_matches(candidate, *texts):
            continue
        first = next((r for r in ordered if rule_matches(r, *texts)), None)
        decides = bool(first and first.name == rule.name)
        deciding += decides
        matches.append(
            {
                "name": n.name,
                "subject": n.subject,
                "customer": n.customer,
                "received_at": n.received_at,
                "status": n.status,
                "current_rule": n.matched_rule,
                "decides": decides,
                "deciding_rule": first.name if first and not decides else None,
            }
        )
    return {"checked": len(notifications), "matched": len(matches), "deciding": deciding, "rows": matches[:100]}


def ensure_rules(rules):
    """Insert seed rules that do not exist yet.

    rules: iterable of (name, sequence, sender, subject keywords, body keywords,
    category, tax type, priority, due days, create todo, assign, auto archive).
    """
    for name, seq, sender, subject, body, category, tax_type, priority, due, todo, assign, archive in rules:
        if frappe.db.exists("Tax Notification Rule", name):
            continue
        if category and not frappe.db.exists("Tax Notification Category", category):
            frappe.get_doc({"doctype": "Tax Notification Category", "category_name": category}).insert(ignore_permissions=True)
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
