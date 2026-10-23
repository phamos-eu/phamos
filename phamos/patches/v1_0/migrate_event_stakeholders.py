"""Organizers and sponsors of events become Stakeholder Web Profiles.

- "phamos organizes this event" is ticked unless an organizer name other than phamos was entered; such
  events keep showing the old name until an editor picks the organizer's profile.
- Sponsor rows are linked to the Stakeholder Web Profile whose name equals the sponsor name.
"""

import frappe


def execute():
	for event in frappe.get_all("Marketing Content", fields=["name", "organizer_name", "organizer"]):
		name = (event.organizer_name or "").strip()
		external = bool(name) and "phamos" not in name.lower()
		frappe.db.set_value("Marketing Content", event.name, "organizer_is_phamos", 0 if external or event.organizer else 1,
			update_modified=False)
	profiles = {(r.party_name or "").strip().lower(): r.name for r in
		frappe.get_all("Stakeholder Web Profile", fields=["name", "party_name"])}
	for row in frappe.get_all("Marketing Event Sponsor", filters={"stakeholder": ["is", "not set"]},
			fields=["name", "sponsor_name"]):
		match = profiles.get((row.sponsor_name or "").strip().lower())
		if match:
			frappe.db.set_value("Marketing Event Sponsor", row.name, "stakeholder", match, update_modified=False)
	frappe.cache.delete_value("web_profile_items")
