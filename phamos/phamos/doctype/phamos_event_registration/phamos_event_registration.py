import frappe
from frappe.model.document import Document


class PhamosEventRegistration(Document):
    def before_insert(self):
        if not self.registered_on:
            self.registered_on = frappe.utils.now()
