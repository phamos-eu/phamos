"""Website texts move from ``*_en`` / ``*_de`` fields into the "Web Profile Content" table
(phamos/phamos#1505), so new website languages add rows instead of fields.

The old columns stay in the tables after the model sync (Frappe never drops columns). Every
record with old values gets one row per language unless it already has a row for that language;
short labels move into their single English field, the German value becomes a Translation
record. Safe to run twice.
"""

import frappe

LANGUAGES = ("en", "de")
# profile doctype -> {row field: old field base name}
TEXT_FIELDS = {
	"Person Web Profile": {"summary": "summary", "content": "bio"},
	"Stakeholder Web Profile": {"summary": "summary", "content": "description"},
	"Department Web Profile": {"summary": "summary", "content": "description"},
	"Team Web Profile": {"summary": "summary", "content": "description"},
	"Module Web Profile": {"summary": "summary", "content": "description"},
	"Implementation Web Profile": {"title": "title", "summary": "summary", "content": "description"},
	"Industry Web Profile": {"title": "title", "summary": "summary", "content": "description"},  # only title_de existed
}


def execute():
	for doctype, fields in TEXT_FIELDS.items():
		move_texts(doctype, fields)
	move_role_labels()
	move_settings_label()


def move_texts(doctype, fields):
	columns = set(frappe.db.get_table_columns(doctype))
	old = [f"{base}_{lang}" for base in fields.values() for lang in LANGUAGES if f"{base}_{lang}" in columns]
	if not old:
		return
	rows = frappe.get_all("Web Profile Content", filters={"parenttype": doctype}, fields=["parent", "language", "idx"])
	existing = {(r.parent, r.language) for r in rows}
	next_idx = {}
	for r in rows:
		next_idx[r.parent] = max(next_idx.get(r.parent, 0), r.idx)

	for record in frappe.db.sql(f"select name, {', '.join(f'`{c}`' for c in old)} from `tab{doctype}`", as_dict=True):
		for lang in LANGUAGES:
			values = {field: record.get(f"{base}_{lang}") for field, base in fields.items()}
			values = {field: value for field, value in values.items() if value}
			if not values or (record.name, lang) in existing:
				continue
			next_idx[record.name] = next_idx.get(record.name, 0) + 1
			frappe.get_doc({
				"doctype": "Web Profile Content",
				"parent": record.name,
				"parenttype": doctype,
				"parentfield": "translations",
				"idx": next_idx[record.name],
				"language": lang,
				**values,
			}).db_insert()


def move_role_labels():
	doctype = "Implementation Web Profile Person"
	columns = set(frappe.db.get_table_columns(doctype))
	if "role_en" not in columns and "role_de" not in columns:
		return
	old = [c for c in ("role_en", "role_de") if c in columns]
	for r in frappe.db.sql(f"select name, role, {', '.join(old)} from `tab{doctype}`", as_dict=True):
		english = r.get("role_en") or r.get("role_de")
		if r.role or not english:
			continue
		frappe.db.set_value(doctype, r.name, "role", english, update_modified=False)
		add_translation(english, r.get("role_de"))


def move_settings_label():
	old = dict(frappe.db.sql(
		"select field, value from `tabSingles` where doctype = 'Web Profile Settings'"
		" and field in ('sales_contact_role_en', 'sales_contact_role_de')"))
	english = old.get("sales_contact_role_en") or old.get("sales_contact_role_de")
	if not english:
		return
	frappe.db.set_single_value("Web Profile Settings", "sales_contact_role", english)
	add_translation(english, old.get("sales_contact_role_de"))


def add_translation(english, german):
	if german and german != english and not frappe.db.exists("Translation", {"source_text": english, "language": "de"}):
		frappe.get_doc({"doctype": "Translation", "language": "de", "source_text": english,
			"translated_text": german}).insert(ignore_permissions=True)
