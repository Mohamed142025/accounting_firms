from frappe import _


def get_dashboard_data(data):
    """Show customer branches and tax notifications in the Connections tab of the Customer form."""
    data.setdefault("transactions", [])
    data["transactions"].insert(0, {"label": _("الإشعارات الضريبية"), "items": ["Tax Notification"]})
    data["transactions"].insert(0, {"label": _("الفروع"), "items": ["Customer Branch"]})
    return data
