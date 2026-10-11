frappe.query_reports["Daily Work Hours"] = {
  filters: [
    { fieldname: "from_date", label: __("من تاريخ"), fieldtype: "Date", default: frappe.datetime.add_days(frappe.datetime.get_today(), -7), reqd: 1 },
    { fieldname: "to_date", label: __("إلى تاريخ"), fieldtype: "Date", default: frappe.datetime.get_today(), reqd: 1 },
    { fieldname: "employee", label: __("الموظف"), fieldtype: "Link", options: "Employee" },
    { fieldname: "customer", label: __("العميل"), fieldtype: "Link", options: "Customer" },
    { fieldname: "group_by", label: __("تجميع حسب"), fieldtype: "Select", options: ["الموظف", "العميل", "نوع العمل"], default: "الموظف" },
  ],
};
