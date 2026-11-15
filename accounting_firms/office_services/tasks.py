"""Service tasks: a customer's service becomes a tree of ERPNext Tasks built from the
service's Service Task Map.

The main task ("<service> — <customer>") holds the map's tasks and subtasks. A task starts
(and is assigned) only when it may: a sequential task after the tasks before it on its level
are done, a parallel one together with the task before it, a subtask when its parent starts.
A task with subtasks is done when they all are; the service is done when all its tasks are.

Assignment follows the map row: one employee, a department's manager, or everyone in a
department / holding a role - then each of them gets it, and the first to claim it keeps it.
"""

import json

import frappe
from frappe import _
from frappe.desk.form.assign_to import _add as add_assignment
from frappe.desk.form.assign_to import _remove as remove_assignment
from frappe.desk.form.assign_to import clear as clear_assignments
from frappe.desk.form.assign_to import close_all_assignments
from frappe.share import add_docshare
from frappe.utils import add_days, cint, getdate, today

from accounting_firms.accounting_firms.doctype.service_task_map.service_task_map import (
    ASSIGN_DEPARTMENT,
    ASSIGN_EMPLOYEE,
    ASSIGN_MANAGER,
    ASSIGN_ROLE,
    MANAGER_FIELD,
    parent_no,
    split_entities,
    task_key,
)

DONE = ("Completed", "Cancelled")
PARALLEL = "متوازي"
ACTIVE = "نشطة"
MANAGER_ROLES = ("System Manager", "Projects Manager", "Accounts Manager")


class DuplicateServiceTask(frappe.ValidationError):
    pass


# ---------------------------------------------------------------- who
def user_of(employee):
    return frappe.db.get_value("Employee", employee, "user_id") if employee else None


def enabled(users):
    users = [u for u in dict.fromkeys(users) if u]
    if not users:
        return []
    return frappe.get_all("User", filters={"name": ["in", users], "enabled": 1}, pluck="name", order_by="full_name asc")


def department_users(department):
    bounds = frappe.db.get_value("Department", department, ["lft", "rgt"])
    departments = (
        frappe.get_all("Department", filters={"lft": [">=", bounds[0]], "rgt": ["<=", bounds[1]]}, pluck="name") if bounds else [department]
    )
    return enabled(
        frappe.get_all("Employee", filters={"department": ["in", departments], "status": "Active", "user_id": ["is", "set"]}, pluck="user_id")
    )


def role_users(role):
    users = frappe.get_all("Has Role", filters={"role": role, "parenttype": "User"}, pluck="parent")
    return [u for u in enabled(users) if frappe.db.get_value("User", u, "user_type") == "System User" and u not in ("Administrator", "Guest")]


def candidates(assign_type, department=None, role=None, user=None):
    """The users a task goes to."""
    if user:
        return enabled([user])
    if assign_type == ASSIGN_MANAGER:
        return enabled([user_of(frappe.db.get_value("Department", department, MANAGER_FIELD))]) if department else []
    if assign_type == ASSIGN_DEPARTMENT:
        return department_users(department) if department else []
    if assign_type == ASSIGN_ROLE:
        return role_users(role) if role else []
    return []


def describe(assign_type, department=None, role=None, user=None):
    if user:
        return frappe.utils.get_fullname(user)
    return {
        ASSIGN_DEPARTMENT: _("كل {0}").format(department),
        ASSIGN_MANAGER: _("مدير {0}").format(department),
        ASSIGN_ROLE: _("رول {0}").format(role),
    }.get(assign_type, "")


# ---------------------------------------------------------------- the map for a customer
def customer_service(customer, service):
    return next((r for r in frappe.get_doc("Customer", customer).get("office_services") or [] if r.service == service), None)


