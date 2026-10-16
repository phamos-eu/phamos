# Copyright (c) 2026, phamos.eu and contributors
# For license information, please see license.txt

"""Expense categories: Items that stand for a kind of expense, not for a product.

Purchase lines are never turned into new Items. A line ("MagentaMobil M Business") is
assigned to a category ("Telekommunikation"); the category's Item Default carries the
expense account per company (SKR04 6805 Telefon). ERPNext reads that account when the
Purchase Invoice is built. Only humans create categories; the AI proposes.

The seed list is a starting point for a software and consulting company on SKR04 and
should be checked by the accounting office once. Keywords help matching (AI prompt and,
later, the assignment library); a few vendor keywords follow the MIT-licensed rule set of
github.com/GalieJJ/accounti, translated to SKR04.
"""

import frappe
from frappe import _
from frappe.custom.doctype.custom_field.custom_field import create_custom_fields
from frappe.utils import cstr

SETTINGS_DOCTYPE = "phamos Settings"
DEFAULT_GROUP = "Expense Categories"
KEYWORDS_FIELD = "custom_ai_keywords"

# (category, SKR04 account number, keywords)
SEED_SKR04 = [
	("Telekommunikation", "6805", "telefon, mobilfunk, handy, sim, festnetz, magentamobil, telekom, vodafone, o2, 1&1, sipgate, easybell"),
	("Hosting & Cloud", "6810", "hosting, server, cloud, domain, dns, ssl, zertifikat, traffic, storage, hetzner, aws, azure, ionos, strato, ovh, cloudflare, internet"),
	("Software-Abos", "6837", "abo, subscription, lizenz, saas, monthly plan, pro plan, seat, cursor, icloud, github, gitlab, slack, notion, microsoft 365, adobe, atlassian, openai, anthropic, mistral, figma, zoom, dropbox"),
	("Wartung Hard- & Software", "6495", "wartung, maintenance, support, servicevertrag, applecare, reparatur, update service"),
	("Geringwertige Wirtschaftsgüter", "6260", "monitor, bildschirm, tastatur, maus, headset, webcam, drucker, dockingstation, ssd, festplatte, stuhl, lampe"),
	("Werkzeuge & Kleingeräte", "6845", "kabel, adapter, ladegerät, usb, hub, werkzeug, batterie"),
	("Bürobedarf", "6815", "papier, toner, patrone, stifte, büromaterial, ordner, etiketten, schreibwaren, staples, viking"),
	("Betriebsbedarf", "6850", "kaffee, getränke, wasser, reinigungsmittel, küche, hygiene"),
	("Porto & Versand", "6800", "porto, briefmarke, versand, paket, einschreiben, dhl, dpd, gls, ups, hermes, fedex"),
	("Fachliteratur", "6820", "buch, bücher, zeitschrift, ebook, fachzeitschrift, kindle, verlag, abonnement zeitung"),
	("Fortbildung", "6821", "schulung, seminar, workshop, kurs, training, konferenz, tagung, zertifizierung, udemy, teilnahmegebühr"),
	("Rechts- & Beratungskosten", "6825", "rechtsanwalt, anwalt, kanzlei, notar, gutachten, rechtsberatung"),
	("Abschluss- & Prüfungskosten", "6827", "jahresabschluss, bilanz, steuerberatung, steuerberater, prüfung, steuererklärung"),
	("Buchführungskosten", "6830", "buchführung, buchhaltung, datev, lohnabrechnung, finanzbuchhaltung"),
	("Fremdleistungen", "6303", "freelancer, subunternehmer, dienstleistung, development, entwicklung, professional services, dayrate, tagessatz, consulting, implementierung, projektleistung"),
	("Bewirtung", "6640", "restaurant, bewirtung, essen, gaststätte, café, lunch, dinner, catering, menü"),
	("Reisekosten Fahrt", "6663", "bahn, db fernverkehr, flug, flugticket, taxi, uber, mietwagen, parken, parkhaus, flixbus, lufthansa, öpnv"),
	("Reisekosten Übernachtung", "6660", "hotel, übernachtung, booking, airbnb, unterkunft"),
	("Verpflegungsmehraufwand", "6664", "verpflegungsmehraufwand, verpflegungspauschale, tagegeld"),
	("Kfz-Kosten", "6530", "tanken, kraftstoff, benzin, diesel, super, e10, ladestrom, aral, shell, esso, jet, waschanlage, tankstelle"),
	("Miete", "6310", "miete, büromiete, coworking, raummiete, office"),
	("Energie & Nebenkosten", "6325", "strom, gas, energie, stadtwerke, nebenkosten, heizung"),
	("Versicherungen", "6400", "versicherung, haftpflicht, police, prämie, beitragsrechnung versicherung, hiscox, allianz"),
	("Beiträge & Gebühren", "6420", "mitgliedsbeitrag, ihk, verband, kammer, beitrag, rundfunkbeitrag"),
	("Werbung & Marketing", "6600", "werbung, anzeige, ads, marketing, messe, flyer, sponsoring, druckerei, linkedin ads, google ads"),
	("Geschenke", "6610", "geschenk, präsent, blumen, weinpräsent"),
	("Nebenkosten Geldverkehr", "6855", "kontoführung, bankgebühr, transaktionsgebühr, stripe fee, paypal gebühr, wise fee"),
	("Zinsen & Mahnkosten", "7300", "zinsen, verzugszinsen, mahngebühr, säumniszuschlag"),
	("Sonstige betriebliche Aufwendungen", "6300", "sonstiges, diverse"),
]


def expense_group():
	return frappe.db.get_single_value(SETTINGS_DOCTYPE, "ai_expense_item_group") or DEFAULT_GROUP


