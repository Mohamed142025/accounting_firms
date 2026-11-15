// Service Task Map: subtasks indented in the grid, and the whole map drawn as a tree.
frappe.ui.form.on("Service Task Map", {
  setup(frm) {
    const df = frappe.meta.get_docfield("Service Task Map Row", "task_title", frm.doc.name);
    df.formatter = (value, _df, _options, doc) => {
      const depth = ((doc && doc.task_no) || "").split(".").length - 1;
      const text = frappe.utils.escape_html(value || "");
      return depth ? `<span style="padding-inline-start:${depth * 18}px">↳ ${text}</span>` : `<b>${text}</b>`;
    };
    frm.set_query("employee", "tasks", () => ({ filters: { status: "Active", user_id: ["is", "set"] } }));
  },

  refresh(frm) {
    render_preview(frm);
  },

  tasks_remove(frm) {
    render_preview(frm);
  },
});

frappe.ui.form.on("Service Task Map Row", {
  task_no: render_preview,
  task_title: render_preview,
  assign_to_type(frm, cdt, cdn) {
    const row = locals[cdt][cdn];
    if (row.assign_to_type !== "رول") frappe.model.set_value(cdt, cdn, "role", null);
    if (row.assign_to_type !== "موظف") frappe.model.set_value(cdt, cdn, "employee", null);
    render_preview(frm);
  },
  department: render_preview,
  role: render_preview,
  employee(frm, cdt, cdn) {
    const row = locals[cdt][cdn];
    if (row.employee && !row.department) {
      frappe.db.get_value("Employee", row.employee, "department").then(({ message }) => {
        if (message?.department) frappe.model.set_value(cdt, cdn, "department", message.department);
      });
    }
    render_preview(frm);
  },
  execution: render_preview,
  expected_days: render_preview,
  mandatory: render_preview,
  requires_attachment: render_preview,
  applies_to: render_preview,

  choose_entities(frm, cdt, cdn) {
    const row = locals[cdt][cdn];
    const chosen = (row.applies_to || "").split("\n").map((s) => s.trim()).filter(Boolean);
    frappe
      .xcall("accounting_firms.accounting_firms.doctype.service_task_map.service_task_map.get_legal_entities")
      .then((entities) => {
        const dialog = new frappe.ui.Dialog({
          title: __("ينطبق على الكيانات"),
          fields: [
            {
              fieldname: "entities",
              fieldtype: "MultiCheck",
              columns: 2,
              options: entities.map((e) => ({ label: e, value: e, checked: chosen.includes(e) })),
              description: __("مفيش اختيار = كل الكيانات."),
            },
          ],
          primary_action_label: __("تم"),
          primary_action({ entities: picked }) {
            frappe.model.set_value(cdt, cdn, "applies_to", (picked || []).join("\n"));
            dialog.hide();
          },
        });
        dialog.show();
      });
  },
});

function sort_key(no) {
  return (no || "").split(".").map((p) => parseInt(p, 10) || 0);
}

function compare(a, b) {
  const x = sort_key(a.task_no), y = sort_key(b.task_no);
  for (let i = 0; i < Math.max(x.length, y.length); i++) {
    if ((x[i] ?? -1) !== (y[i] ?? -1)) return (x[i] ?? -1) - (y[i] ?? -1);
  }
  return 0;
}

function assignee_text(row) {
  const esc = frappe.utils.escape_html;
  switch (row.assign_to_type) {
    case "قسم":
      return __("كل {0}", [esc(row.department || "؟")]);
    case "مدير قسم":
      return __("مدير {0}", [esc(row.department || "؟")]);
    case "رول":
      return __("رول {0}", [esc(row.role || "؟")]);
    case "موظف":
      return esc(row.employee || "؟");
    default:
      return `<span class="text-danger">${__("مش محدد")}</span>`;
  }
}

function render_preview(frm) {
  const field = frm.fields_dict.map_preview;
  if (!field) return;
  const rows = [...(frm.doc.tasks || [])].filter((r) => r.task_no).sort(compare);
  if (!rows.length) {
    field.$wrapper.html(`<div class="text-muted">${__("ضيف المهام في الجدول اللي فوق.")}</div>`);
    return;
  }
  const esc = frappe.utils.escape_html;
  const items = rows
    .map((r) => {
      const depth = r.task_no.split(".").length - 1;
      const tags = [
        `<span class="indicator-pill ${r.execution === "متوازي" ? "purple" : "blue"}">${__(r.execution || "تسلسلي")}</span>`,
        r.expected_days ? `<span class="indicator-pill gray">${__("{0} يوم", [r.expected_days])}</span>` : "",
        r.mandatory ? "" : `<span class="indicator-pill yellow">${__("اختيارية")}</span>`,
        r.requires_attachment ? `<span class="indicator-pill orange">${__("مرفق")}</span>` : "",
        r.applies_to ? `<span class="indicator-pill gray" title="${esc(r.applies_to)}">${__("كيانات محددة")}</span>` : "",
      ].join(" ");
      return `<div style="display:flex;gap:10px;align-items:center;padding:6px 8px;border-bottom:1px solid var(--border-color);padding-inline-start:${8 + depth * 26}px">
        <span class="text-muted" style="min-width:34px">${esc(r.task_no)}</span>
        <span style="${depth ? "" : "font-weight:600"}">${depth ? "↳ " : ""}${esc(r.task_title || "")}</span>
        <span class="text-muted" style="margin-inline-start:auto">${assignee_text(r)}</span>
        <span>${tags}</span>
      </div>`;
    })
    .join("");
  field.$wrapper.html(`<div style="border:1px solid var(--border-color);border-radius:var(--border-radius-md)">${items}</div>`);
}
