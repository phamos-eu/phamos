# Copyright (c) 2023, phamos.eu and contributors
# For license information, please see license.txt

import frappe
from frappe.model.document import Document
from frappe.utils import today
from erpnext import get_default_company


class AccountingReceipt(Document):
	@frappe.whitelist()
	def make_purchase_invoice(self):
		"""
			Create a Purchase Invoice from Accounting Receipt
		"""
		pi = frappe.new_doc("Purchase Invoice")
		pi.posting_date = today()
		company = get_default_company()
		pi.company = company
		pi.supplier = self.supplier
		pi.currency = self.currency
		pi.exchange_rate = self.conversion_rate
		pi.expense_account = self.payment_account
		pi.append(
			"items",
			{
				"item_code": self.item,
				"qty": 1,
				"rate": self.total_billing_amount,
				"project": self.project,
				"expense_account": self.payment_account
			},
		)
		pi.set_missing_values()
		pi.insert()
		self.db_set('purchase_invoice', pi.name)
		return pi