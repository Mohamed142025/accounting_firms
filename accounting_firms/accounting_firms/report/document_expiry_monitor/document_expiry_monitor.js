frappe.query_reports["Document Expiry Monitor"] = {
  onload(report) {
    const branch = report.get_filter("branch");
    if (!branch) return;
    branch.get_query = () => {
      const customer = report.get_filter_value("customer");
      return customer ? { filters: { customer } } : {};
    };
  },
};