def ensure_keywords_field():
	if frappe.get_meta("Item").has_field(KEYWORDS_FIELD):
		return
	create_custom_fields(
		{
			"Item": [
				{
					"fieldname": KEYWORDS_FIELD,
					"label": "AI Keywords",
					"fieldtype": "Small Text",
					"insert_after": "description",
					"module": "Phamos",
					"description": "Expense categories: comma-separated words that point to this category on a receipt line.",
				}
			]
		},
		update=False,
	)


def ensure_expense_item_group():
	"""Create the group; returns True when it was created just now."""
	group = expense_group()
	if frappe.db.exists("Item Group", group):
		return False
	frappe.get_doc(
		{"doctype": "Item Group", "item_group_name": group, "parent_item_group": "All Item Groups", "is_group": 0}
	).insert(ignore_permissions=True)
	if not frappe.db.get_single_value(SETTINGS_DOCTYPE, "ai_expense_item_group"):
		frappe.db.set_single_value(SETTINGS_DOCTYPE, "ai_expense_item_group", group)
	return True


def ensure_categories_setup():
	"""Called from setup: field, group, and the seed on first install for SKR04 companies.

	The seed runs only when the group did not exist before, so categories someone deleted
	are never created again by a migrate.
	"""
	ensure_keywords_field()
	if ensure_expense_item_group():
		for company in frappe.get_all("Company", pluck="name"):
			if chart_family(company) == "SKR04":
				seed_expense_categories(company)


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
def seed_expense_categories(company=None, only_missing=1):
	"""Create the SKR04 seed categories for a company. Existing Items are left alone,
	except that an empty keyword field is filled. Returns created / skipped / no_account."""
	frappe.only_for(("System Manager", "Accounts Manager"))
	company = company or frappe.defaults.get_global_default("company")
	ensure_keywords_field()
	ensure_expense_item_group()
	result = {"created": [], "skipped": [], "no_account": []}
	for name, number, keywords in SEED_SKR04:
		account = account_by_number(company, number)
		if frappe.db.exists("Item", name):
			if not frappe.db.get_value("Item", name, KEYWORDS_FIELD):
				frappe.db.set_value("Item", name, KEYWORDS_FIELD, keywords)
			result["skipped"].append(name)
			continue
		create_expense_category(name, account, company, keywords, check_permission=False)
		result["created" if account else "no_account"].append(name)
	clear_category_cache()
	return result


def create_expense_category(name, expense_account=None, company=None, keywords=None, cost_center=None, check_permission=True):
	"""Item in the expense group with an Item Default expense account for the company."""
	if check_permission:
		frappe.only_for(("System Manager", "Accounts Manager"))
	name = cstr(name).strip()
	if not name:
		frappe.throw(_("A category needs a name."))
	if frappe.db.exists("Item", name):
		frappe.throw(_("{0} already exists.").format(name))
	company = company or frappe.defaults.get_global_default("company")
	if expense_account:
		account = frappe.db.get_value("Account", expense_account, ["company", "root_type", "is_group"], as_dict=True)
		if not account or account.company != company or account.is_group or account.root_type != "Expense":
			frappe.throw(_("{0} is not an expense account of {1}.").format(expense_account, company))
	item = frappe.get_doc(
		{
			"doctype": "Item",
			"item_code": name,
			"item_name": name,
			"item_group": expense_group(),
			"stock_uom": "Nos",
			"is_stock_item": 0,
			"is_sales_item": 0,
			"is_purchase_item": 1,
			"include_item_in_manufacturing": 0,
			KEYWORDS_FIELD: keywords,
			"item_defaults": [
				{"company": company, "expense_account": expense_account, "buying_cost_center": cost_center}
			]
			if expense_account or cost_center
			else [],
		}
	)
	# Accounts users usually have no Item permission; categories live only in their group.
	item.insert(ignore_permissions=True)
	clear_category_cache()
	return item.name


def expense_categories(company):
	"""[{item_code, item_name, expense_account, account_number, account_name, keywords}], cached."""
	key = f"phamos_expense_categories:{company}"
	cached = frappe.cache.get_value(key)
	if cached is not None:
		return cached
	items = frappe.get_all(
		"Item",
		filters={"item_group": expense_group(), "disabled": 0},
		fields=["name", "item_name", KEYWORDS_FIELD],
		order_by="item_name asc",
	)
	result = []
	for item in items:
		account = resolve_expense_account(item.name, company)
		number, account_name = (frappe.db.get_value("Account", account, ["account_number", "account_name"]) or (None, None)) if account else (None, None)
		result.append(
			{
				"item_code": item.name,
				"item_name": item.item_name,
				"expense_account": account,
				"account_number": number,
				"account_name": account_name,
				"keywords": [k.strip() for k in cstr(item.get(KEYWORDS_FIELD)).split(",") if k.strip()],
			}
		)
	frappe.cache.set_value(key, result, expires_in_sec=600)
	return result


def clear_category_cache(doc=None, event=None):
	for company in frappe.get_all("Company", pluck="name"):
		frappe.cache.delete_value(f"phamos_expense_categories:{company}")


def resolve_expense_account(item_code, company):
	"""Expense account of a category: Item Default, then Item Group Default. Never the
	company default account (for SKR04 companies that is a production-cost account)."""
	if not item_code or not company:
		return None
	account = frappe.db.get_value("Item Default", {"parent": item_code, "parenttype": "Item", "company": company}, "expense_account")
	if account:
		return account
	group = frappe.db.get_value("Item", item_code, "item_group")
	return frappe.db.get_value(
		"Item Default", {"parent": group, "parenttype": "Item Group", "company": company}, "expense_account"
	)


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
