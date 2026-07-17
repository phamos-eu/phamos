# Copyright (c) 2026, phamos.eu and contributors
# For license information, please see license.txt

import frappe
from frappe.model.document import Document


class TeamDailySchedule(Document):
	pass


@frappe.whitelist()
@frappe.validate_and_sanitize_search_inputs
def email_account_with_dav_password_query(doctype, txt, searchfield, start, page_len, filters):
	"""Return Email Accounts whose email_id exists in Mailcow DAV Password.user."""
	return frappe.db.sql(
		"""
		SELECT DISTINCT
			ea.name,
			ea.email_id
		FROM `tabEmail Account` ea
		INNER JOIN `tabMailcow DAV Password` mdp ON mdp.user = ea.email_id
		WHERE (
			ea.name LIKE %(txt)s
			OR ea.email_id LIKE %(txt)s
		)
		ORDER BY ea.email_id ASC
		LIMIT %(start)s, %(page_len)s
		""",
		{
			"txt": f"%{txt or ''}%",
			"start": int(start or 0),
			"page_len": int(page_len or 20),
		},
	)
