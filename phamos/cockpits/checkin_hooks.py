# Copyright (c) 2026, phamos.eu and contributors
# For license information, please see license.txt

"""Live updates for check-ins in the Personal Cockpit (phamos/phamos#1571).

Publishes to the Employee's own user whenever one of their Employee Checkins changes, also
when it was made in the HRMS app or in Desk. The payload carries no content.
"""

import frappe

REALTIME_EVENT = "cockpit_checkin_changed"


def _publish(doc):
	user = frappe.db.get_value("Employee", doc.employee, "user_id") if doc.employee else None
	if user:
		frappe.publish_realtime(REALTIME_EVENT, {"name": doc.name}, user=user, after_commit=True)


def on_update(doc, method=None):
	_publish(doc)


def on_trash(doc, method=None):
	_publish(doc)
