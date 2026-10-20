# Copyright (c) 2026, phamos.eu and contributors
# For license information, please see license.txt

"""Checklist item assignment: one ToDo per assigned item, kept in sync both ways (#1625).

The ToDo references the Checklist and is created directly, not through `assign_to.add`,
because that allows only one ToDo per (document, user) and an assignee may own several
items of one checklist. The item keeps its ToDo in the hidden `todo` field.

Checklist -> ToDo (`sync_item_todos`, on Checklist update): open item -> ToDo Open, ticked
item -> ToDo Closed, new assignee -> old ToDo Cancelled and a new one created, assignee
cleared or item removed -> ToDo Cancelled. The due date becomes the ToDo date.

ToDo -> Checklist (`sync_item_from_todo`, on ToDo update): Closed ticks the item, Open
unticks it, Cancelled clears the assignee, a new date becomes the item due date.

Both directions only write when something differs, and `frappe.flags.in_checklist_todo_sync`
stops the save of one side from echoing back.

`todo` and the Checklist's `assignment_shared_with` belong to this module: `validate_assignment`
puts back whatever a client sends for them (read-only is not enforced on save), and a ToDo is
only ever touched when it references this very checklist. Otherwise anyone who can edit a
checklist could close or cancel other people's ToDos by naming them in `todo`.

Assignees who cannot open the checklist yet get it shared read + write, so they can tick their
items. Only shares made that way are recorded in `assignment_shared_with`, and only those are
removed again once the user has no item left on the checklist.
"""

import html
from contextlib import contextmanager

import frappe
from frappe import _
from frappe.utils import cint, getdate, strip_html

SYNC_FLAG = "in_checklist_todo_sync"

# A row whose values here are unchanged since the last save keeps its ToDo as it is.
SYNCED_ROW_FIELDS = ("assigned_to", "done", "due_date", "description", "todo")
# These go into every ToDo description, so a change re-syncs all rows.
SYNCED_CHECKLIST_FIELDS = ("title", "document", "reference_record")


def in_sync():
	return bool(frappe.flags.get(SYNC_FLAG))


@contextmanager
def _syncing():
	previous = frappe.flags.get(SYNC_FLAG)
	frappe.flags[SYNC_FLAG] = True
	try:
		yield
	finally:
		frappe.flags[SYNC_FLAG] = previous


# ----- validate -----


def validate_assignment(checklist):
	"""Checklist validate: keep the server-owned fields and check newly assigned users."""
	before = None if checklist.is_new() else checklist.get_doc_before_save()
	before_rows = {row.name: row for row in (before.checklist_items if before else [])}

	if not in_sync():
		for row in checklist.checklist_items:
			previous = before_rows.get(row.name)
			row.todo = previous.todo if previous else None
		checklist.assignment_shared_with = before.get("assignment_shared_with") if before else None

	new_assignees = {
		row.assigned_to
		for row in checklist.checklist_items
		if row.assigned_to
		and (row.name not in before_rows or before_rows[row.name].assigned_to != row.assigned_to)
	}
	if not new_assignees:
		return

	validate_assignees(new_assignees)
	if in_sync() or checklist.flags.ignore_permissions:
		return
	_validate_can_assign(checklist, new_assignees)


def validate_assignees(users):
	"""Only enabled employees with desk access, the same users the assignee picker offers
	(`checklist_owner_query`); portal users (customers, suppliers) never see internal checklists."""
	desk_users = frappe.get_all(
		"User",
		filters={"name": ("in", list(users)), "enabled": 1, "user_type": "System User"},
		pluck="name",
	)
	valid = set(
		frappe.get_all(
			"Has Role",
			filters={"parenttype": "User", "parent": ("in", desk_users or [""]), "role": "Employee"},
			pluck="parent",
		)
	)
	invalid = sorted(users - valid)
	if invalid:
		frappe.throw(
			_("Checklist items can only be assigned to enabled users with the Employee role: {0}").format(
				", ".join(invalid)
			)
		)


