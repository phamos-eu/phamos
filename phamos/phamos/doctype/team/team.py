# Copyright (c) 2025, phamos.eu and contributors
# For license information, please see license.txt

import frappe
from frappe.model.document import Document
from frappe.utils import nowdate


class Team(Document):
	pass

	def create_team_capacity_ledger_entry(doc, method):
		frappe.get_doc({
			"doctype": "Team Capacity Ledger",
			"team": doc.team_name,
			"total_team_capacity": doc.total_team_capacity,
			"date": nowdate()
		}).insert(ignore_permissions=True)
