# Copyright (c) 2026, phamos.eu and contributors
# For license information, please see license.txt

"""Live updates for the Personal Cockpit timer (phamos/phamos#1572).

Publishes to the record employee's user whenever a Timesheet Record changes or is deleted, so
the top bar follows timers started, paused or stopped in another tab or in the Action Panels.
"""

import frappe

REALTIME_EVENT = "cockpit_timer_changed"


def _publish(doc):
	user = frappe.db.get_value("Employee", doc.employee, "user_id") if doc.get("employee") else None
	if user:
		frappe.publish_realtime(REALTIME_EVENT, {"name": doc.name}, user=user, after_commit=True)


def on_change(doc, method=None):
	_publish(doc)


def on_trash(doc, method=None):
	_publish(doc)
