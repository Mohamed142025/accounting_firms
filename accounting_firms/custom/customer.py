import frappe
from frappe import _

from erpnext.selling.doctype.customer.customer import Customer


class CustomCustomer(Customer):
	def validate(self):
		super().validate()

		if self.is_new():
			return

		old_value = frappe.db.get_value("Customer", self.name, "custom_custom_number")
		if old_value is None:
			return

		new_value = (self.custom_custom_number or "").strip()
		if str(old_value) != str(new_value):
			frappe.throw(_("custom_custom_number cannot be changed after save."))

	def autoname(self):
		custom_number = (getattr(self, "custom_custom_number", None) or "").strip()
		if custom_number:
			self.name = custom_number
			return

		super().autoname()
