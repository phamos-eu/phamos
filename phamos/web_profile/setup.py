"""Custom fields the Web Profile website needs on standard doctypes (run after every migrate)."""

from frappe.custom.doctype.custom_field.custom_field import create_custom_fields

# Web Page: one page per language, linked as translations (phamos/phamos#1502). The German page is
# the master; the English page points to it with "Translation Of".
WEB_PAGE_FIELDS = {
	"Web Page": [
		{
			"fieldname": "language",
			"fieldtype": "Select",
			"label": "Language",
			"options": "\nde\nen",
			"insert_after": "route",
			"description": "Page language. Use routes de/… and en/… so navbar, footer and language picker can switch.",
			"module": "Phamos",
		},
		{
			"fieldname": "translation_of",
			"fieldtype": "Link",
			"label": "Translation Of",
			"options": "Web Page",
			"insert_after": "language",
			"depends_on": "eval:doc.language && doc.language != 'de'",
			"description": "For the English page: the German page it translates.",
			"module": "Phamos",
		},
	]
}


def after_migrate():
	create_custom_fields(WEB_PAGE_FIELDS, update=True)
