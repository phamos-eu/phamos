"""Turn the renamed Employee Profile records into Person Web Profiles of party type Employee.

Old columns stay in the table (Frappe never drops columns): employee -> party, profile_image ->
image, bio -> English text row (+ legacy_bio), email_id -> legacy_email. Mirrored facts are refreshed from
the Employee. Nothing is published by this patch; editors decide per profile.
"""

import frappe

from phamos.web_profile.mirror import refresh_mirrored_fields


def execute():
	columns = set(frappe.db.get_table_columns("Person Web Profile"))
	if "employee" not in columns:
		return
	legacy = [c for c in ("employee", "profile_image", "bio", "email_id") if c in columns]
	rows = frappe.db.sql(
		f"select name, {', '.join(f'`{c}`' for c in legacy)} from `tabPerson Web Profile`"
		" where ifnull(party, '') = ''",
		as_dict=True,
	)
	for row in rows:
		if not row.employee or not frappe.db.exists("Employee", row.employee):
			continue
		doc = frappe.get_doc("Person Web Profile", row.name)
		doc.party_type, doc.party = "Employee", row.employee
		if row.get("profile_image") and not doc.image:
			doc.image = row.profile_image
		if row.get("bio"):
			doc.legacy_bio = row.bio
			if not any(t.language == "en" for t in doc.get("translations") or []):
				doc.append("translations", {"language": "en", "content": row.bio})
		if row.get("email_id"):
			doc.legacy_email = row.email_id
		refresh_mirrored_fields(doc)
		doc.set_route()
		doc.db_update()
		doc.update_child_table("translations")
