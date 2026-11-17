"""Move the Company events (#1814) to the General Management Department and drop the Company tab.

The event planning moved from Company to Department (#1949): the General Management Department's
Event Schedule holds the company-wide appointments of the General Management Cockpit.

- Rows keep their Mailcow UID, mailbox and sequence, so the invites in the calendars stay as they
  are and nobody gets mail. Only parent, parenttype and idx change, and the source link in the
  stored description now points to the Department. The calendar copy keeps the Company link
  until the appointment is next edited (rewriting it would resend the invite).
- Without a General Management Department in Cockpit Settings the rows can't move yet. That is
  the normal case on a site getting this release: the setting is new too. The rows and the
  Company fields stay, and saving Cockpit Settings with the department set moves them
  (CockpitSettings.on_update calls move_company_events()).
- Safe to run twice.
"""

import frappe
from frappe.utils import get_url_to_form

from phamos.setup.event_schedule import ensure_event_schedule_fields

ROW_DOCTYPE = "Team Daily Schedule"
COMPANY_FIELDS = ("Company-event_schedule", "Company-events_tab")


def execute():
	ensure_event_schedule_fields()  # the Department table must exist before rows move there
	move_company_events(log_if_blocked=True)


def has_company_events():
	return bool(frappe.db.exists(ROW_DOCTYPE, {"parenttype": "Company", "parentfield": "event_schedule"}))


def move_company_events(log_if_blocked=False):
	"""Move what is left on Company, then drop the Company fields. Returns the number moved."""
	rows = frappe.get_all(
		ROW_DOCTYPE,
		filters={"parenttype": "Company", "parentfield": "event_schedule"},
		fields=["name", "parent", "description"],
		order_by="parent asc, idx asc",
	)
	if rows:
		department = frappe.db.get_single_value("Cockpit Settings", "general_management_department")
		if not department:
			if log_if_blocked:
				frappe.log_error(
					f"{len(rows)} Company events wait for their move: set the General Management Department "
					"in Cockpit Settings and save; that moves them (#1949).",
					"Move Company events to Department (#1949)",
				)
			return 0
		last_idx = (
			frappe.db.sql(
				f"select max(idx) from `tab{ROW_DOCTYPE}` where parenttype = 'Department' and parent = %s",
				department,
			)[0][0]
			or 0
		)
		department_url = get_url_to_form("Department", department)
		for offset, row in enumerate(rows, start=1):
			values = {"parenttype": "Department", "parent": department, "parentfield": "event_schedule", "idx": last_idx + offset}
			description = row.description or ""
			company_url = get_url_to_form("Company", row.parent)
			if company_url in description:
				values["description"] = description.replace(company_url, department_url)
			frappe.db.set_value(ROW_DOCTYPE, row.name, values, update_modified=False)

	for name in COMPANY_FIELDS:
		if frappe.db.exists("Custom Field", name):
			frappe.delete_doc("Custom Field", name, ignore_permissions=True, force=True)
	frappe.clear_cache(doctype="Company")
	return len(rows)