def _validate_can_assign(checklist, new_assignees):
	user = frappe.session.user
	# Someone who can only open the checklist through a share (an assignee) may tick and edit
	# items, but must not hand access on to more people by assigning them.
	if user != checklist.checklist_owner and not frappe.has_permission(
		"Checklist", "write", doc=checklist, user=user, ignore_share_permissions=True
	):
		frappe.throw(_("Only the checklist owner or users with edit rights on checklists can assign items"))

	if not frappe.get_system_settings("disable_document_sharing"):
		return
	blocked = sorted(u for u in new_assignees if not _can_write(checklist, u))
	if blocked:
		frappe.throw(
			_("Document sharing is disabled, so {0} could not open this checklist. Assign someone with access to checklists.").format(
				", ".join(blocked)
			)
		)


def _can_write(checklist, user):
	return frappe.has_permission("Checklist", "write", doc=checklist, user=user)


# ----- Checklist -> ToDo -----


def sync_item_todos(checklist):
	"""Checklist on_update: create, update or cancel the ToDos of changed items."""
	before = checklist.get_doc_before_save()
	before_rows = {row.name: row for row in (before.checklist_items if before else [])}
	current_names = {row.name for row in checklist.checklist_items}
	resync_all = before is None or any(
		checklist.get(field) != before.get(field) for field in SYNCED_CHECKLIST_FIELDS
	)

	with _syncing():
		for row in checklist.checklist_items:
			previous = before_rows.get(row.name)
			if resync_all or previous is None or _row_changed(row, previous):
				_sync_row(checklist, row)
		for name, row in before_rows.items():
			if name not in current_names:
				_cancel_own_todo(checklist, row.todo)

	_sync_shares(checklist)


def cancel_item_todos(checklist):
	"""Checklist on_trash: cancel open item ToDos at once, so the assignees' cockpits update.

	Frappe deletes the ToDos of a deleted document later, in a background job without hooks.
	"""
	with _syncing():
		for row in checklist.checklist_items:
			_cancel_own_todo(checklist, row.todo)


def _row_changed(row, previous):
	def value(doc, field):
		raw = doc.get(field)
		if field == "due_date":
			return getdate(raw) if raw else None
		if field == "done":
			return cint(raw)
		return raw or None

	return any(value(row, field) != value(previous, field) for field in SYNCED_ROW_FIELDS)


def _own_todo(checklist, todo_name):
	"""The item's ToDo, but only if it really belongs to this checklist."""
	if not todo_name:
		return None
	return frappe.db.get_value(
		"ToDo",
		{"name": todo_name, "reference_type": "Checklist", "reference_name": checklist.name},
		["name", "allocated_to", "status"],
		as_dict=True,
	)


def _cancel_own_todo(checklist, todo_name):
	todo = _own_todo(checklist, todo_name)
	if todo and todo.status != "Cancelled":
		_set_todo_status(todo.name, "Cancelled")


def _sync_row(checklist, row):
	todo = _own_todo(checklist, row.todo)

	if todo and todo.allocated_to != row.assigned_to:
		_set_todo_status(todo.name, "Cancelled")
		todo = None

	if not todo:
		# A ticked item needs no ToDo; one is created when it is unticked.
		todo_name = _create_todo(checklist, row) if row.assigned_to and not row.done else None
		if row.todo != todo_name:
			row.db_set("todo", todo_name, update_modified=False)
		return

	todo_doc = frappe.get_doc("ToDo", todo.name)
	values = {
		"status": "Closed" if row.done else "Open",
		"date": getdate(row.due_date) if row.due_date else None,
		"description": _todo_description(checklist, row),
	}
	changed = False
	for field, value in values.items():
		current = todo_doc.get(field)
		if field == "date" and current:
			current = getdate(current)
		if current != value:
			todo_doc.set(field, value)
			changed = True
	if changed:
		# The editor may not own the assignee's ToDo; the checklist write was checked already.
		todo_doc.save(ignore_permissions=True)


