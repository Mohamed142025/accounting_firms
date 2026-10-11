import frappe
from frappe import _
from frappe.utils.nestedset import NestedSet


class CustomerArchiveFolder(NestedSet):
    nsm_parent_field = "parent_customer_archive_folder"
    allow_root_deletion = True

    def validate(self):
        self.is_group = 1
        self.folder_name = (self.folder_name or "").strip()
        if not self.folder_name:
            frappe.throw(_("اسم المجلد مطلوب."))
        if self.parent_customer_archive_folder:
            parent_customer = frappe.db.get_value("Customer Archive Folder", self.parent_customer_archive_folder, "customer")
            if parent_customer != self.customer:
                frappe.throw(_("المجلد الأب يتبع عميلًا آخر."))
        elif not self.is_root:
            frappe.throw(_("لا يمكن إنشاء مجلد بدون مجلد أب."))
        duplicate = frappe.db.exists(
            "Customer Archive Folder",
            {
                "customer": self.customer,
                "folder_name": self.folder_name,
                "parent_customer_archive_folder": self.parent_customer_archive_folder or "",
                "name": ["!=", self.name],
            },
        )
        if duplicate:
            frappe.throw(_("يوجد مجلد بنفس الاسم في نفس المستوى."))

    def on_trash(self):
        if self.is_root and not frappe.flags.in_delete_customer:
            frappe.throw(_("لا يمكن حذف المجلد الرئيسي لأرشيف العميل."))
        if frappe.db.exists("Customer Document", {"folder": self.name}):
            frappe.throw(_("المجلد يحتوي على ملفات. انقل الملفات أو احذفها أولاً."))
        if frappe.db.exists("Customer Archive Folder", {"parent_customer_archive_folder": self.name}):
            frappe.throw(_("المجلد يحتوي على مجلدات فرعية. احذفها أولاً."))
        super().on_trash()
