# Copyright (c) 2026, phamos.eu and contributors
# For license information, please see license.txt

import frappe
from frappe.model.document import Document
from frappe.utils import date_diff, today


class Escalation(Document):
	def before_save(self):
		self._update_days_of_escalation()
		self._fetch_snapshot_fields()

	def _update_days_of_escalation(self):
		if not self.open_date:
			return
		if self.status == "Resolved" and self.close_date:
			self.days_of_escalation = date_diff(self.close_date, self.open_date)
		else:
			self.days_of_escalation = date_diff(today(), self.open_date)

	def _fetch_snapshot_fields(self):
		if not self.implementation or not self.open_date:
			return
		snapshot = _get_snapshot(self.implementation, self.open_date)
		if snapshot:
			self.maturity_level = snapshot.get("maturity_level")
			self.implementation_status = snapshot.get("forecast")


@frappe.whitelist()
def get_status_before_date(implementation, open_date):
	return _get_snapshot(implementation, open_date)


def _get_snapshot(implementation, open_date):
	"""Return the Status Updates row strictly before open_date (non-Escalated).
	Falls back to the row on or before open_date (today's entry) if none found."""
	result = frappe.db.sql(
		"""
		SELECT maturity_level, forecast
		FROM `tabStatus Information`
		WHERE parent = %s
		AND parentfield = 'status_updates'
		AND `date` < %s
		AND COALESCE(status, '') != 'Escalated'
		ORDER BY `date` DESC
		LIMIT 1
		""",
		(implementation, open_date),
		as_dict=True,
	)
	if result:
		return result[0]

	# Fallback: today's row (no previous entry exists yet)
	fallback = frappe.db.sql(
		"""
		SELECT maturity_level, forecast
		FROM `tabStatus Information`
		WHERE parent = %s
		AND parentfield = 'status_updates'
		AND `date` <= %s
		ORDER BY `date` DESC
		LIMIT 1
		""",
		(implementation, open_date),
		as_dict=True,
	)
	return fallback[0] if fallback else {}
