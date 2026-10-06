const dateRanges = [
  ["tax_card", "issue_date", "expiry_date"],
  ["vat_registration", "issue_date", "expiry_date"],
  ["licenses", "issue_date", "expiry_date"],
  ["construction_federation_membership", "issue_date", "expiry_date"],
  ["import_cards", "issue_date", "expiry_date"],
  ["export_cards", "issue_date", "expiry_date"],
  ["token_data", "issue_date", "expiry_date"],
  ["facilitations", "from_date", "to_date"],
  ["advance_payments", "subscription_start_date", "subscription_end_date"],
];

// child tables that carry a `branch` link to Customer Branch
const branchTables = [
  "tax_card",
  "vat_registration",
  "commercial_register",
  "licenses",
  "construction_federation_membership",
  "import_cards",
  "export_cards",
  "tax_email_configuration",
  "token_data",
  "facilitations",
  "advance_payments",
  "social_insurance",
];

frappe.ui.form.on("Customer", {
  setup(frm) {
    frm.set_query("parent_company_group", () => ({
      filters: [["Customer", "name", "!=", frm.doc.name || ""]],
    }));

    // only this customer's active branches are selectable in child rows
    branchTables.forEach((tableField) => {
      frm.set_query("branch", tableField, () => ({
        filters: { customer: frm.doc.name || "", status: "Active" },
      }));
    });
  },

  refresh(frm) {
    const isNew = frm.is_new();
    frm.set_df_property("company_code", "reqd", isNew ? 1 : 0);
    frm.set_df_property("company_code", "read_only", isNew ? 0 : 1);
    frm.set_df_property("company_status", "reqd", isNew ? 1 : 0);

    if (!isNew) {
      frm.add_custom_button(
        __("فرع جديد"),
        () => frappe.new_doc("Customer Branch", { customer: frm.doc.name }),
        __("إنشاء"),
      );
    }

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
    const label = frappe.meta.get_label("Customer", tableField, frm.doc.name) || tableField;
    (frm.doc[tableField] || []).forEach((row) => {
      if (row[startField] && row[endField] && row[endField] < row[startField]) {
        frappe.throw(
          __("تاريخ الانتهاء لا يمكن أن يكون قبل تاريخ الإصدار في {0} (صف {1}).", [label, row.idx]),
        );
      }
    });
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