def _create_todo(checklist, row):
	todo = frappe.get_doc(
		{
			"doctype": "ToDo",
			"allocated_to": row.assigned_to,
			"assigned_by": frappe.session.user,
			"reference_type": "Checklist",
			"reference_name": checklist.name,
			"description": _todo_description(checklist, row),
			"date": row.due_date or None,
			"status": "Open",
		}
	)
	todo.insert(ignore_permissions=True)
	_notify_assignee(todo, checklist)
	return todo.name


def _notify_assignee(todo, checklist):
	"""Bell notification (and mail, per the user's settings) like a regular Frappe assignment."""
	if todo.allocated_to == frappe.session.user:
		return
	from frappe.desk.form.assign_to import notify_assignment

	notify_assignment(
		todo.assigned_by, todo.allocated_to, "Checklist", checklist.name, action="ASSIGN", description=todo.description
	)


def _set_todo_status(todo_name, status):
	todo = frappe.get_doc("ToDo", todo_name)
	if todo.status != status:
		todo.status = status
		todo.save(ignore_permissions=True)


def _plain(value):
	"""Text as typed: Frappe stores Data values that contain HTML escaped, so undo that first."""
	return html.unescape(strip_html(value or "")).strip()


def _todo_description(checklist, row):
	text = frappe.utils.escape_html(_plain(row.description)) or _("Checklist item")
	context = frappe.utils.escape_html(_plain(checklist.get("title")) or checklist.name)
	if checklist.document and checklist.reference_record:
		context += f" · {_(checklist.document)} {frappe.utils.escape_html(checklist.reference_record)}"
	return f"<p>{text}</p><p>{_('Checklist')}: {context}</p>"


def _sync_shares(checklist):
	shared = set(filter(None, (checklist.get("assignment_shared_with") or "").split("\n")))
	assignees = {row.assigned_to for row in checklist.checklist_items if row.assigned_to}
	flags = {"ignore_share_permission": True}
	sharing_disabled = frappe.get_system_settings("disable_document_sharing")
	before = set(shared)

	for user in sorted(assignees - shared):
		# Users with access already (roles or a share made by hand) need nothing from us.
		if sharing_disabled or _can_write(checklist, user):
			continue
		frappe.share.add_docshare("Checklist", checklist.name, user, read=1, write=1, flags=flags)
		shared.add(user)

	for user in sorted(shared - assignees):
		share_name = frappe.db.get_value(
			"DocShare", {"share_doctype": "Checklist", "share_name": checklist.name, "user": user}
		)
		if share_name:
			# The editor may lack DocShare delete rights; this share was made by the assignment.
			frappe.delete_doc("DocShare", share_name, ignore_permissions=True, flags=flags)
		shared.discard(user)

	if shared != before:
		checklist.db_set("assignment_shared_with", "\n".join(sorted(shared)) or None, update_modified=False)


# ----- ToDo -> Checklist -----


def sync_item_from_todo(doc, method=None):
	"""ToDo on_update: carry status and date of an item's ToDo back to the checklist item."""
	if doc.reference_type != "Checklist" or in_sync():
		return
	row_name = frappe.db.get_value("Checklist Items", {"todo": doc.name, "parent": doc.reference_name}, "name")
	if not row_name:
		return

	checklist = frappe.get_doc("Checklist", doc.reference_name)
	row = next((r for r in checklist.checklist_items if r.name == row_name), None)
	if not row:
		return

	changed = False
	if doc.status == "Cancelled":
		row.assigned_to = None
		row.todo = None
		changed = True
	else:
		done = 1 if doc.status == "Closed" else 0
		if cint(row.done) != done:
			row.done = done
			changed = True
		due_date = getdate(doc.date) if doc.date else None
		if (getdate(row.due_date) if row.due_date else None) != due_date:
			row.due_date = due_date
			changed = True

	if not changed:
		return
	with _syncing():
		# The assignee closing their own ToDo may only hold a share; the item is theirs to tick.
		checklist.save(ignore_permissions=True)


def clear_item_todo_link(doc, method=None):
	"""ToDo on_trash: drop the item's link first, so deleting the ToDo does not fail on it."""
	if doc.reference_type == "Checklist":
		frappe.db.set_value("Checklist Items", {"todo": doc.name}, "todo", None, update_modified=False)
