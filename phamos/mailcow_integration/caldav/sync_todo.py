'''
TASK Handlers 
(ERPNext --> VTODO)

'''

from __future__ import annotations
import frappe
from frappe.utils import get_datetime
from .client import put_ics, delete_ics
from .ics import vtodo

# Map ERPNext ToDo -> VTODO fields
def _status(todo_status: str | None) -> str | None:
	# ERPNext ToDo status: Open/Closed/Cancelled (customs vary)
	if not todo_status: return None
	s = todo_status.lower()
	if s in ("closed", "completed", "done"): return "COMPLETED"
	if s in ("cancelled", "canceled"): return "CANCELLED"
	return "NEEDS-ACTION"

def on_upsert(doc, method=None):
	try:
		seq = int(doc.get("mailcow_seq") or 0) + 1
		doc.db_set("mailcow_seq", seq, notify=False)

		due = get_datetime(doc.date) if getattr(doc, "date", None) else None
		ics = vtodo(
			uid=doc.name,
			seq=seq,
			title=doc.description or doc.name,
			due=due,
			status=_status(getattr(doc, "status", None)),
			description=doc.description or "",
			priority=getattr(doc, "priority", None),
		)
		put_ics(doc.name, ics, acting_user_id=doc.owner)
		doc.db_set("mailcow_uid", doc.name, notify=False)
		doc.db_set("mailcow_synced", 1, notify=False)
	except Exception:
		frappe.log_error(frappe.get_traceback(), "ToDo CalDAV Sync Error")

def on_delete(doc, method=None):
	try:
		delete_ics(doc.name, acting_user_id=doc.owner)
	except Exception:
		frappe.log_error(frappe.get_traceback(), "ToDo CalDAV Delete Error")
