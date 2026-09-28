import frappe


def execute():
    sidebar = frappe.get_doc("Workspace Sidebar", "Selling")
    if any(item.link_type == "Report" and item.link_to == "Document Expiry Monitor" for item in sidebar.items):
        return

    sidebar.append(
        "items",
        {
            "label": "Document Expiry Monitor",
            "type": "Link",
            "link_type": "Report",
            "link_to": "Document Expiry Monitor",
            "icon": "calendar",
            "child": 0,
            "collapsible": 1,
            "indent": 0,
            "keep_closed": 0,
            "show_arrow": 0,
        },
    )

    previous_import_flag = frappe.flags.in_import
    frappe.flags.in_import = True
    try:
        sidebar.save(ignore_permissions=True)
    finally:
        frappe.flags.in_import = previous_import_flag
