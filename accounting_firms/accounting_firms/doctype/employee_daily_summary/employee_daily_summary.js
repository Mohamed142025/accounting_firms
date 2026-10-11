frappe.ui.form.on("Employee Daily Summary", {
  onload(frm) {
    if (frm.is_new() && !frm.doc.employee) {
      frappe.db.get_value("Employee", { user_id: frappe.session.user }, "name").then(({ message }) => {
        if (message?.name) frm.set_value("employee", message.name);
      });
    }
  },
  refresh(frm) {
    if (!frm.is_new() && frm.doc.needs_follow_up) {
      frm.dashboard.set_headline_alert(__("هذا الملخص يحتاج متابعة من المدير"), "orange");
    }
  },
});

frappe.ui.form.on("Daily Summary Item", {
  hours(frm) {
    const total = (frm.doc.work_items || []).reduce((sum, row) => sum + flt(row.hours), 0);
    frm.set_value("total_hours", flt(total, 1));
  },
  work_items_remove(frm) {
    const total = (frm.doc.work_items || []).reduce((sum, row) => sum + flt(row.hours), 0);
    frm.set_value("total_hours", flt(total, 1));
  },
});
