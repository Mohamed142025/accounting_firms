// "New service task" on the Customer form: pick one of the customer's active services, see
// the tasks its map will create and who gets each, leave out optional ones or give a task to
// someone in particular, then create them.
(function () {
  const API = "accounting_firms.office_services.tasks";
  const esc = frappe.utils.escape_html;
  const PRIORITIES = ["Low", "Medium", "High", "Urgent"];

  function open_dialog(frm, service) {
    if (frm.is_dirty()) {
      frappe.msgprint(__("احفظ العميل الأول."));
      return;
    }
    frappe.xcall(`${API}.get_new_task_context`, { customer: frm.doc.name }).then((ctx) => {
      if (!ctx.services.length) {
        frappe.msgprint(__("العميل مالوش خدمات نشطة. علّم على خدماته في تاب «الخدمات» الأول."));
        return;
      }
      const dialog = new frappe.ui.Dialog({
        title: __("مهمة خدمة جديدة — {0}", [frm.doc.customer_name || frm.doc.name]),
        size: "extra-large",
        fields: [
          {
            fieldname: "service",
            fieldtype: "Select",
            label: __("الخدمة"),
            reqd: 1,
            options: [{ value: "", label: "" }].concat(ctx.services.map((s) => ({ value: s.service, label: s.service_name }))),
            default: service || "",
            change: () => load(dialog.get_value("service")),
          },
          { fieldname: "period", fieldtype: "Data", label: __("الفترة"), description: __("للخدمات الدورية، مثلاً 2026-11 أو Q4-2026.") },
          { fieldtype: "Column Break" },
          { fieldname: "due_date", fieldtype: "Date", label: __("تاريخ التسليم") },
          {
            fieldname: "priority",
            fieldtype: "Select",
            label: __("الأولوية"),
            options: PRIORITIES.map((p) => ({ value: p, label: __(p) })),
            default: "Medium",
          },
          { fieldtype: "Section Break" },
          { fieldname: "notes", fieldtype: "Small Text", label: __("ملاحظات") },
          { fieldtype: "Section Break", label: __("المهام اللي هتتعمل") },
          { fieldname: "preview", fieldtype: "HTML" },
        ],
        primary_action_label: __("إنشاء المهام"),
        primary_action: () => create(),
      });
      let current = null;

      function load(svc) {
        current = null;
        const $p = dialog.get_field("preview").$wrapper;
        if (!svc) {
          $p.html(`<div class="text-muted">${__("اختار الخدمة.")}</div>`);
          return;
        }
        $p.html(`<div class="text-muted">${__("جاري التحميل...")}</div>`);
        frappe.xcall(`${API}.get_new_task_context`, { customer: frm.doc.name, service: svc }).then((c) => {
          current = c;
          dialog.set_value("period", c.period || "");
          render(c);
        });
      }

      function employee_options(selected) {
        return [`<option value="">${__("حسب الخريطة")}</option>`]
          .concat(current.employees.map((e) => `<option value="${esc(e.user)}" ${e.user === selected ? "selected" : ""}>${esc(e.employee_name)}</option>`))
          .join("");
      }

      function render(c) {
        const $p = dialog.get_field("preview").$wrapper;
        if (!c.has_map) {
          $p.html(`
            <div class="alert alert-warning">${__("الخدمة دي مالهاش خريطة مهام، فهتتعمل مهمة واحدة.")}
              <a href="/app/service-task-map/new?service=${encodeURIComponent(dialog.get_value("service"))}">${__("اعمل خريطة")}</a></div>
            <label>${__("مسندة إلى")}</label>
            <select class="form-control af-st-user" data-task="">${employee_options()}</select>`);
          return;
        }
        const rows = c.rows
          .map((r) => {
            const pad = r.depth * 22;
            const people = r.candidates.length
              ? r.candidates.length > 3
                ? __("{0} شخص", [r.candidates.length])
                : r.candidates.map((p) => esc(p.full_name)).join("، ")
              : `<span class="text-danger">${__("مفيش حد")}</span>`;
            const include = r.skipped
              ? `<span class="text-muted" title="${esc(r.skipped)}">—</span>`
              : `<input type="checkbox" class="af-st-include" data-task="${esc(r.task_no)}" checked ${r.mandatory ? "disabled" : ""}>`;
            return `<tr class="${r.skipped ? "text-muted" : ""}">
              <td style="width:36px;text-align:center">${include}</td>
              <td style="padding-inline-start:${8 + pad}px">${r.depth ? "↳ " : ""}${esc(r.task_title)}
                ${r.mandatory ? "" : `<span class="indicator-pill yellow">${__("اختيارية")}</span>`}
                ${r.skipped ? `<div class="small">${esc(r.skipped)}</div>` : ""}</td>
              <td>${esc(r.assign)}<div class="small text-muted">${people}</div></td>
              <td style="width:200px">${r.skipped ? "" : `<select class="form-control input-xs af-st-user" data-task="${esc(r.task_no)}">${employee_options()}</select>`}</td>
              <td style="width:110px">${__(r.execution || "تسلسلي")}${r.expected_days ? ` · ${__("{0} يوم", [r.expected_days])}` : ""}</td>
            </tr>`;
          })
          .join("");
        $p.html(`
          <div class="small text-muted" style="margin-bottom:6px">${__("كيان العميل: {0}", [esc(c.legal_entity || __("غير محدد"))])}</div>
          <div style="max-height:50vh;overflow:auto"><table class="table table-bordered table-sm">
            <thead><tr><th></th><th>${__("المهمة")}</th><th>${__("حسب الخريطة")}</th><th>${__("تغيير المسؤول")}</th><th>${__("التنفيذ")}</th></tr></thead>
            <tbody>${rows}</tbody></table></div>`);
      }

      function chosen_rows() {
        const $p = dialog.get_field("preview").$wrapper;
        const out = {};
        $p.find(".af-st-include").each((_i, el) => {
          (out[el.dataset.task] ||= { task_no: el.dataset.task }).include = el.checked ? 1 : 0;
        });
        $p.find(".af-st-user").each((_i, el) => {
          if (el.value) (out[el.dataset.task] ||= { task_no: el.dataset.task }).user = el.value;
        });
        return Object.values(out);
      }

      function create(force) {
        const values = dialog.get_values();
        if (!values || !current) return;
        frappe.call({
          method: `${API}.create_service_tasks`,
          args: {
            customer: frm.doc.name,
            service: values.service,
            period: values.period,
            due_date: values.due_date,
            priority: values.priority,
            notes: values.notes,
            rows: chosen_rows(),
            force: force ? 1 : 0,
          },
          freeze: true,
          freeze_message: __("جاري إنشاء المهام..."),
          callback: (r) => {
            if (!r.message) return;
            dialog.hide();
            frappe.show_alert({ message: __("اتعملت مهام الخدمة."), indicator: "green" });
            frm.af_services?.load();
            frappe.set_route("Form", "Task", r.message);
          },
          error: (r) => {
            if (r?.exc_type === "DuplicateServiceTask") {
              frappe.confirm(__("فيه مهمة مفتوحة على نفس الخدمة والفترة. تعمل واحدة جديدة برضه؟"), () => create(true));
            }
          },
        });
      }

      dialog.show();
      load(service || "");
    });
  }

  window.af_new_service_task = open_dialog;

  frappe.ui.form.on("Customer", {
    refresh(frm) {
      if (frm.is_new() || !frm.fields_dict.office_services) return;
      frm.add_custom_button(__("مهمة خدمة"), () => open_dialog(frm), __("إنشاء"));
    },
  });
})();
