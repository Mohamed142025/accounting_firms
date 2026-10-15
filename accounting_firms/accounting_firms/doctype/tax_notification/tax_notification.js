const TN_SET_STATUS = "accounting_firms.accounting_firms.doctype.tax_notification.tax_notification.set_status";

frappe.ui.form.on("Tax Notification", {
  refresh(frm) {
    if (frm.is_new() || !frm.perm[0]?.write) return;
    const open = ["جديد", "تحت المراجعة"].includes(frm.doc.status);
    const move = (status) =>
      frappe
        .call({ method: TN_SET_STATUS, args: { names: [frm.doc.name], status }, freeze: true })
        .then(() => frm.reload_doc());

    if (open) {
      frm.add_custom_button(__("تم التعامل"), () => move("تم التعامل")).addClass("btn-primary");
      if (frm.doc.status === "جديد") {
        frm.add_custom_button(__("تحت المراجعة"), () => move("تحت المراجعة"));
      }
      frm.add_custom_button(__("أرشفة"), () => move("مؤرشف"));
    } else {
      frm.add_custom_button(__("إعادة فتح"), () => move("تحت المراجعة"));
    }

    if (frm.doc.handled_by) {
      frm.set_intro(
        __("{0} بواسطة {1} في {2}", [
          __(frm.doc.status),
          frappe.user.full_name(frm.doc.handled_by),
          frappe.datetime.str_to_user(frm.doc.handled_at),
        ]),
        "green",
      );
    } else {
      frm.set_intro("");
    }
  },
});
