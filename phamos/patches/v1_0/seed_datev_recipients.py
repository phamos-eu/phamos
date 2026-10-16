"""Move the DATEV upload addresses from Accounting Receipt field defaults to phamos Settings.

Until now every receipt carried two read-only address fields: one for incoming invoices and
one for all other documents ("Sonstiges"). The settings table keeps that routing: invoices,
credit notes and receipts go to the invoice address (the default), everything else to the
second address. Runs only while the table is
empty, so addresses edited in the settings are never overwritten.
"""

import frappe

SETTINGS_DOCTYPE = "phamos Settings"
LEGACY_INVOICE_ADDRESS = "5ae13779-6eb8-43a1-9292-87d9b30bf1a8@uploadmail.datev.de"
LEGACY_OTHER_ADDRESS = "8b013751-c088-48a9-a998-1745463f94a0@uploadmail.datev.de"


def execute():
	settings = frappe.get_single(SETTINGS_DOCTYPE)
	if settings.get("datev_recipients"):
		return
	settings.append(
		"datev_recipients",
		{
			"label": "Eingangsrechnungen",
			"email": LEGACY_INVOICE_ADDRESS,
			"receipt_types": "Invoice, Credit Note, Receipt",
			"is_default": 1,
		},
	)
	settings.append(
		"datev_recipients",
		{"label": "Sonstiges", "email": LEGACY_OTHER_ADDRESS, "receipt_types": "Tax Notice, Contract, Reminder, Statement, Other", "is_default": 0},
	)
	settings.flags.ignore_mandatory = True
	settings.save(ignore_permissions=True)
