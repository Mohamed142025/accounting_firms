from frappe.model.document import Document


class MailServer(Document):
    def validate(self):
        self.server_host = (self.server_host or "").strip().lower()
        if not self.port:
            self.port = 993 if self.use_ssl else 143
