# Copyright (c) 2026, phamos.eu and contributors
# For license information, please see license.txt

"""Expense accounts that receipt lines are booked on.

The expense account is the one thing a receipt line needs: a person picks it in the
cockpit, the Purchase Invoice line carries it, and DATEV sees it. There is no extra
category layer. To give the AI (and later the assignment library) a short, curated list
instead of the whole chart, accounts carry two custom fields:

- `custom_ai_selectable`: the account is offered to the AI when it proposes an account.
- `custom_ai_keywords`: comma-separated words on a receipt line that point to it.

People can still book a line on any expense account; the flag only shapes what the AI
proposes. The seed below marks a starting set for a software and consulting company on
SKR04. The accounting office should check it once. A few vendor keywords follow the
MIT-licensed rule set of github.com/GalieJJ/accounti, translated to SKR04.
"""

import frappe
from frappe.custom.doctype.custom_field.custom_field import create_custom_fields
from frappe.utils import cstr

SELECTABLE_FIELD = "custom_ai_selectable"
KEYWORDS_FIELD = "custom_ai_keywords"

# (SKR04 account number, keywords)  # what the account stands for
SEED_SKR04 = [
	("6805", "telefon, mobilfunk, handy, sim, festnetz, magentamobil, telekom, vodafone, o2, 1&1, sipgate, easybell"),  # Telekommunikation
	("6810", "hosting, server, cloud, domain, dns, ssl, zertifikat, traffic, storage, hetzner, aws, azure, ionos, strato, ovh, cloudflare, internet"),  # Hosting & Cloud
	("6837", "abo, subscription, lizenz, saas, monthly plan, pro plan, seat, cursor, icloud, github, gitlab, slack, notion, microsoft 365, adobe, atlassian, openai, anthropic, mistral, figma, zoom, dropbox"),  # Software-Abos
	("6495", "wartung, maintenance, support, servicevertrag, applecare, reparatur, update service"),  # Wartung Hard- & Software
	("6260", "monitor, bildschirm, tastatur, maus, headset, webcam, drucker, dockingstation, ssd, festplatte, stuhl, lampe"),  # Geringwertige Wirtschaftsgüter
	("6845", "kabel, adapter, ladegerät, usb, hub, werkzeug, batterie"),  # Werkzeuge & Kleingeräte
	("6815", "papier, toner, patrone, stifte, büromaterial, ordner, etiketten, schreibwaren, staples, viking"),  # Bürobedarf
	("6850", "kaffee, getränke, wasser, reinigungsmittel, küche, hygiene"),  # Betriebsbedarf
	("6800", "porto, briefmarke, versand, paket, einschreiben, dhl, dpd, gls, ups, hermes, fedex"),  # Porto & Versand
	("6820", "buch, bücher, zeitschrift, ebook, fachzeitschrift, kindle, verlag, abonnement zeitung"),  # Fachliteratur
	("6821", "schulung, seminar, workshop, kurs, training, konferenz, tagung, zertifizierung, udemy, teilnahmegebühr"),  # Fortbildung
	("6825", "rechtsanwalt, anwalt, kanzlei, notar, gutachten, rechtsberatung"),  # Rechts- & Beratungskosten
	("6827", "jahresabschluss, bilanz, steuerberatung, steuerberater, prüfung, steuererklärung"),  # Abschluss- & Prüfungskosten
	("6830", "buchführung, buchhaltung, datev, lohnabrechnung, finanzbuchhaltung"),  # Buchführungskosten
	("6303", "freelancer, subunternehmer, dienstleistung, development, entwicklung, professional services, dayrate, tagessatz, consulting, implementierung, projektleistung"),  # Fremdleistungen
	("6640", "restaurant, bewirtung, essen, gaststätte, café, lunch, dinner, catering, menü"),  # Bewirtung
	("6663", "bahn, db fernverkehr, flug, flugticket, taxi, uber, mietwagen, parken, parkhaus, flixbus, lufthansa, öpnv"),  # Reisekosten Fahrt
	("6660", "hotel, übernachtung, booking, airbnb, unterkunft"),  # Reisekosten Übernachtung
	("6664", "verpflegungsmehraufwand, verpflegungspauschale, tagegeld"),  # Verpflegungsmehraufwand
	("6530", "tanken, kraftstoff, benzin, diesel, super, e10, ladestrom, aral, shell, esso, jet, waschanlage, tankstelle"),  # Kfz-Kosten
	("6310", "miete, büromiete, coworking, raummiete, office"),  # Miete
	("6325", "strom, gas, energie, stadtwerke, nebenkosten, heizung"),  # Energie & Nebenkosten
	("6400", "versicherung, haftpflicht, police, prämie, beitragsrechnung versicherung, hiscox, allianz"),  # Versicherungen
	("6420", "mitgliedsbeitrag, ihk, verband, kammer, beitrag, rundfunkbeitrag"),  # Beiträge & Gebühren
	("6600", "werbung, anzeige, ads, marketing, messe, flyer, sponsoring, druckerei, linkedin ads, google ads"),  # Werbung & Marketing
	("6610", "geschenk, präsent, blumen, weinpräsent"),  # Geschenke
	("6855", "kontoführung, bankgebühr, transaktionsgebühr, stripe fee, paypal gebühr, wise fee"),  # Nebenkosten Geldverkehr
	("7300", "zinsen, verzugszinsen, mahngebühr, säumniszuschlag"),  # Zinsen & Mahnkosten
	("6300", "sonstiges, diverse"),  # Sonstige betriebliche Aufwendungen
]


