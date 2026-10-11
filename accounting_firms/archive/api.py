"""Customer archive: per-customer folder trees and documents."""

import io
import json
import zipfile

import frappe
from frappe import _
from frappe.utils import cint, get_files_path, now_datetime
from frappe.utils.file_manager import get_file_path

FOLDER = "Customer Archive Folder"
TEMPLATE = "Archive Folder Template"
DOCUMENT = "Customer Document"
MANAGER_ROLES = ("System Manager",)


# ---------------------------------------------------------------- helpers
def _check(customer, ptype="read"):
    if not frappe.has_permission("Customer", ptype=ptype, doc=customer):
        frappe.throw(_("ليس لديك صلاحية على هذا العميل."), frappe.PermissionError)


def _is_manager():
    return any(role in frappe.get_roles() for role in MANAGER_ROLES)


def _parse_names(names):
    if isinstance(names, str):
        names = frappe.parse_json(names)
    return [n for n in (names or []) if n]


def template_paths():
    """{path: (name, parent_path)} for every template folder, parents first."""
    rows = frappe.get_all(TEMPLATE, fields=["name", "folder_name", "parent_archive_folder_template"], order_by="lft asc")
    by_name = {r.name: r for r in rows}
    paths = {}
    for r in rows:
        parts, cur = [], r
        while cur:
            parts.append(cur.folder_name)
            cur = by_name.get(cur.parent_archive_folder_template)
        path = "/".join(reversed(parts))
        parent_path = path.rsplit("/", 1)[0] if "/" in path else ""
        paths[path] = parent_path
    return paths


def get_root(customer, create=True):
    root = frappe.db.get_value(FOLDER, {"customer": customer, "is_root": 1}, "name")
    if root or not create:
        return root
    doc = frappe.get_doc(
        {"doctype": FOLDER, "customer": customer, "folder_name": frappe.db.get_value("Customer", customer, "customer_name") or customer, "is_root": 1}
    )
    doc.flags.ignore_permissions = True
    doc.insert(ignore_permissions=True)
    return doc.name


def ensure_customer_tree(customer):
    """Create the root and any template folder the customer does not have yet. Returns number created."""
    root = get_root(customer)
    existing = {
        r.template_path: r.name
        for r in frappe.get_all(FOLDER, filters={"customer": customer, "template_path": ["is", "set"]}, fields=["name", "template_path"])
    }
    created = 0
    for path, parent_path in template_paths().items():
        if path in existing:
            continue
        parent = existing.get(parent_path) if parent_path else root
        if not parent:
            continue
        doc = frappe.get_doc(
            {"doctype": FOLDER, "customer": customer, "folder_name": path.rsplit("/", 1)[-1], "parent_customer_archive_folder": parent, "template_path": path}
        )
        doc.flags.ignore_permissions = True
        doc.insert(ignore_permissions=True)
        existing[path] = doc.name
        created += 1
    return created


def ensure_tree_for_customer(doc, method=None):
    """doc_events hook: build the archive tree when a customer is created."""
    try:
        ensure_customer_tree(doc.name)
    except Exception:
        frappe.log_error(title=f"archive tree for {doc.name} failed")


# ---------------------------------------------------------------- tree
@frappe.whitelist()
def get_tree(customer):
    _check(customer)
    ensure_customer_tree(customer)
    folders = frappe.get_all(
        FOLDER,
        filters={"customer": customer},
        fields=["name", "folder_name", "parent_customer_archive_folder as parent", "is_root", "template_path", "lft"],
        order_by="lft asc",
    )
    counts = dict(
        frappe.db.sql(
            "SELECT folder, COUNT(name) FROM `tabCustomer Document` WHERE customer = %s GROUP BY folder", customer
        )
    )
    for f in folders:
        f.file_count = cint(counts.get(f.name))
    return {"folders": folders, "can_delete": _is_manager(), "total_files": sum(counts.values())}


@frappe.whitelist()
def add_folder(customer, parent, folder_name):
    _check(customer, "write")
    doc = frappe.get_doc({"doctype": FOLDER, "customer": customer, "folder_name": folder_name, "parent_customer_archive_folder": parent})
    doc.insert()
    return doc.name


@frappe.whitelist()
def rename_folder(name, folder_name):
    doc = frappe.get_doc(FOLDER, name)
    _check(doc.customer, "write")
    if doc.is_root:
        frappe.throw(_("لا يمكن إعادة تسمية المجلد الرئيسي."))
    doc.folder_name = folder_name
    doc.save()
    return doc.name