def map_rows(service, legal_entity=None):
    """The map's rows for a customer of this legal entity, with why a row is left out."""
    name = frappe.db.get_value("Service Task Map", {"service": service, "enabled": 1})
    if not name:
        return None
    rows = sorted(frappe.get_doc("Service Task Map", name).tasks, key=lambda r: task_key(r.task_no))
    skipped = {}
    for row in rows:
        parent = parent_no(row.task_no)
        entities = split_entities(row.applies_to)
        if parent in skipped:
            skipped[row.task_no] = _("المهمة الأم مش هتتعمل")
        elif entities and legal_entity not in entities:
            skipped[row.task_no] = _("مش بتنطبق على كيان العميل ({0})").format(legal_entity or _("غير محدد"))
    return rows, skipped


def default_period(recurrence, on=None):
    day = getdate(on or today())
    return {
        "شهري": f"{day.year}-{day.month:02d}",
        "ربع سنوي": f"Q{(day.month - 1) // 3 + 1}-{day.year}",
        "نصف سنوي": f"H{1 if day.month <= 6 else 2}-{day.year}",
        "سنوي": str(day.year),
    }.get(recurrence or "", "")


def _check_customer(customer):
    if not frappe.has_permission("Customer", "read", doc=customer):
        frappe.throw(_("ليس لديك صلاحية على هذا العميل."), frappe.PermissionError)
    if not frappe.has_permission("Task", "create"):
        frappe.throw(_("ليس لديك صلاحية إنشاء مهام."), frappe.PermissionError)


def open_main_task(customer, service, period):
    return frappe.db.get_value(
        "Task",
        {"af_customer": customer, "af_service": service, "af_period": period or "", "parent_task": ["is", "not set"], "status": ["not in", DONE]},
    )


@frappe.whitelist()
def get_new_task_context(customer, service=None):
    """The customer's active services, and for one of them what its tasks will be."""
    _check_customer(customer)
    doc = frappe.get_doc("Customer", customer)
    services = [
        {"service": r.service, "service_name": r.service_name or r.service, "recurrence": r.recurrence}
        for r in doc.get("office_services") or []
        if r.status == ACTIVE
    ]
    out = {"services": services, "legal_entity": doc.get("legal_entity")}
    if not service:
        return out
    row = customer_service(customer, service)
    if not row or row.status != ACTIVE:
        frappe.throw(_("الخدمة مش من الخدمات النشطة للعميل."))
    out["period"] = default_period(row.recurrence)
    out["recurrence"] = row.recurrence
    out["employees"] = frappe.get_all(
        "Employee", filters={"status": "Active", "user_id": ["is", "set"]}, fields=["user_id as user", "employee_name"], order_by="employee_name asc"
    )
    found = map_rows(service, doc.get("legal_entity"))
    if found is None:
        out["has_map"] = False
        return out
    rows, skipped = found
    out["has_map"] = True
    out["rows"] = [
        {
            "task_no": r.task_no,
            "task_title": r.task_title,
            "depth": r.task_no.count("."),
            "mandatory": cint(r.mandatory),
            "execution": r.execution,
            "expected_days": cint(r.expected_days),
            "assign": describe(r.assign_to_type, r.department, r.role, user_of(r.employee) if r.assign_to_type == ASSIGN_EMPLOYEE else None),
            "candidates": [
                {"user": u, "full_name": frappe.utils.get_fullname(u)}
                for u in candidates(r.assign_to_type, r.department, r.role, user_of(r.employee) if r.assign_to_type == ASSIGN_EMPLOYEE else None)
            ],
            "skipped": skipped.get(r.task_no),
        }
        for r in rows
    ]
    return out


