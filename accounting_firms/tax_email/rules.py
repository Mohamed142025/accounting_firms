"""Rule-based classification of tax notifications."""

import re

import frappe
from frappe.utils import add_days, cint, getdate

_TASHKEEL = re.compile(r"[ً-ْـ]")
_ARABIC_MAP = str.maketrans({"أ": "ا", "إ": "ا", "آ": "ا", "ى": "ي", "ة": "ه", "ؤ": "و", "ئ": "ي"})


def normalize(text):
    """Lowercase and fold common Arabic spelling variants so keywords match reliably."""
    text = _TASHKEEL.sub("", (text or "").lower())
    return text.translate(_ARABIC_MAP)


def _keywords(value):
    return [normalize(k).strip() for k in re.split(r"[\n,،]", value or "") if k.strip()]


def _matches(keywords, haystack):
    return not keywords or any(k in haystack for k in keywords)


def get_rules():
    return frappe.get_all(
        "Tax Notification Rule",
        filters={"enabled": 1},
        fields=[
            "name",
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


def find_rules(doc, rules=None):
    """All matching rules, in sequence order."""
    sender = normalize(f"{doc.sender or ''} {doc.sender_name or ''}")
    subject = normalize(doc.subject)
    body = normalize(doc.body_text)

    matched = []
    for rule in rules if rules is not None else get_rules():
        conditions = (_keywords(rule.sender_contains), _keywords(rule.subject_keywords), _keywords(rule.body_keywords))
        if not any(conditions):
            continue  # a rule without conditions would swallow everything
        if _matches(conditions[0], sender) and _matches(conditions[1], subject) and _matches(conditions[2], body):
            matched.append(rule)
    return matched


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
    frappe.only_for(("System Manager", "Accounts Manager"))
    if isinstance(names, str):
        names = frappe.parse_json(names)
    filters = {"name": ["in", names]} if names else {"status": ["in", ["جديد", "تحت المراجعة"]]}
    rules = get_rules()
    changed = 0
    for name in frappe.get_all("Tax Notification", filters=filters, pluck="name"):
        doc = frappe.get_doc("Tax Notification", name)
        before = (doc.category, doc.tax_type, doc.priority, doc.due_date, doc.matched_rule, doc.status)
        apply_rules(doc, rules)
        if before != (doc.category, doc.tax_type, doc.priority, doc.due_date, doc.matched_rule, doc.status):
            doc.save(ignore_permissions=True)
            changed += 1
    return {"changed": changed}


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
