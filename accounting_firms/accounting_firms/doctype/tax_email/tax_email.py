# Copyright (c) 2026, Mohamed sayed and contributors
# For license information, please see license.txt

import frappe
from frappe.model.document import Document


class TaxEmail(Document):
	pass


@frappe.whitelist()
def get_password(name):
	frappe.only_for("System Manager")
	return frappe.get_doc("Tax Email", name).get_password("email_password", raise_exception=False)
