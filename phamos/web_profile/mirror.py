"""Mirror facts from internal source records onto their Web Profiles.

Mirrored fields are read-only on the profile. They are refreshed whenever the profile is saved
(``WebProfileDocument.validate``) and pushed whenever a source record is saved (``on_update``
doc events in hooks.py), so form saves, Data Import and API updates all propagate.
"""

import frappe
from frappe import _

# Parties a Person Web Profile can represent. Employees are phamos people; the others are
# represented by one of their Contacts (the actual person).
PERSON_PARTY_TYPES = ("Employee", "Customer", "Supplier", "Sales Partner")
PARTY_NAME_FIELDS = {"Customer": "customer_name", "Supplier": "supplier_name", "Sales Partner": "partner_name"}

# profile doctype -> (link field on the profile, source doctype, {profile field: source field})
MIRRORS = {
	"Department Web Profile": ("department", "Department", {"department_name": "department_name"}),
	"Team Web Profile": ("team", "Team", {"team_name": "team_name", "team_lead": "team_lead"}),
	"Module Web Profile": ("module", "Implementation Module", {"module_name": "module_name"}),
	"Implementation Web Profile": (
		"implementation",
		"Implementation",
		{
			"customer": "customer",
			"implementation_status": "status",
			"team": "team",
			"department": "department",
			"start_date": "start_date",
		},
	),
	"Industry Web Profile": ("industry", "Industry Type", {}),

}
STAKEHOLDER_FIELDS = ("party_name", "website")
PARTY_WEBSITE_FIELDS = {"Customer": "website", "Supplier": "website", "Sales Partner": "partner_website"}
PERSON_FIELDS = ("full_name", "designation", "company_name", "status", "department", "date_of_joining",
	"relieving_date", "email_id")


def refresh_mirrored_fields(profile):
	"""Copy the mirrored facts from the source record(s) onto ``profile`` (no save)."""
	if profile.doctype == "Person Web Profile":
		return _refresh_person(profile)
	if profile.doctype == "Stakeholder Web Profile":
		return _refresh_stakeholder(profile)

	link_field, source_doctype, field_map = MIRRORS[profile.doctype]
	source_name = profile.get(link_field)
	if not source_name or not field_map:
		return

	values = frappe.db.get_value(source_doctype, source_name, list(field_map.values()), as_dict=True) or {}
	for target, source in field_map.items():
		profile.set(target, values.get(source))

	if profile.doctype == "Implementation Web Profile":
		_refresh_implementation_extras(profile)
	if profile.doctype == "Module Web Profile":
		# Official ERPNext icon of the module's workspace (see web_profile/icons.py).
		profile.icon = frappe.db.get_value("Workspace", profile.workspace, "icon") if profile.workspace else None


def _refresh_person(profile):
	"""Employee: facts from the Employee. Anyone else: the person from the Contact, the
	organization from the party. Field names follow the Contact/Employee fields they come from."""
	if profile.party_type and profile.party_type not in PERSON_PARTY_TYPES:
		frappe.throw(_("Party Type must be one of: {0}").format(", ".join(PERSON_PARTY_TYPES)))
	if not profile.party_type or not profile.party:
		return

	contact = (
		frappe.db.get_value("Contact", profile.contact,
			["full_name", "first_name", "last_name", "designation", "email_id"], as_dict=True)
		if profile.contact else None
	) or frappe._dict()
	values = dict.fromkeys(PERSON_FIELDS)

	if profile.party_type == "Employee":
		employee = frappe.db.get_value("Employee", profile.party,
			["employee_name", "designation", "company", "status", "department", "date_of_joining",
				"relieving_date", "company_email", "prefered_email"], as_dict=True) or frappe._dict()
		values.update({
			"full_name": employee.employee_name,
			"designation": employee.designation,
			"company_name": employee.company,
			"status": employee.status,
			"department": employee.department,
			"date_of_joining": employee.date_of_joining,
			"relieving_date": employee.relieving_date,
			"email_id": contact.email_id or employee.company_email or employee.prefered_email,
		})
	else:
		if profile.contact and not frappe.db.exists("Dynamic Link", {"parenttype": "Contact",
				"parent": profile.contact, "link_doctype": profile.party_type, "link_name": profile.party}):
			frappe.throw(_("Contact {0} is not linked to {1} {2}.").format(profile.contact, profile.party_type, profile.party))
		values.update({
			"full_name": contact.full_name or " ".join(filter(None, [contact.first_name, contact.last_name])),
			"designation": contact.designation,
			"company_name": frappe.db.get_value(profile.party_type, profile.party, PARTY_NAME_FIELDS[profile.party_type]),
			"status": "Active",
			"email_id": contact.email_id,
		})
	for field, value in values.items():
		profile.set(field, value)


