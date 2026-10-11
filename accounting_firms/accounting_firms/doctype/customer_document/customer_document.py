import frappe
from frappe import _
from frappe.utils import now_datetime


class CustomerDocument(frappe.model.document.Document):
    def validate(self):
        folder_customer = frappe.db.get_value("Customer Archive Folder", self.folder, "customer")
        if folder_customer != self.customer:
            frappe.throw(_("المجلد المختار لا يتبع هذا العميل."))
        if not self.file_name and self.file:
            self.file_name = self.file.rsplit("/", 1)[-1]
        if not self.uploaded_by:
            self.uploaded_by = frappe.session.user
            self.uploaded_on = now_datetime()
        file_doc = frappe.db.get_value("File", {"file_url": self.file}, ["name", "file_size"], as_dict=True)
        if file_doc:
            self.file_size = file_doc.file_size

    def after_insert(self):
        self._attach_file()
        self._log(_("تم رفع ملف {0} في مجلد {1}"))

    def on_trash(self):
        frappe.only_for("System Manager")
        self._log(_("تم حذف ملف {0} من مجلد {1}"))

    def after_delete(self):
        for name in frappe.get_all("File", {"attached_to_doctype": self.doctype, "attached_to_name": self.name}, pluck="name"):
            frappe.delete_doc("File", name, ignore_permissions=True, force=True)

    def _attach_file(self):
        """Point the File record at this document so it is removed together with it."""
        file_name = frappe.db.get_value("File", {"file_url": self.file}, "name")
        if file_name:
            frappe.db.set_value(
                "File", file_name,
                {"attached_to_doctype": self.doctype, "attached_to_name": self.name, "attached_to_field": "file", "is_private": 1},
                update_modified=False,
            )

    def _log(self, template):
        frappe.get_doc(
            {
                "doctype": "Comment",
                "comment_type": "Info",
                "reference_doctype": "Customer",
                "reference_name": self.customer,
                "content": template.format(frappe.bold(self.file_name or self.file), frappe.bold(self.folder_name or self.folder)),
            }
        ).insert(ignore_permissions=True)
