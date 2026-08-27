# Copyright (c) 2026, phamos.eu and contributors
# For license information, please see license.txt

import frappe
from frappe.model.document import Document
from frappe.share import add_docshare


class IncidentCorrectiveAction(Document):
	pass


@frappe.whitelist()
def share_with_internal_team(name):
	"""Share this document (read/write) with every Team member who is an internal user."""
	doc = frappe.get_doc("Incident Corrective Action", name)

	team_users = {row.user for row in doc.team if row.user}
	if not team_users:
		return []

	internal_users = frappe.get_all(
		"Employee",
		filters={"user_id": ["in", list(team_users)]},
		pluck="user_id",
	)

	for user in internal_users:
		add_docshare(doc.doctype, doc.name, user, read=1, write=1, notify=0)

	return internal_users
