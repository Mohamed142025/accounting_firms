const dateRanges = [
  ["tax_card", "issue_date", "expiry_date"],
  ["vat_registration", "issue_date", "expiry_date"],
  ["licenses", "issue_date", "expiry_date"],
  ["construction_federation_membership", "issue_date", "expiry_date"],
  ["token_data", "issue_date", "expiry_date"],
  ["facilitations", "from_date", "to_date"],
  ["advance_payments", "subscription_start_date", "subscription_end_date"],
];

frappe.ui.form.on("Customer", {
  setup(frm) {
    frm.set_query("parent_company_group", () => ({
      filters: [["Customer", "name", "!=", frm.doc.name || ""]],
    }));
  },

  refresh(frm) {
    const isNew = frm.is_new();
    frm.set_df_property("company_code", "reqd", isNew ? 1 : 0);
    frm.set_df_property("company_code", "read_only", isNew ? 0 : 1);
    frm.set_df_property("company_status", "reqd", isNew ? 1 : 0);
    loadExpiryAlert(frm);
  },

  validate(frm) {
    if (frm.doc.company_code) {
      frm.set_value("company_code", frm.doc.company_code.trim().toUpperCase());
    }

    if (frm.is_new() && !frm.doc.company_status) {
      frm.set_value("company_status", "Active");
    }

    validateDateRanges(frm);
    validateBranchCodes(frm);
  },
});

frappe.ui.form.on("Tax Email Configuration", {
  show_password(frm, cdt, cdn) {
    const grid = frm.grids
      .map((tableField) => tableField.grid)
      .find((tableGrid) => tableGrid.grid_rows_by_docname?.[cdn]);
    const gridRow = grid?.grid_rows_by_docname?.[cdn];
    const passwordField = gridRow?.get_field("email_password");
    const buttonField = gridRow?.get_field("show_password");
    const input = passwordField?.$input || gridRow?.row?.find('[data-fieldname="email_password"] input');

    if (!input?.length) return;

    if (input.attr("type") === "text") {
      input.attr("type", "password");
      buttonField?.set_label(__("عرض كلمة المرور"));
      return;
    }

    frappe.call({
      method: "accounting_firms.accounting_firms.doctype.tax_email_configuration.tax_email_configuration.get_password",
      args: { name: cdn, parent: frm.doc.name },
      btn: buttonField?.$input,
    }).then(({ message }) => {
      if (message) {
        input.attr("type", "text").val(message);
        buttonField?.set_label(__("إخفاء كلمة المرور"));
      }
    });
  },
});

function validateDateRanges(frm) {
  dateRanges.forEach(([tableField, startField, endField]) => {
    (frm.doc[tableField] || []).forEach((row) => {
      if (row[startField] && row[endField] && row[endField] < row[startField]) {
        frappe.throw(__("تاريخ الانتهاء لا يمكن أن يكون قبل تاريخ الإصدار."));
      }
    });
  });
}

function validateBranchCodes(frm) {
  const seen = new Set();
  (frm.doc.customer_branches || []).forEach((row) => {
    const code = (row.branch_code || "").trim().toUpperCase();
    if (!code) {
      frappe.throw(__("كود الفرع مطلوب لكل فرع."));
    }
    if (seen.has(code)) {
      frappe.throw(__("لا يمكن تكرار كود الفرع داخل نفس العميل."));
    }
    seen.add(code);
  });
}

function loadExpiryAlert(frm) {
  if (frm.is_new()) {
    frm.dashboard.clear_headline();
    return;
  }

  frappe.call({
    method: "accounting_firms.accounting_firms.report.document_expiry_monitor.document_expiry_monitor.get_customer_expiry_summary",
    args: { customer: frm.doc.name },
  }).then(({ message }) => {
    const summary = message?.summary;
    if (!summary) return;

    if (summary.expired) {
      frm.dashboard.set_headline_alert(
        __("يوجد {0} مستند منتهي و{1} مستند قريب الانتهاء.", [summary.expired, summary.due_soon]),
        "red",
        true,
      );
    } else if (summary.due_soon) {
      frm.dashboard.set_headline_alert(
        __("يوجد {0} مستند قريب الانتهاء خلال 30 يوم.", [summary.due_soon]),
        "orange",
        true,
      );
    } else {
      frm.dashboard.clear_headline();
    }
  });
}