# ---------------------------------------------------------------- creating
@frappe.whitelist()
def create_service_tasks(customer, service, period=None, due_date=None, priority=None, notes=None, rows=None, force=0):
    """The main task of the service and the map's tasks under it. `rows`: [{task_no,
    include, user}] - leave out optional tasks, or give a task to someone in particular."""
    _check_customer(customer)
    row = customer_service(customer, service)
    if not row or row.status != ACTIVE:
        frappe.throw(_("الخدمة مش من الخدمات النشطة للعميل."))
    period = (period or "").strip()
    existing = open_main_task(customer, service, period)
    if existing and not cint(force):
        frappe.throw(
            _("فيه مهمة مفتوحة على نفس الخدمة والفترة: {0}").format(frappe.utils.get_link_to_form("Task", existing)),
            title=_("مهمة مكررة"),
            exc=DuplicateServiceTask,
        )
    choices = {c["task_no"]: c for c in (json.loads(rows) if isinstance(rows, str) else rows or [])}
    customer_doc = frappe.get_doc("Customer", customer)
    found = map_rows(service, customer_doc.get("legal_entity"))

    subject = " — ".join(p for p in (row.service_name or service, customer_doc.customer_name, period) if p)
    main = frappe.get_doc(
        {
            "doctype": "Task",
            "subject": subject[:140],
            "is_group": 1 if found else 0,
            "priority": priority or "Medium",
            "exp_start_date": today(),
            "exp_end_date": due_date or None,
            "description": notes,
            "af_customer": customer,
            "af_service": service,
            "af_period": period,
            "af_ready": 1,
        }
    )
    main.insert()
    main.db_set("af_root", main.name, update_modified=False)

    if not found:
        # a service without a map: one task, to whoever was chosen
        user = (choices.get("") or {}).get("user") or user_of(row.responsible)
        if user:
            main.db_set({"af_assign_type": ASSIGN_EMPLOYEE, "af_assign_user": user}, update_modified=False)
            assign(main.name, [user])
        return main.name

    rows_, skipped = found
    has_children = {parent_no(r.task_no) for r in rows_}
    created = {}
    left_out = set(skipped)
    for r in rows_:
        choice = choices.get(r.task_no) or {}
        parent = parent_no(r.task_no)
        if r.task_no in left_out or parent in left_out:
            left_out.add(r.task_no)
            continue
        if not cint(r.mandatory) and choice.get("include") in (0, False, "0"):
            left_out.add(r.task_no)
            continue
        user = choice.get("user") or (user_of(r.employee) if r.assign_to_type == ASSIGN_EMPLOYEE else None)
        task = frappe.get_doc(
            {
                "doctype": "Task",
                "subject": r.task_title[:140],
                "parent_task": created.get(parent, main.name),
                "is_group": 1 if r.task_no in has_children else 0,
                "priority": priority or "Medium",
                "department": r.department,
                "description": r.description,
                "af_customer": customer,
                "af_service": service,
                "af_period": period,
                "af_root": main.name,
                "af_task_no": r.task_no,
                "af_assign_type": ASSIGN_EMPLOYEE if user else r.assign_to_type,
                "af_role": None if user else r.role,
                "af_assign_user": user,
                "af_execution": r.execution,
                "af_mandatory": cint(r.mandatory),
                "af_requires_attachment": cint(r.requires_attachment),
                "af_expected_days": cint(r.expected_days),
            }
        )
        task.flags.af_engine = True
        task.insert()
        created[r.task_no] = task.name

    if not created:
        frappe.throw(_("مفيش ولا مهمة من الخريطة بتنطبق على العميل ده."))
    advance(main.name)
    return main.name


# ---------------------------------------------------------------- running
def assign(task, users, pool=False):
    """Assign, and share the task for editing: office staff may hold no role on Task, and
    they must be able to work on and close what is theirs."""
    # shared first: Frappe would otherwise share it itself, with the permissions of whoever
    # finished the task before (who may not share Tasks)
    for user in users:
        add_docshare("Task", task, user, read=1, write=1, flags={"ignore_share_permission": True})
    subject = frappe.db.get_value("Task", task, "subject")
    add_assignment(
        {"assign_to": users, "doctype": "Task", "name": task, "description": subject, "date": frappe.db.get_value("Task", task, "exp_end_date")},
        ignore_permissions=True,
    )
    frappe.db.set_value("Task", task, "af_pool", 1 if pool and len(users) > 1 else 0, update_modified=False)


