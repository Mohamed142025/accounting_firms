frappe.listview_settings["Employee Daily Summary"] = {
  add_fields: ["needs_follow_up", "total_hours"],
  get_indicator(doc) {
    if (doc.needs_follow_up) return [__("يحتاج متابعة"), "orange", "needs_follow_up,=,1"];
    return [__("{0} ساعة", [doc.total_hours || 0]), "green", "needs_follow_up,=,0"];
  },
};
