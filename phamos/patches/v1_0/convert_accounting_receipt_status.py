"""Accounting Receipt status became a Select; map the old free-text values onto its options.

Blank status is derived the way the cockpit kanban did (paid, then sent to DATEV, else
Inbox). Text that is not an option any more goes to Needs Decision, so a human looks at it.
Safe to run twice: the second run finds only valid values.
"""

import frappe

DOCTYPE = "Accounting Receipt"


def execute():
	options = _status_options()
	rows = frappe.get_all(DOCTYPE, fields=["name", "status", "is_paid", "sent_to_datev"])
	for row in rows:
		new_status = convert_status(row, options)
		if new_status != (row.status or ""):
			frappe.db.set_value(DOCTYPE, row.name, "status", new_status, update_modified=False)


def convert_status(row, options):
	status = (row.get("status") or "").strip()
	if status in options:
		return status
	if not status:
		if row.get("is_paid"):
			return "Paid"
		if row.get("sent_to_datev"):
			return "Sent to DATEV"
		return "Inbox"
	return "Needs Decision"


def _status_options():
	field = frappe.get_meta(DOCTYPE, cached=False).get_field("status")
	return [option for option in (field.options or "").split("\n") if option]