@frappe.whitelist()
def delete_folder(name):
    frappe.only_for(MANAGER_ROLES)
    doc = frappe.get_doc(FOLDER, name)
    _check(doc.customer, "write")
    doc.delete()
    return True


@frappe.whitelist()
def apply_template(customer):
    _check(customer, "write")
    return ensure_customer_tree(customer)


# ---------------------------------------------------------------- documents
@frappe.whitelist()
def get_documents(customer, folder=None, year=None, search=None, include_subfolders=0):
    _check(customer)
    filters = {"customer": customer}
    if folder:
        if cint(include_subfolders):
            lft, rgt = frappe.db.get_value(FOLDER, folder, ["lft", "rgt"])
            filters["folder"] = ["in", frappe.get_all(FOLDER, {"customer": customer, "lft": [">=", lft], "rgt": ["<=", rgt]}, pluck="name")]
        else:
            filters["folder"] = folder
    if year:
        filters["year"] = cint(year)
    or_filters = None
    if search:
        like = f"%{search}%"
        or_filters = [["file_name", "like", like], ["description", "like", like], ["keywords", "like", like]]
    return frappe.get_all(
        DOCUMENT,
        filters=filters,
        or_filters=or_filters,
        fields=["name", "file", "file_name", "file_size", "folder", "folder_name", "document_date", "year", "month", "description", "uploaded_by", "uploaded_on", "expiry_date"],
        order_by="document_date desc, uploaded_on desc",
        limit_page_length=1000,
    )


@frappe.whitelist()
def register_upload(customer, folder, file_name, year=None, month=None, document_date=None, description=None, keywords=None):
    """Turn an uploaded File (attached to the customer by the uploader) into a Customer Document."""
    _check(customer, "write")
    file_doc = frappe.get_doc("File", file_name)
    if file_doc.attached_to_doctype != "Customer" or file_doc.attached_to_name != customer:
        frappe.throw(_("الملف غير مرتبط بهذا العميل."))
    doc = frappe.get_doc(
        {
            "doctype": DOCUMENT,
            "customer": customer,
            "folder": folder,
            "file": file_doc.file_url,
            "file_name": file_doc.file_name,
            "file_size": file_doc.file_size,
            "year": cint(year) or None,
            "month": str(cint(month)) if cint(month) else None,
            "document_date": document_date or None,
            "description": description,
            "keywords": keywords,
            "uploaded_by": frappe.session.user,
            "uploaded_on": now_datetime(),
        }
    )
    doc.insert()
    return doc.name


@frappe.whitelist()
def move_documents(names, folder):
    names = _parse_names(names)
    target_customer = frappe.db.get_value(FOLDER, folder, "customer")
    folder_name = frappe.db.get_value(FOLDER, folder, "folder_name")
    moved = 0
    for name in names:
        doc = frappe.get_doc(DOCUMENT, name)
        _check(doc.customer, "write")
        if doc.customer != target_customer:
            frappe.throw(_("لا يمكن نقل الملف إلى مجلد عميل آخر."))
        if doc.folder != folder:
            doc.folder = folder
            doc.folder_name = folder_name
            doc.save()
            moved += 1
    return moved


@frappe.whitelist()
def delete_documents(names):
    frappe.only_for(MANAGER_ROLES)
    deleted = 0
    for name in _parse_names(names):
        frappe.delete_doc(DOCUMENT, name)
        deleted += 1
    return deleted


@frappe.whitelist()
def download_zip(names):
    names = _parse_names(names)
    if not names:
        frappe.throw(_("لم يتم تحديد ملفات."))
    buffer = io.BytesIO()
    used = set()
    customer = None
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as zf:
        for name in names:
            doc = frappe.get_doc(DOCUMENT, name)
            _check(doc.customer)
            customer = customer or doc.customer
            path = get_file_path(doc.file)
            arcname = f"{doc.folder_name or 'files'}/{doc.file_name or path.rsplit('/', 1)[-1]}"
            while arcname in used:
                arcname = arcname.replace("/", f"/{doc.name}-", 1)
            used.add(arcname)
            zf.write(path, arcname)
    frappe.response["filename"] = f"archive-{customer or 'files'}.zip"
    frappe.response["filecontent"] = buffer.getvalue()
    frappe.response["type"] = "download"
