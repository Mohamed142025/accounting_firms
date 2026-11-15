// Service tasks (made from a Service Task Map): claim a task given to a department / role,
// close an optional one as not applicable, and see why a task has not started yet.
frappe.ui.form.on("Task", {
  status(frm) {
    // ERPNext asks for the completion date; a service task takes today and the user
    if (frm.doc.af_root && frm.doc.status === "Completed") {
      if (!frm.doc.completed_on) frm.set_value("completed_on", frappe.datetime.get_today());
      if (!frm.doc.completed_by) frm.set_value("completed_by", frappe.session.user);
    }
  },

  refresh(frm) {
    const d = frm.doc;
    if (!d.af_root || frm.is_new()) return;
    const API = "accounting_firms.office_services.tasks";
    const open = !["Completed", "Cancelled"].includes(d.status);
    const notes = [];

    if (d.name === d.af_root) {
      frm.add_custom_button(__("مهام الخدمة"), () => frappe.set_route("List", "Task", { af_root: d.name }));
      if (d.af_customer) {
        frm.add_custom_button(__("العميل"), () => frappe.set_route("Form", "Customer", d.af_customer));
      }
    }

    if (open && d.name !== d.af_root && !d.af_ready) {
      notes.push(__("المهمة لسه ما بدأتش: مستنية المهام اللي قبلها تخلص، وبعدها هتتسند."));
    }

    // from docinfo: "_assign" is not sent to whom the task is only shared with
    const docinfo = frm.get_docinfo() || {};
    const assigned = docinfo.assignments ? docinfo.assignments.map((a) => a.owner) : JSON.parse(d._assign || "[]");
    if (open && d.af_pool && !d.af_claimed_by) {
      notes.push(__("المهمة مسندة لـ{0} شخص. أول واحد يضغط «استلام المهمة» بتبقى بتاعته.", [assigned.length]));
      if (assigned.includes(frappe.session.user)) {
        frm
          .add_custom_button(__("استلام المهمة"), () =>
            frappe.xcall(`${API}.claim`, { task: d.name }).then(() => {
              frappe.show_alert({ message: __("المهمة بقت بتاعتك."), indicator: "green" });
              frm.reload_doc();
            }),
          )
          .addClass("btn-primary");
      }
    }
    if (d.af_claimed_by) {
      notes.push(__("استلمها {0}.", [frappe.user.full_name(d.af_claimed_by)]));
    }

    if (open && d.af_ready && !d.af_mandatory && d.name !== d.af_root) {
      frm.add_custom_button(__("لا ينطبق"), () =>
        frappe.prompt(
          { fieldname: "reason", fieldtype: "Small Text", label: __("السبب") },
          ({ reason }) => frappe.xcall(`${API}.not_applicable`, { task: d.name, reason }).then(() => frm.reload_doc()),
          __("المهمة لا تنطبق"),
          __("تأكيد"),
        ),
      );
    }

    if (open && d.af_requires_attachment && !d.is_group) {
      notes.push(__("المهمة محتاجة مرفق قبل ما تتقفل."));
    }
    if (d.af_waiting_reason && open) {
      notes.push(__("الحالة: {0}", [__(d.af_waiting_reason)]));
    }
    frm.set_intro(notes.join("<br>"), notes.length ? "blue" : null);
  },
});