def start(task):
    """Dates and assignment of a task whose turn has come."""
    doc = frappe.get_doc("Task", task)
    values = {"af_ready": 1, "exp_start_date": today()}
    days = cint(doc.af_expected_days)
    if days:
        end = getdate(add_days(today(), days))
        parent_end = frappe.db.get_value("Task", doc.parent_task, "exp_end_date") if doc.parent_task else None
        # ERPNext keeps a subtask within its parent's end date; a parent already past it
        # leaves the subtask without one rather than ending before it starts
        if not parent_end:
            values["exp_end_date"] = end
        elif getdate(parent_end) >= getdate(today()):
            values["exp_end_date"] = min(end, getdate(parent_end))
    frappe.db.set_value("Task", task, values, update_modified=False)
    users = candidates(doc.af_assign_type, doc.department, doc.af_role, doc.af_assign_user)
    if users:
        assign(task, users, pool=not doc.af_assign_user and doc.af_assign_type in (ASSIGN_DEPARTMENT, ASSIGN_ROLE))
    else:
        frappe.get_doc(
            {
                "doctype": "Comment",
                "comment_type": "Comment",
                "reference_doctype": "Task",
                "reference_name": task,
                "content": _("مفيش حد ينطبق عليه إسناد المهمة ({0}). أسندها يدوياً.").format(
                    describe(doc.af_assign_type, doc.department, doc.af_role)
                ),
            }
        ).insert(ignore_permissions=True)


def advance(root):
    """Start the tasks whose turn has come and close the ones whose subtasks are all done,
    until nothing changes."""
    if frappe.flags.af_advancing:
        frappe.flags.af_advance_again = True
        return
    frappe.flags.af_advancing = True
    try:
        for _round in range(50):
            frappe.flags.af_advance_again = False
            if not _advance_once(root) and not frappe.flags.af_advance_again:
                break
    finally:
        frappe.flags.af_advancing = False


def _advance_once(root):
    tasks = frappe.get_all(
        "Task",
        filters={"af_root": root},
        fields=["name", "parent_task", "status", "is_group", "af_ready", "af_execution", "af_task_no"],
    )
    by_parent = {}
    for t in tasks:
        if t.name != root:
            by_parent.setdefault(t.parent_task, []).append(t)
    for siblings in by_parent.values():
        siblings.sort(key=lambda t: task_key(t.af_task_no) if t.af_task_no else (0,))
    changed = False

    # groups whose subtasks are all done are done (deepest first)
    for t in sorted(tasks, key=lambda t: -len((t.af_task_no or "").split("."))):
        children = by_parent.get(t.name)
        if t.is_group and children and t.status not in DONE and all(c.status in DONE for c in children):
            doc = frappe.get_doc("Task", t.name)
            doc.status = "Completed" if any(c.status == "Completed" for c in children) else "Cancelled"
            doc.flags.af_engine = True
            doc.save(ignore_permissions=True)
            t.status = doc.status
            changed = True

    def walk(parent, parent_running):
        nonlocal changed
        previous_start = parent_running
        siblings = by_parent.get(parent) or []
        for i, t in enumerate(siblings):
            if t.af_execution == PARALLEL and i:
                may_start = previous_start
            else:
                may_start = parent_running and all(s.status in DONE for s in siblings[:i])
            previous_start = may_start
            if may_start and not t.af_ready and t.status not in DONE:
                start(t.name)
                t.af_ready = 1
                changed = True
            walk(t.name, may_start and t.status not in DONE)

    root_status = next((t.status for t in tasks if t.name == root), None)
    walk(root, root_status not in DONE)
    return changed


# ---------------------------------------------------------------- task events
def has_attachment(task):
    return frappe.db.exists("File", {"attached_to_doctype": "Task", "attached_to_name": task})


def is_manager():
    return bool(set(MANAGER_ROLES) & set(frappe.get_roles()))


