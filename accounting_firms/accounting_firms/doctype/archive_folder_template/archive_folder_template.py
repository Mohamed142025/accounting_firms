import frappe
from frappe import _
from frappe.utils.nestedset import NestedSet


class ArchiveFolderTemplate(NestedSet):
    nsm_parent_field = "parent_archive_folder_template"

    def validate(self):
        self.is_group = 1
        self.folder_name = (self.folder_name or "").strip()
        duplicate = frappe.db.exists(
            "Archive Folder Template",
            {"folder_name": self.folder_name, "parent_archive_folder_template": self.parent_archive_folder_template or "", "name": ["!=", self.name]},
        )
        if duplicate:
            frappe.throw(_("يوجد مجلد بنفس الاسم في نفس المستوى."))
