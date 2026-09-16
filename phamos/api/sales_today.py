# Copyright (c) 2026, phamos.eu and contributors
# For license information, please see license.txt

"""Sales-specific sections for the cockpit's Today dashboard."""

import frappe
from frappe import _
from frappe.utils import format_date, format_datetime, getdate, today

from phamos.api.sales_demos import DEMO_LIST_FIELDS
from phamos.api.sales_leads import LEAD_LIST_FIELDS, _check_lead_access

TODAY_LIMIT = 50


def _follow_ups_section(today_date):
	"""Leads due for follow-up today, with anything overdue ahead of them."""
	rows = frappe.get_all(
		"Lead",
		filters={
			"disabled": 0,
			"custom_next_followup": ("<=", today_date),
			"status": ("not in", ["Converted", "Do Not Contact", "Lost Quotation"]),
		},
		fields=LEAD_LIST_FIELDS,
		order_by="custom_next_followup asc",
		limit_page_length=TODAY_LIMIT,
	)

	items = []
	for row in rows:
		overdue = getdate(row.custom_next_followup) < today_date
		items.append(
			{
				"title": row.lead_name or row.name,
				"subtitle": row.company_name or "",
				"meta": _("Overdue") if overdue else _("Today"),
				"tone": "red" if overdue else "amber",
				"route": {"name": "LeadDetail", "params": {"name": row.name}},
			}
		)

	return {
		"key": "follow_ups",
		"title": _("Follow-ups due"),
		"empty": _("No follow-ups due today"),
		"items": items,
	}


def _next_steps_section(today_date):
	"""Next steps that have come due, so they're actionable without opening each lead."""
	steps = frappe.get_all(
		"Lead Next Step",
		filters={"parenttype": "Lead", "date": ("<=", today_date)},
		fields=["parent", "next_step", "date"],
		order_by="date asc",
		limit_page_length=TODAY_LIMIT,
	)

	leads = {
		row.name: row
		for row in frappe.get_all(
			"Lead",
			filters={
				"name": ("in", list({s.parent for s in steps})),
				"disabled": 0,
				"status": ("not in", ["Converted", "Do Not Contact", "Lost Quotation"]),
			},
			fields=["name", "lead_name", "company_name"],
		)
	} if steps else {}

	items = []
	for step in steps:
		lead = leads.get(step.parent)
		# A step on a closed or disabled lead isn't work for today.
		if not lead or not (step.next_step or "").strip():
			continue
		overdue = getdate(step.date) < today_date
		items.append(
			{
				"title": step.next_step,
				"subtitle": lead.lead_name or lead.company_name or lead.name,
				"meta": _("Overdue") if overdue else _("Today"),
				"tone": "red" if overdue else "amber",
				"route": {"name": "LeadDetail", "params": {"name": lead.name}},
			}
		)

	return {
		"key": "next_steps",
		"title": _("Next steps due"),
		"empty": _("No next steps due today"),
		"items": items,
	}


def _demos_section(today_date):
	"""Demos happening today, plus any still waiting on a date."""
	scheduled = frappe.get_all(
		"Demo",
		filters={
			"scheduled_on": ("between", [f"{today_date} 00:00:00", f"{today_date} 23:59:59"]),
			"status": ("!=", "Cancelled"),
		},
		fields=DEMO_LIST_FIELDS,
		order_by="scheduled_on asc",
		limit_page_length=TODAY_LIMIT,
	)

	items = [
		{
			"title": row.subject,
			"subtitle": row.lead_name or row.lead or "",
			"meta": format_datetime(row.scheduled_on, "HH:mm"),
			"tone": "blue",
			"url": f"/app/demo/{row.name}",
		}
		for row in scheduled
	]

	return {
		"key": "demos",
		"title": _("Demos today"),
		"empty": _("No demos scheduled today"),
		"items": items,
	}


def _awaiting_date_section():
	"""Demos whose proposed dates are out with the customer."""
	rows = frappe.get_all(
		"Demo",
		filters={"scheduled_on": ("is", "not set"), "status": "Planned"},
		fields=DEMO_LIST_FIELDS,
		order_by="modified desc",
		limit_page_length=TODAY_LIMIT,
	)

	return {
		"key": "demos_awaiting",
		"title": _("Demos awaiting a date"),
		"empty": _("Nothing waiting on a customer"),
		"items": [
			{
				"title": row.subject,
				"subtitle": row.lead_name or row.lead or "",
				"meta": format_date(row.modified),
				"tone": "gray",
				"url": f"/app/demo/{row.name}",
			}
			for row in rows
		],
	}


def sales_today_sections():
	"""Lead/Demo sections for the Today dashboard."""
	_check_lead_access()
	today_date = getdate(today())

	sections = [_follow_ups_section(today_date), _next_steps_section(today_date)]
	if frappe.has_permission("Demo", "read"):
		sections.append(_demos_section(today_date))
		sections.append(_awaiting_date_section())
	return sections