def before_validate_task(doc, method=None):
    """Runs before ERPNext's Task.validate: that one closes every assignment of a completed
    task with the user's own permissions, which office staff do not have on each other's."""
    if not doc.get("af_root") or doc.is_new():
        return
    before = doc.get_doc_before_save()
    if not before or before.status == doc.status:
        return
    if not doc.flags.af_engine:
        if doc.status == "Completed" and doc.af_requires_attachment and not doc.is_group and not has_attachment(doc.name):
            frappe.throw(_("المهمة دي محتاجة مرفق قبل ما تتقفل. ارفع الملف الأول."), title=_("مرفق مطلوب"))
        if doc.status == "Cancelled" and doc.af_mandatory and doc.name != doc.af_root and not is_manager():
            frappe.throw(_("المهمة إجبارية، ومش ممكن تتلغي إلا من المدير."))
        if doc.status not in DONE and not doc.af_ready and doc.name != doc.af_root:
            frappe.throw(_("المهمة لسه ما بدأتش: مستنية المهام اللي قبلها تخلص."))
    if doc.status in ("Completed", "Working") and doc.af_pool and not doc.af_claimed_by:
        # working on a group task without claiming it claims it
        take(doc.name, frappe.session.user)
        doc.af_claimed_by, doc.af_pool = frappe.session.user, 0
    if doc.status == "Completed":
        doc.completed_on = doc.completed_on or today()
        doc.completed_by = doc.completed_by or frappe.session.user
        close_all_assignments("Task", doc.name, ignore_permissions=True)
    elif doc.status == "Cancelled":
        clear_assignments("Task", doc.name, ignore_permissions=True)


def on_task_update(doc, method=None):
    if not doc.get("af_root") or doc.flags.af_engine:
        return
    before = doc.get_doc_before_save()
    if before and before.status == doc.status:
        return
    if doc.name == doc.af_root and doc.status == "Cancelled":
        # the whole service is cancelled
        for name in frappe.get_all("Task", filters={"af_root": doc.name, "name": ["!=", doc.name], "status": ["not in", DONE]}, pluck="name"):
            frappe.db.set_value("Task", name, "status", "Cancelled")
            clear_assignments("Task", name, ignore_permissions=True)
        return
    if doc.status in DONE:
        advance(doc.af_root)


# ---------------------------------------------------------------- actions
def unshare(task, user):
    for name in frappe.get_all("DocShare", filters={"share_doctype": "Task", "share_name": task, "user": user}, pluck="name"):
        frappe.delete_doc("DocShare", name, ignore_permissions=True, flags={"ignore_share_permission": True})


@frappe.whitelist()
def claim(task):
    """Take a task given to a whole department / role: it leaves everyone else's list."""
    user = frappe.session.user
    doc = frappe.get_doc("Task", task)
    frappe.db.get_value("Task", task, "name", for_update=True)
    claimed = frappe.db.get_value("Task", task, "af_claimed_by")
    if claimed:
        frappe.throw(_("المهمة استلمها {0} بالفعل.").format(frappe.utils.get_fullname(claimed)))
    if user not in json.loads(doc._assign or "[]"):
        frappe.throw(_("المهمة مش مسندة لك."), frappe.PermissionError)
    take(task, user)
    frappe.db.set_value("Task", task, {"af_claimed_by": user, "af_pool": 0, "status": "Working"})
    return user


def take(task, user):
    """The task leaves the list of everyone it was given to but `user`."""
    for other in json.loads(frappe.db.get_value("Task", task, "_assign") or "[]"):
        if other != user:
            remove_assignment("Task", task, other, ignore_permissions=True)
            unshare(task, other)


@frappe.whitelist()
def not_applicable(task, reason=None):
    """Close an optional task as not applicable."""
    doc = frappe.get_doc("Task", task)
    doc.check_permission("write")
    if doc.af_mandatory and not is_manager():
        frappe.throw(_("المهمة إجبارية."))
    doc.status = "Cancelled"
    doc.save()
    doc.add_comment("Comment", _("لا ينطبق") + (f": {reason}" if reason else ""))
    return doc.status
