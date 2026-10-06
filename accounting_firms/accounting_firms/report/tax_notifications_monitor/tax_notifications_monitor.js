frappe.query_reports["Tax Notifications Monitor"] = {
  filters: [
    { fieldname: "customer", label: __("العميل"), fieldtype: "Link", options: "Customer" },
    { fieldname: "assigned_to", label: __("المسؤول"), fieldtype: "Link", options: "User" },
    { fieldname: "category", label: __("التصنيف"), fieldtype: "Link", options: "Tax Notification Category" },
    {
      fieldname: "status",
      label: __("الحالة"),
      fieldtype: "Select",
      options: ["المفتوحة", "الكل", "جديد", "تحت المراجعة", "تم التعامل", "مؤرشف", "متأخر"],
      default: "المفتوحة",
    },
    { fieldname: "from_date", label: __("من تاريخ"), fieldtype: "Date", default: frappe.datetime.add_days(frappe.datetime.get_today(), -30) },
    { fieldname: "to_date", label: __("إلى تاريخ"), fieldtype: "Date", default: frappe.datetime.get_today() },
  ],
  formatter(value, row, column, data, default_formatter) {
    value = default_formatter(value, row, column, data);
    if (!data) return value;
    if (column.fieldname === "days_overdue" && data.days_overdue > 0) {
      return `<span style="color: var(--red-500); font-weight: 600">${value}</span>`;
    }
    if (column.fieldname === "priority" && data.priority === "عالية") {
      return `<span style="color: var(--red-500)">${value}</span>`;
    }
    return value;
  },
};
