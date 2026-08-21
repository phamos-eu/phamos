# Copyright (c) 2026, phamos.eu and contributors
# For license information, please see license.txt

import frappe
from frappe.model.document import Document
from frappe.utils import flt, getdate


class MonthlySalaryInvoice(Document):

    def autoname(self):
        invoice_date = getdate(self.invoice_date)
        year = invoice_date.strftime("%Y")
        month = invoice_date.strftime("%m")

        self.name = f"ACC-SINV-{year}-{int(month):03d}"
    
    def validate(self):
        if not self.supplier_email:
            frappe.throw(frappe._("Supplier Email is required. Please set an email on the Employee."))

        if not self.items:
            frappe.throw(frappe._("Please add at least one Line Item."))

        total = 0
        for idx, row in enumerate(self.items, start=1):
            if flt(row.amount) <= 0:
                frappe.throw(
                    frappe._("Row {0}: Amount must be greater than 0.").format(idx)
                )
            total += flt(row.amount)

        self.total_amount = flt(total, 2)
