# Copyright (c) 2026, phamos.eu and contributors
# For license information, please see license.txt

"""Timesheet timer APIs for department cockpits.

Facade over the existing desk-page implementation in
`phamos.phamos.page.dev_action_panel` so SPA clients do not call that page
module directly. Moving the timer implementation into this package (and
retiring `public/js/dev_action_panel`) is intentional follow-up work.
"""

import frappe

from phamos.phamos.page.dev_action_panel import dev_action_panel as _timer


@frappe.whitelist()
def get_active_project_session():
	return _timer.get_active_project_session()


@frappe.whitelist(methods=["POST"])
def start_project_timer(project_name, expected_time, goal, manual_start_time=None):
	return _timer.start_project_timer(project_name, expected_time, goal, manual_start_time=manual_start_time)


@frappe.whitelist(methods=["POST"])
def pause_timer(name):
	return _timer.pause_timer(name)


@frappe.whitelist(methods=["POST"])
def resume_timer(name):
	return _timer.resume_timer(name)


@frappe.whitelist(methods=["POST"])
def stop_timer(name, result, percent_billable=100, activity_type=None, manual_end_time=None):
	return _timer.stop_timer(
		name,
		result,
		percent_billable=percent_billable,
		activity_type=activity_type,
		manual_end_time=manual_end_time,
	)


@frappe.whitelist(methods=["POST"])
def create_break_timesheet(
	from_time,
	to_time=None,
	project=None,
	goal=None,
	result=None,
	percent_billable=100,
	activity_type=None,
):
	return _timer.create_break_timesheet(
		from_time,
		to_time=to_time,
		project=project,
		goal=goal,
		result=result,
		percent_billable=percent_billable,
		activity_type=activity_type,
	)
