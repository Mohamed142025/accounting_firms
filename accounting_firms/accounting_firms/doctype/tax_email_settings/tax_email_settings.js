frappe.ui.form.on("Tax Email Settings", {
  refresh(frm) {
    frm.add_custom_button(__("حالة مزامنة الإيميلات"), () => frappe.set_route("List", "Tax Mailbox Sync"));
    frm.add_custom_button(__("قواعد التصنيف"), () => frappe.set_route("List", "Tax Notification Rule"));
  },
});
