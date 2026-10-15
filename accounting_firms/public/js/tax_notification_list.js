frappe.listview_settings["Tax Notification"] = {
  add_fields: ["status", "priority", "due_date"],
  get_indicator(doc) {
    const overdue =
      doc.due_date && ["جديد", "تحت المراجعة"].includes(doc.status) && doc.due_date < frappe.datetime.get_today();
    if (overdue) return [__("متأخر"), "red", "due_date,<,Today|status,in,جديد,تحت المراجعة"];
    const colors = { "جديد": "blue", "تحت المراجعة": "orange", "تم التعامل": "green", "مؤرشف": "gray" };
    return [__(doc.status), colors[doc.status] || "gray", `status,=,${doc.status}`];
  },
  onload(listview) {
    ["تم التعامل", "تحت المراجعة", "مؤرشف"].forEach((status) => {
      listview.page.add_actions_menu_item(__("تغيير الحالة إلى: {0}", [status]), () => {
        const names = listview.get_checked_items(true);
        if (!names.length) return;
        frappe
          .call({
            method: "accounting_firms.accounting_firms.doctype.tax_notification.tax_notification.set_status",
            args: { names, status },
            freeze: true,
          })
          .then(({ message }) => {
            frappe.show_alert({ message: __("تم تحديث {0} إشعار", [message.changed]), indicator: "green" });
            listview.refresh();
          });
      });
    });
    listview.page.add_inner_button(__("إعادة تطبيق القواعد"), () => {
      const names = listview.get_checked_items(true);
      frappe.confirm(
        names.length
          ? __("إعادة تصنيف {0} إشعار محدد؟", [names.length])
          : __("إعادة تصنيف كل الإشعارات المفتوحة حسب القواعد الحالية؟"),
        () => {
          frappe
            .call({
              method: "accounting_firms.tax_email.rules.reclassify",
              args: { names: names.length ? names : null },
              freeze: true,
            })
            .then(({ message }) => {
              frappe.show_alert({ message: __("تم تحديث {0} إشعار", [message.changed]), indicator: "green" });
              listview.refresh();
            });
        },
      );
    });
  },
};
