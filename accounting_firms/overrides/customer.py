import frappe
from frappe import _
from frappe.utils import add_months, add_years, cint, flt, getdate


DATE_TABLES = {
    "tax_card": ("issue_date", "expiry_date"),
    "vat_registration": ("issue_date", "expiry_date"),
    "licenses": ("issue_date", "expiry_date"),
    "construction_federation_membership": ("issue_date", "expiry_date"),
    "commercial_register": ("issue_date", "expiry_5_months"),
    "trademarks": ("filing_date", "expiry_date"),
    "company_representatives": ("from_date", "to_date"),
    "import_cards": ("issue_date", "expiry_date"),
    "export_cards": ("issue_date", "expiry_date"),
    "token_data": ("issue_date", "expiry_date"),
    "facilitations": ("from_date", "to_date"),
    "advance_payments": ("subscription_start_date", "subscription_end_date"),
}

# child tables that carry a link to Customer Branch
BRANCH_TABLES = (
    "tax_card",
    "vat_registration",
    "commercial_register",
    "licenses",
    "trademarks",
    "construction_federation_membership",
    "import_cards",
    "export_cards",
    "tax_email_configuration",
    "token_data",
    "facilitations",
    "advance_payments",
    "social_insurance",
    "tax_platform_accounts",
    "e_invoice_profiles",
)


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
        self._set_default_expiry_dates()
        self._validate_date_ranges()
        self._validate_branches()
        self._validate_tax_emails()
        self._validate_related_companies()
        self._update_capital_summary()
        self._update_shareholders()

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
                    label = frappe.get_meta("Customer").get_label(table_field) or row.doctype
                    frappe.throw(
                        _("تاريخ الانتهاء لا يمكن أن يكون قبل تاريخ الإصدار في {0} (صف {1}).").format(
                            label, row.idx
                        )
                    )

    def _validate_branches(self):
        """Every branch referenced in a child row must belong to this customer."""
        used = set()
        for table_field in BRANCH_TABLES:
            for row in self.get(table_field) or []:
                if row.get("branch"):
                    used.add(row.branch)
        if not used:
            return

        owners = dict(
            frappe.get_all(
                "Customer Branch",
                filters={"name": ["in", list(used)]},
                fields=["name", "customer"],
                as_list=True,
            )
        )
        for table_field in BRANCH_TABLES:
            for row in self.get(table_field) or []:
                branch = row.get("branch")
                if not branch:
                    continue
                if owners.get(branch) != self.name:
                    label = frappe.get_meta("Customer").get_label(table_field) or row.doctype
                    frappe.throw(
                        _("الفرع {0} لا يتبع هذا العميل (في {1} صف {2}).").format(
                            frappe.bold(branch), label, row.idx
                        )
                    )

    def _validate_tax_emails(self):
        """A tax mailbox belongs to one customer and appears once: each row is read on its own,
        so a repeated one would bring every message twice."""
        seen = {}
        for row in self.get("tax_email_configuration") or []:
            # stripped only: the stored address is part of each message's duplicate key
            row.tax_email = (row.tax_email or "").strip() or row.tax_email
            email = (row.tax_email or "").lower()
            if not email:
                continue
            if email in seen:
                frappe.throw(
                    _("الإيميل الضريبي {0} مكرر في الصفين {1} و{2}.").format(frappe.bold(email), seen[email], row.idx)
                )
            seen[email] = row.idx
            if row.get("auth_method") == "OAuth" and not row.get("connected_app"):
                frappe.throw(_("اختار Connected App للإيميل {0} (صف {1}).").format(frappe.bold(email), row.idx))
        if not seen:
            return
        other = frappe.db.sql(
            """select cfg.tax_email, cfg.parent, c.customer_name
            from `tabTax Email Configuration` cfg
            join `tabCustomer` c on c.name = cfg.parent
            where cfg.parenttype = 'Customer' and cfg.parent != %s and lower(trim(cfg.tax_email)) in %s
            limit 1""",
            (self.name or "", tuple(seen)),
            as_dict=True,
        )
        if other:
            frappe.throw(
                _("الإيميل الضريبي {0} مسجل بالفعل للعميل {1}.").format(
                    frappe.bold(other[0].tax_email), frappe.bold(f"{other[0].customer_name} ({other[0].parent})")
                )
            )

    def _set_default_expiry_dates(self):
        """Fill expiry dates the user left empty (commercial register: 3 months / 5 years, trademark: 10 years)."""
        for row in self.get("commercial_register") or []:
            if row.issue_date:
                if not row.expiry_3_months:
                    row.expiry_3_months = add_months(getdate(row.issue_date), 3)
                if not row.expiry_5_months:
                    row.expiry_5_months = add_years(getdate(row.issue_date), 5)
        for row in self.get("trademarks") or []:
            if row.filing_date and not row.expiry_date:
                row.expiry_date = add_years(getdate(row.filing_date), 10)

    def _validate_related_companies(self):
        rows = self.get("related_companies") or []
        if rows and not self.get("has_related_companies"):
            frappe.throw(_("جدول الشركات المرتبطة به بيانات. علّم على \"يوجد ارتباط مع شركات أخرى\" أو احذف الصفوف."))
        for row in rows:
            if row.related_customer and row.related_customer == self.name:
                frappe.throw(_("لا يمكن ربط الشركة بنفسها (صف {0}).").format(row.idx))
            if row.has_share and row.share_percent and not (0 < row.share_percent <= 100):
                frappe.throw(_("نسبة الحصة يجب أن تكون بين 0 و 100 (صف {0}).").format(row.idx))

    def _update_capital_summary(self):
        """Current capital = the latest capital change row; also sanity-check each row."""
        rows = self.get("capital_changes") or []
        for row in rows:
            authorized, issued, paid = flt(row.authorized_capital), flt(row.issued_capital), flt(row.paid_capital)
            if issued and authorized and issued > authorized:
                frappe.throw(_("رأس المال المصدر لا يمكن أن يتجاوز المرخص (حركة رأس المال صف {0}).").format(row.idx))
            if paid and issued and paid > issued:
                frappe.throw(_("رأس المال المدفوع لا يمكن أن يتجاوز المصدر (حركة رأس المال صف {0}).").format(row.idx))
        latest = max(rows, key=lambda r: (getdate(r.change_date), r.idx)) if rows else None
        self.authorized_capital = flt(latest.authorized_capital) if latest else 0
        self.issued_capital = flt(latest.issued_capital) if latest else 0
        self.paid_capital = flt(latest.paid_capital) if latest else 0
        self.total_shares = cint(latest.total_shares) if latest else 0
        self.share_par_value = flt(latest.share_par_value) if latest else 0

    def _update_shareholders(self):
        total_shares = cint(self.get("total_shares"))
        total_percent = 0
        for row in self.get("shareholders") or []:
            row.shares_value = flt(row.number_of_shares) * flt(row.share_price)
            if total_shares and row.number_of_shares:
                row.share_percent = flt(row.number_of_shares) * 100 / total_shares
            if row.share_percent and not (0 < flt(row.share_percent) <= 100):
                frappe.throw(_("نسبة المساهمة يجب أن تكون بين 0 و 100 (المساهمون صف {0}).").format(row.idx))
            if row.status == "حالي":
                total_percent += flt(row.share_percent)
        if total_percent > 100.001:
            frappe.throw(_("مجموع نسب المساهمين الحاليين ({0}%) يتجاوز 100%.").format(flt(total_percent, 2)))
        self.shareholders_total_percent = flt(total_percent, 2)
