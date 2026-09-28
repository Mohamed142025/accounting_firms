import frappe
from frappe import _
from frappe.utils import getdate


DATE_TABLES = {
    "tax_card": ("issue_date", "expiry_date"),
    "vat_registration": ("issue_date", "expiry_date"),
    "licenses": ("issue_date", "expiry_date"),
    "construction_federation_membership": ("issue_date", "expiry_date"),
    "token_data": ("issue_date", "expiry_date"),
    "facilitations": ("from_date", "to_date"),
    "advance_payments": ("subscription_start_date", "subscription_end_date"),
}


class AccountingFirmsCustomer:
    def autoname(self):
        if self.get("company_code"):
            self.name = self.company_code.strip().upper()
            return
        super().autoname()

    def validate(self):
        super().validate()
        self._validate_company_code()
        self._validate_parent_company()
        self._validate_date_ranges()
        self._validate_branch_codes()

    def _validate_company_code(self):
        is_new_customer = self.is_new() or not self.name
        code = (self.company_code or "").strip() if self.get("company_code") else ""
        if code:
            self.company_code = code.upper()

        if is_new_customer and not self.company_code:
            frappe.throw(_("كود الشركة مطلوب عند إنشاء عميل جديد."))

        if not self.company_status:
            if is_new_customer:
                self.company_status = "Active"
            else:
                return

        if not is_new_customer and self.has_value_changed("company_code"):
            frappe.throw(_("لا يمكن تعديل كود الشركة بعد الحفظ لأنه معرف ثابت للعميل."))

        if self.company_code:
            duplicate = frappe.db.exists(
                "Customer",
                {"company_code": self.company_code, "name": ["!=", self.name]},
            )
            if duplicate:
                frappe.throw(_("كود الشركة مستخدم بالفعل، برجاء إدخال كود مختلف."))

    def _validate_parent_company(self):
        if not self.parent_company_group:
            return
        if self.parent_company_group == self.name:
            frappe.throw(_("لا يمكن أن تكون الشركة تابعة لنفسها."))

        visited = {self.name}
        current = self.parent_company_group
        while current:
            if current in visited:
                frappe.throw(_("لا يمكن إنشاء علاقة دائرية بين الشركات."))
            visited.add(current)
            current = frappe.db.get_value("Customer", current, "parent_company_group")

    def _validate_date_ranges(self):
        for table_field, (start_field, end_field) in DATE_TABLES.items():
            for row in self.get(table_field) or []:
                start = getdate(row.get(start_field)) if row.get(start_field) else None
                end = getdate(row.get(end_field)) if row.get(end_field) else None
                if start and end and end < start:
                    frappe.throw(
                        _("تاريخ الانتهاء لا يمكن أن يكون قبل تاريخ الإصدار في {0}.").format(
                            row.doctype
                        )
                    )

    def _validate_branch_codes(self):
        seen = set()
        for row in self.get("customer_branches") or []:
            code = (row.branch_code or "").strip()
            if not code:
                frappe.throw(_("كود الفرع مطلوب لكل فرع."))
            normalized = code.upper()
            if normalized in seen:
                frappe.throw(_("لا يمكن تكرار كود الفرع داخل نفس العميل."))
            seen.add(normalized)
            row.branch_code = code
