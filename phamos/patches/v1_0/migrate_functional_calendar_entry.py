import frappe
from frappe.custom.doctype.custom_field.custom_field import create_custom_fields


CHILD_FIELDS = [
	"name",
	"creation",
	"modified",
	"modified_by",
	"owner",
	"docstatus",
	"idx",
	"parent",
	"parentfield",
	"parenttype",
	"subject",
	"location",
	"repeat_this_event",
	"repeat_on",
	"repeat_till",
	"description",
	"start",
	"end",
	"required_attendees",
	"email_account",
	"optional_attendees",
	"mailcow_uid",
	"mailcow_seq",
	"mailcow_synced",
	"mailcow_last_sync_at",
	"mailcow_mailbox",
	"mailcow_last_error",
]


def execute():
	frappe.reload_doc("Mailcow Integration", "doctype", "functional_calendar_entry")
	frappe.reload_doc("Phamos", "doctype", "team")
	frappe.reload_doc("Phamos", "doctype", "implementation")

	_migrate_team_daily_schedule_rows()
	_ensure_department_employee_fields()
	_delete_deprecated_team_daily_schedule()


def _migrate_team_daily_schedule_rows():
	if not frappe.db.table_exists("Team Daily Schedule"):
		return
	if not frappe.db.table_exists("Functional Calendar Entry"):
		return

	existing = frappe.db.count("Functional Calendar Entry")
	legacy = frappe.db.count("Team Daily Schedule")
	if legacy == 0:
		return

	# Resolve columns that exist on the legacy table
	legacy_columns = {row[0] for row in frappe.db.sql("SHOW COLUMNS FROM `tabTeam Daily Schedule`")}
	available = [c for c in CHILD_FIELDS if c in legacy_columns]
	if "name" not in available:
		return

	if existing == 0:
		cols_sql = ", ".join(f"`{c}`" for c in available)
		frappe.db.sql(
			f"""
			INSERT INTO `tabFunctional Calendar Entry` ({cols_sql})
			SELECT {cols_sql}
			FROM `tabTeam Daily Schedule`
			"""
		)
	else:
		legacy_names = set(frappe.get_all("Team Daily Schedule", pluck="name"))
		target_names = set(frappe.get_all("Functional Calendar Entry", pluck="name"))
		for name in legacy_names - target_names:
			row = frappe.db.get_value("Team Daily Schedule", name, available, as_dict=True)
			if not row:
				continue
			doc = frappe.get_doc({"doctype": "Functional Calendar Entry", **row})
			doc.db_insert()

	frappe.db.commit()


def _ensure_department_employee_fields():
	create_custom_fields(
		{
			"Department": [
				{
					"fieldname": "custom_appointment_schedule_section",
					"fieldtype": "Section Break",
					"label": "Appointments",
					"insert_after": "department_name",
				},
				{
					"fieldname": "custom_appointment_schedule",
					"fieldtype": "Table",
					"label": "Appointment Schedule",
					"options": "Functional Calendar Entry",
					"insert_after": "custom_appointment_schedule_section",
				},
			],
			"Employee": [
				{
					"fieldname": "custom_appointment_schedule_section",
					"fieldtype": "Section Break",
					"label": "Appointments",
					"insert_after": "image",
				},
				{
					"fieldname": "custom_appointment_schedule",
					"fieldtype": "Table",
					"label": "Appointment Schedule",
					"options": "Functional Calendar Entry",
					"insert_after": "custom_appointment_schedule_section",
				},
			],
		},
		ignore_validate=True,
		update=True,
	)


def _delete_deprecated_team_daily_schedule():
	"""Remove the Team-specific child DocType after rows were migrated."""
	if not frappe.db.exists("DocType", "Team Daily Schedule"):
		return

	team_options = frappe.db.get_value(
		"DocField",
		{"parent": "Team", "fieldname": "custom_team_daily_schedule"},
		"options",
	)
	if team_options != "Functional Calendar Entry":
		return

	try:
		frappe.delete_doc("DocType", "Team Daily Schedule", force=1, ignore_missing=True)
		frappe.db.commit()
	except Exception:
		frappe.log_error(frappe.get_traceback(), "Delete Team Daily Schedule DocType")
