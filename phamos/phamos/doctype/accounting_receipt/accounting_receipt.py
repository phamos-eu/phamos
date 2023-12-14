# Copyright (c) 2023, phamos.eu and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import today
from erpnext import get_default_company
from frappe.desk.form.load import get_attachments, get_communications
from frappe.desk.form.utils import add_comment


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


@frappe.whitelist()
def make_accounting_receipt(issue):
	"""
		Create an Accouting Receipt from an Issue
	"""
	issue_doc = frappe.get_doc("Issue",issue)
	ar = frappe.new_doc("Accounting Receipt")
	ar.posting_date = today()
	ar.customer = issue_doc.customer
	ar.project = issue_doc.project
	ar.title = issue_doc.subject
	ar.conversion_rate = 1
	ar.insert()
	issue_doc.db_set("accounting_receipt", ar.name)

	""" Get the email data and attachments """
	communication_data = get_communications("Issue",issue)
	for data in communication_data:
		content = data.content
		attachments = frappe.get_all(
		"File",
		fields=["name"],
		filters={"attached_to_name": "Communication", "attached_to_doctype": data.name},
		)
		""" Transfer the attachments """
		if attachments := [d.name for d in get_attachments("Communication",data.name)]:
			for attachment in attachments:
				file_doc = frappe.get_doc("File",attachment)
				file_doc.db_set("attached_to_doctype", "Accounting Receipt")
				file_doc.db_set("attached_to_name", ar.name)
		"""" Add email as Comment """		
		ar.add_comment("Comment", content)
	return ar.name