def _refresh_stakeholder(profile):
	"""Name and website from the party; the industry from the Customer (set by hand for others)."""
	if profile.party_type and profile.party_type not in PARTY_NAME_FIELDS:
		frappe.throw(_("Party Type must be one of: {0}").format(", ".join(PARTY_NAME_FIELDS)))
	if not profile.party_type or not profile.party:
		return
	values = frappe.db.get_value(profile.party_type, profile.party,
		[PARTY_NAME_FIELDS[profile.party_type], PARTY_WEBSITE_FIELDS[profile.party_type]], as_dict=True) or {}
	profile.party_name = values.get(PARTY_NAME_FIELDS[profile.party_type])
	profile.website = values.get(PARTY_WEBSITE_FIELDS[profile.party_type])
	if profile.party_type == "Customer":
		profile.industry = frappe.db.get_value("Customer", profile.party, "industry") or profile.industry


def _refresh_implementation_extras(profile):
	"""Industry via the Customer; modules via the Implementation's module table."""
	profile.industry = (
		frappe.db.get_value("Customer", profile.customer, "industry") if profile.customer else None
	)
	module_names = frappe.get_all(
		"Implementation Item",
		filters={"parent": profile.implementation, "parenttype": "Implementation"},
		pluck="module",
		order_by="idx asc",
	)
	# Module Web Profiles are named after their Implementation Module (autoname field:module).
	existing = set(frappe.get_all("Module Web Profile", filters={"name": ["in", module_names or [""]]}, pluck="name"))
	profile.set("modules", [{"module": m} for m in dict.fromkeys(module_names) if m in existing])


def _targets(doc):
	"""(profile doctype, filters) of every profile that mirrors something from ``doc``."""
	targets = [
		(profile_doctype, {link_field: doc.name})
		for profile_doctype, (link_field, source_doctype, _fields) in MIRRORS.items()
		if source_doctype == doc.doctype
	]
	if doc.doctype in PERSON_PARTY_TYPES:
		targets.append(("Person Web Profile", {"party_type": doc.doctype, "party": doc.name}))
	if doc.doctype in PARTY_NAME_FIELDS:
		targets.append(("Stakeholder Web Profile", {"party_type": doc.doctype, "party": doc.name}))
	if doc.doctype == "Workspace":
		targets.append(("Module Web Profile", {"workspace": doc.name}))
	if doc.doctype == "Contact":
		targets.append(("Person Web Profile", {"contact": doc.name}))
	if doc.doctype == "Customer":
		# The industry shown on an implementation comes from its Customer.
		targets.append(("Implementation Web Profile", {"customer": doc.name}))
	return targets


def push_to_profiles(doc, method=None):
	"""doc_events on_update handler for every source doctype (see hooks.py)."""
	if frappe.flags.in_migrate or frappe.flags.in_install or frappe.flags.in_patch:
		return  # schema may be mid-sync; profiles refresh themselves on their next save
	# Members, leads and names feed the rendered listings even when no mirrored field changed.
	frappe.cache.delete_value("web_profile_items")

	for profile_doctype, filters in _targets(doc):
		for name in frappe.get_all(profile_doctype, filters=filters, pluck="name"):
			profile = frappe.get_doc(profile_doctype, name)
			before = profile.as_dict()
			refresh_mirrored_fields(profile)
			if _changed(before, profile):
				profile.flags.ignore_permissions = True
				profile.save()


def _changed(before, profile):
	if profile.doctype == "Person Web Profile":
		fields = PERSON_FIELDS
	elif profile.doctype == "Stakeholder Web Profile":
		fields = (*STAKEHOLDER_FIELDS, "industry")
	else:
		fields = list(MIRRORS[profile.doctype][2]) + {"Implementation Web Profile": ["industry"],
			"Module Web Profile": ["icon"]}.get(profile.doctype, [])
	if any(before.get(f) != profile.get(f) for f in fields):
		return True
	if profile.doctype == "Implementation Web Profile":
		return [r.get("module") for r in before.get("modules") or []] != [r.module for r in profile.modules]
	return False