def ensure_account_fields():
	meta = frappe.get_meta("Account")
	if meta.has_field(SELECTABLE_FIELD) and meta.has_field(KEYWORDS_FIELD):
		return
	create_custom_fields(
		{
			"Account": [
				{
					"fieldname": SELECTABLE_FIELD,
					"label": "Offered to the AI",
					"fieldtype": "Check",
					"insert_after": "account_type",
					"module": "Phamos",
					"depends_on": "eval:doc.root_type=='Expense' && !doc.is_group",
					"description": "The AI Accountant may propose this account for receipt lines.",
				},
				{
					"fieldname": KEYWORDS_FIELD,
					"label": "AI Keywords",
					"fieldtype": "Small Text",
					"insert_after": SELECTABLE_FIELD,
					"module": "Phamos",
					"depends_on": f"eval:doc.{SELECTABLE_FIELD}",
					"description": "Comma-separated words on a receipt line that point to this account.",
				},
			]
		},
		update=False,
	)


def ensure_expense_account_setup():
	"""Called from setup: the two fields, and the seed for SKR04 companies that have no
	account offered to the AI yet. A company where someone already chose accounts is left
	alone, so a migrate never undoes that choice."""
	ensure_account_fields()
	for company in frappe.get_all("Company", pluck="name"):
		if chart_family(company) == "SKR04" and not frappe.db.exists(
			"Account", {"company": company, SELECTABLE_FIELD: 1}
		):
			seed_expense_accounts(company, check_permission=False)


def chart_family(company):
	chart = cstr(frappe.db.get_value("Company", company, "chart_of_accounts")).upper()
	if "SKR04" in chart:
		return "SKR04"
	if "SKR03" in chart:
		return "SKR03"
	return None


def account_by_number(company, number):
	return frappe.db.get_value("Account", {"company": company, "account_number": number, "is_group": 0}, "name")


@frappe.whitelist(methods=["POST"])
def seed_expense_accounts(company=None, check_permission=True):
	"""Offer the SKR04 seed accounts to the AI and fill their keywords where empty.
	Returns marked / missing (account numbers the chart does not have)."""
	if check_permission:
		frappe.only_for(("System Manager", "Accounts Manager"))
	company = company or frappe.defaults.get_global_default("company")
	ensure_account_fields()
	result = {"marked": [], "missing": []}
	for number, keywords in SEED_SKR04:
		account = account_by_number(company, number)
		if not account:
			result["missing"].append(number)
			continue
		values = {SELECTABLE_FIELD: 1}
		if not frappe.db.get_value("Account", account, KEYWORDS_FIELD):
			values[KEYWORDS_FIELD] = keywords
		frappe.db.set_value("Account", account, values, update_modified=False)
		result["marked"].append(account)
	clear_account_cache()
	return result


def ai_expense_accounts(company):
	"""The accounts offered to the AI: [{account, account_number, account_name, keywords}], cached."""
	key = f"phamos_ai_expense_accounts:{company}"
	cached = frappe.cache.get_value(key)
	if cached is not None:
		return cached
	rows = frappe.get_all(
		"Account",
		filters={"company": company, SELECTABLE_FIELD: 1, "root_type": "Expense", "is_group": 0, "disabled": 0},
		fields=["name", "account_number", "account_name", KEYWORDS_FIELD],
		order_by="account_number asc",
	)
	result = [
		{
			"account": r.name,
			"account_number": r.account_number,
			"account_name": r.account_name,
			"keywords": [k.strip() for k in cstr(r.get(KEYWORDS_FIELD)).split(",") if k.strip()],
		}
		for r in rows
	]
	frappe.cache.set_value(key, result, expires_in_sec=600)
	return result


def clear_account_cache(doc=None, event=None):
	for company in frappe.get_all("Company", pluck="name"):
		frappe.cache.delete_value(f"phamos_ai_expense_accounts:{company}")


def is_expense_account(account, company):
	row = frappe.db.get_value("Account", account, ["company", "root_type", "is_group", "disabled"], as_dict=True)
	return bool(row and row.company == company and row.root_type == "Expense" and not row.is_group and not row.disabled)


def item_tax_template_for_rate(rate, company):
	"""Item Tax Template of the company whose highest rate equals the line's tax rate."""
	if rate is None or rate == "":
		return None
	rows = frappe.db.sql(
		"""select t.name, max(d.tax_rate) as rate
		from `tabItem Tax Template` t join `tabItem Tax Template Detail` d on d.parent = t.name
		where t.company = %s and ifnull(t.disabled, 0) = 0
		group by t.name""",
		company,
		as_dict=True,
	)
	for row in rows:
		if abs(float(row.rate or 0) - float(rate)) < 0.01:
			return row.name
	return None
