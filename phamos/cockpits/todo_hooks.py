# Copyright (c) 2026, phamos.eu and contributors
# For license information, please see license.txt

"""ToDo lifecycle stamps for the Personal Cockpit (phamos/phamos#1553).

Frappe's `assign_to` closes and cancels ToDos through `doc.save()`, so these hooks see
closes from Desk, ERPNext and the cockpit alike. Only the raw deletion of assignment
ToDos when their record is deleted (`delete_dynamic_links`) bypasses hooks.
"""

import frappe
from frappe.utils import getdate, now_datetime

DONE_STATUSES = ("Closed", "Cancelled")
REALTIME_EVENT = "cockpit_todos_changed"


def _has_cockpit_fields(doc):
	return doc.meta.has_field("cockpit_closed_on")


def before_insert(doc, method=None):
	if not _has_cockpit_fields(doc):
		return
	if doc.date and not doc.cockpit_first_due_date:
		doc.cockpit_first_due_date = doc.date
	if not doc.cockpit_important and doc.priority == "High":
		doc.cockpit_important = 1
	if doc.status in DONE_STATUSES and not doc.cockpit_closed_on:
		_stamp_closed(doc)


def validate(doc, method=None):
	if not _has_cockpit_fields(doc) or doc.is_new():
		return
	before = doc.get_doc_before_save()
	if not before:
		return

	if before.status == "Open" and doc.status in DONE_STATUSES:
		_stamp_closed(doc)
	elif doc.status == "Open" and before.status in DONE_STATUSES:
		doc.cockpit_closed_on = None
		doc.cockpit_closed_by = None

	if doc.date and not doc.cockpit_first_due_date:
		doc.cockpit_first_due_date = doc.date
	if (
		doc.status == "Open"
		and doc.date
		and before.date
		and getdate(doc.date) > getdate(before.date)
	):
		doc.cockpit_reschedule_count = (doc.cockpit_reschedule_count or 0) + 1


def on_update(doc, method=None):
	"""Tell the assignee's open cockpits that their ToDos changed (no content in the payload)."""
	users = {doc.allocated_to}
	before = doc.get_doc_before_save()
	if before and before.allocated_to:
		users.add(before.allocated_to)
	for user in filter(None, users):
		frappe.publish_realtime(REALTIME_EVENT, {"name": doc.name}, user=user, after_commit=True)


def on_trash(doc, method=None):
	"""Remove the ToDo's checklists first, so deleting it does not fail on the link."""
	for name in frappe.get_all(
		"Checklist", filters={"document": "ToDo", "reference_record": doc.name}, pluck="name"
	):
		frappe.delete_doc("Checklist", name, ignore_permissions=True, force=True)
	if doc.allocated_to:
		frappe.publish_realtime(REALTIME_EVENT, {"name": doc.name}, user=doc.allocated_to, after_commit=True)


def _stamp_closed(doc):
	doc.cockpit_closed_on = now_datetime()
	doc.cockpit_closed_by = frappe.session.user
