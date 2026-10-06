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
  "tax_platform_accounts",
  "e_invoice_profiles",
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

frappe.ui.form.on("Tax Platform Account", {
  show_password(frm, cdt, cdn) {
    const gridRow = getGridRow(frm, cdn);
    const input =
      gridRow?.get_field("password")?.$input ||
      gridRow?.row?.find('[data-fieldname="password"] input');
    const buttonField = gridRow?.get_field("show_password");
    if (!input?.length) return;

    if (input.attr("type") === "text") {
      input.attr("type", "password");
      buttonField?.set_label(__("عرض كلمة المرور"));
      return;
    }

    frappe.call({
      method: "accounting_firms.accounting_firms.doctype.tax_platform_account.tax_platform_account.get_password",
      args: { name: cdn, parent: frm.doc.name },
      btn: buttonField?.$input,
    }).then(({ message }) => {
      if (message) {
        input.attr("type", "text").val(message);
        buttonField?.set_label(__("إخفاء كلمة المرور"));
      }
    });
  },

  open_link(frm, cdt, cdn) {
    const row = frappe.get_doc(cdt, cdn);
    if (row.__islocal || frm.is_dirty()) {
      frappe.msgprint(__("احفظ العميل أولاً ثم اضغط فتح المنصة."));
      return;
    }

    // open synchronously so the browser does not block the popup
    const portal = window.open(row.login_url || "about:blank", "_blank");

    frappe.call({
      method: "accounting_firms.accounting_firms.doctype.tax_platform_account.tax_platform_account.get_login_payload",
      args: { name: cdn, parent: frm.doc.name },
    }).then(({ message }) => {
      if (!message) return;
      if (portal && !row.login_url && message.login_url) {
        portal.location = message.login_url;
      }
      // hand the login data to the browser extension (phase 2); harmless if not installed
      window.postMessage(
        { type: "ACCOUNTING_FIRMS_AUTOLOGIN", payload: message },
        window.location.origin,
      );
      showCredentialsDialog(message);
    });
  },
});

function getGridRow(frm, cdn) {
  const grid = frm.grids
    .map((tableField) => tableField.grid)
    .find((tableGrid) => tableGrid.grid_rows_by_docname?.[cdn]);
  return grid?.grid_rows_by_docname?.[cdn];
}

function copyToClipboard(text) {
  if (navigator.clipboard?.writeText) {
    return navigator.clipboard.writeText(text);
  }
  const helper = $("<textarea>").val(text).appendTo("body").select();
  document.execCommand("copy");
  helper.remove();
  return Promise.resolve();
}

function extensionHint() {
  if (document.documentElement.dataset.accountingFirmsExtension) {
    return `<p class="text-muted small">${__("تم فتح المنصة وإرسال بيانات الدخول لإضافة المتصفح لملئها تلقائيًا.")}</p>`;
  }
  const link = "/assets/accounting_firms/extension/accounting-firms-auto-login.zip";
  return `<p class="text-muted small">${__("تم فتح المنصة في نافذة جديدة. انسخ البيانات والصقها في صفحة الدخول.")}<br>${__(
    "للتعبئة التلقائية سطّب إضافة المتصفح:",
  )} <a href="${link}" target="_blank">${__("تحميل الإضافة")}</a></p>`;
}

function showCredentialsDialog(data) {
  const dialog = new frappe.ui.Dialog({
    title: __("بيانات الدخول: {0}", [data.platform]),
    fields: [
      { fieldtype: "Data", fieldname: "username", label: __("اسم المستخدم"), default: data.username || "", read_only: 1 },
      { fieldtype: "Button", fieldname: "copy_username", label: __("نسخ اسم المستخدم") },
      { fieldtype: "Column Break" },
      {
        fieldtype: "Data",
        fieldname: "password",
        label: __("كلمة المرور"),
        default: data.password ? "••••••••" : __("غير متاحة لصلاحياتك"),
        read_only: 1,
      },
      { fieldtype: "Button", fieldname: "copy_password", label: __("نسخ كلمة المرور"), hidden: data.password ? 0 : 1 },
      { fieldtype: "Section Break" },
      {
        fieldtype: "HTML",
        fieldname: "hint",
        options: extensionHint(),
      },
    ],
    primary_action_label: __("إغلاق"),
    primary_action: () => dialog.hide(),
  });

  dialog.fields_dict.copy_username.$input.on("click", () => {
    copyToClipboard(data.username || "").then(() => frappe.show_alert({ message: __("تم نسخ اسم المستخدم"), indicator: "green" }));
  });
  dialog.fields_dict.copy_password.$input.on("click", () => {
    copyToClipboard(data.password || "").then(() => frappe.show_alert({ message: __("تم نسخ كلمة المرور"), indicator: "green" }));
  });
  dialog.show();
}

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
