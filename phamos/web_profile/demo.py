"""Demo data for testing the Web Profile pages on a local developer site. Never runs in production.

    bench --site dev.localhost execute phamos.web_profile.demo.seed

Idempotent: records are looked up by their natural keys and only created when missing.
People use the names and public titles from the former Website Person fixtures; everything
else (bios, languages, expertise, teams, customers, implementations) is placeholder content.
"""

import frappe
from frappe.utils import add_years, getdate, nowdate

DEMO_NOTE_EN = "Placeholder text for local testing."
DEMO_NOTE_DE = "Platzhaltertext für lokale Tests."

PEOPLE = [
	# name, designation, department, years at phamos, modules, team
	("Wolfram Schmidt", "Managing Director", "Management", 8, ["Accounting", "Sales"], None),
	("Philipp Gutstein", "Head of HR & Project Lead", "Human Resources", 6, ["HR & Payroll", "Projects"], None),
	("Roque Vera", "Head of Software Development", "Software Development", 5, ["Accounting", "Manufacturing"], "Green Team"),
	("Furqan Asghar", "Software Developer", "Software Development", 4, ["Accounting", "CRM"], "Green Team"),
	("Robera Workneh", "Software Developer", "Software Development", 3, ["Inventory", "Manufacturing"], "Green Team"),
	("Muhammad Ali Baig", "Software Developer", "Software Development", 3, ["CRM", "Sales"], "Green Team"),
	("Sonali Narkar", "Software Developer", "Software Development", 3, ["Projects", "Helpdesk"], "Blue Team"),
	("Gunther Schmidt", "Head of Project Management", "Project Management", 4, ["Projects", "Quality Management"], "Blue Team"),
	("Simon Peter Wanyama", "Software Developer", "Software Development", 2, ["Inventory", "Purchase"], "Blue Team"),
	("Kamal Singh", "Software Developer", "Software Development", 2, ["Accounting", "Purchase"], "Blue Team"),
	("Kalsoom Akhtar", "Software Developer", "Software Development", 2, ["HR & Payroll", "Helpdesk"], "Blue Team"),
	("Rainer Kloker", "Project Manager", "Project Management", 3, ["Projects", "Inventory"], "Green Team"),
	("Celia Lohner", "Project Manager", "Project Management", 1, ["Projects", "CRM"], "Blue Team"),
]
# Fictional former colleagues: one consented to a named alumni profile, one did not.
ALUMNI = [
	("Lisa Bauer", "Project Manager", "Project Management", 4, True, ["Projects"]),
	("Max Mustermann", "Software Developer", "Software Development", 3, False, ["Accounting"]),
]
TEAMS = {
	"Green Team": ("Roque Vera", 2021, "Precision for manufacturing and finance projects.", "Präzision für Fertigungs- und Finanzprojekte."),
	"Blue Team": ("Gunther Schmidt", 2022, "Steady delivery for service and project businesses.", "Verlässliche Umsetzung für Dienstleister und Projektgeschäft."),
}
DEPARTMENT_LEADS = {
	"Management": "Wolfram Schmidt",
	"Human Resources": "Philipp Gutstein",
	"Software Development": "Roque Vera",
	"Project Management": "Gunther Schmidt",
}
MODULES = {
	# name: (complexity, duration, EN subtitle, DE subtitle)
	"Accounting": ("Critical", "8–12 weeks", "Financial accounting, banking and closing.", "Finanzbuchhaltung, Banking und Abschluss."),
	"Sales": ("Medium", "3–5 weeks", "Quotations, orders and pricing.", "Angebote, Aufträge und Preise."),
	"Purchase": ("Medium", "3–5 weeks", "Suppliers, requests and purchase orders.", "Lieferanten, Anfragen und Bestellungen."),
	"Inventory": ("High", "4–8 weeks", "Stock, warehouses and serial numbers.", "Bestand, Lager und Seriennummern."),
	"Manufacturing": ("High", "6–10 weeks", "BOMs, work orders and production planning.", "Stücklisten, Arbeitsaufträge und Produktionsplanung."),
	"Projects": ("Medium", "3–6 weeks", "Projects, tasks and timesheets.", "Projekte, Aufgaben und Zeiterfassung."),
	"HR & Payroll": ("High", "6–8 weeks", "Employees, leave and payroll.", "Mitarbeitende, Abwesenheiten und Lohn."),
	"CRM": ("Low", "2–4 weeks", "Leads, opportunities and follow-ups.", "Leads, Chancen und Wiedervorlagen."),
	"Helpdesk": ("Low", "2–3 weeks", "Tickets, SLAs and customer support.", "Tickets, SLAs und Kundensupport."),
	"Quality Management": ("Medium", "3–5 weeks", "Inspections, procedures and non-conformance.", "Prüfungen, Verfahren und Abweichungen."),
}
# ERPNext workspace per module: the website shows that workspace's official icon.
MODULE_WORKSPACES = {
	"Accounting": "Accounting", "Sales": "Selling", "Purchase": "Buying", "Inventory": "Stock",
	"Manufacturing": "Manufacturing", "Projects": "Projects", "HR & Payroll": "HR", "CRM": "CRM",
	"Helpdesk": "Support", "Quality Management": "Quality",
}
INDUSTRIES = {
	"Manufacturing": ("Fertigung", ["Manufacturing", "Inventory", "Quality Management", "Accounting"]),
	"Retail & Wholesale": ("Handel", ["Sales", "Inventory", "Purchase", "CRM"]),
	"Health Care": ("Gesundheitswesen", ["HR & Payroll", "Helpdesk", "Projects"]),
}
# Fictional people at customers and partners. example.com addresses, so test messages reach nobody.
EXTERNAL_PEOPLE = [
	# name, designation, party type, party, email, contact consent
	("Anna Krüger", "Head of Operations", "Customer", "Nordwerk Maschinenbau GmbH", "anna.krueger@example.com", True),
	("Jonas Weber", "Managing Director", "Customer", "Alpenfrisch Handels AG", "jonas.weber@example.com", False),
	("Mira Hoffmann", "Partner Manager", "Supplier", "Datenwerk IT-Services", "mira.hoffmann@example.com", True),
]
# Social profiles for the fictional people only (example URLs). Real people add their own.
SOCIALS = {
	"Anna Krüger": ["https://www.linkedin.com/in/anna-krueger-example", "https://www.xing.com/profile/Anna_Krueger_example"],
	"Mira Hoffmann": ["https://www.linkedin.com/in/mira-hoffmann-example", "https://datenwerk-it.example"],
	"Lisa Bauer": ["https://www.linkedin.com/in/lisa-bauer-example", "https://github.com/lisa-bauer-example"],
}
PROJECT_PEOPLE = {
	# customer: [(person name, role EN, role DE)]
	"Nordwerk Maschinenbau GmbH": [("Rainer Kloker", "Project manager", "Projektleitung"),
		("Roque Vera", "Lead developer", "Leitende Entwicklung"), ("Anna Krüger", "Project manager", "Projektleitung")],
	# Not approved for naming: Jonas Weber must not appear on this case (his profile names Alpenfrisch).
	"Alpenfrisch Handels AG": [("Celia Lohner", "Project manager", "Projektleitung"), ("Jonas Weber", "Sponsor", "Sponsor")],
}
# Shown in the sidebar of module / industry pages as "Your contact".
TOPIC_CONTACTS = {
	("Module Web Profile", "Accounting"): "Furqan Asghar",
	("Module Web Profile", "Manufacturing"): "Roque Vera",
	("Module Web Profile", "Projects"): "Gunther Schmidt",
	("Module Web Profile", "HR & Payroll"): "Philipp Gutstein",
	("Industry Web Profile", "Manufacturing"): "Roque Vera",
	("Industry Web Profile", "Retail & Wholesale"): "Muhammad Ali Baig",
}
# The implementation managers on each side get the "Key Person" tick (sidebar).
KEY_PEOPLE = {"Rainer Kloker", "Anna Krüger", "Celia Lohner"}
CUSTOMERS = [
	# customer, industry, approved, region, team, status, start year, modules, EN title, DE title
	("Nordwerk Maschinenbau GmbH", "Manufacturing", True, "DACH", "Green Team", "Completed", 2023,
		["Manufacturing", "Inventory", "Accounting"], "ERPNext for a growing machine builder", "ERPNext für einen wachsenden Maschinenbauer"),
	("Alpenfrisch Handels AG", "Retail & Wholesale", False, "DACH", "Blue Team", "Open", 2024,
		["Sales", "Inventory", "Purchase"], "", ""),
	("Klinikverbund Süd", "Health Care", True, "Germany", "Blue Team", "Completed", 2022,
		["HR & Payroll", "Projects"], "HR and payroll for a hospital group", "HR und Lohn für einen Klinikverbund"),
	("Feinguss Rhein GmbH", "Manufacturing", False, "Germany", "Green Team", "Open", 2025,
		["Manufacturing", "Quality Management"], "", ""),
]


def seed():
	if not frappe.conf.developer_mode:
		frappe.throw("The Web Profile demo seed only runs on developer sites (developer_mode = 1).")
	frappe.flags.mute_emails = True
	company = frappe.defaults.get_global_default("company") or frappe.get_all("Company", pluck="name", limit=1)[0]

	employees = {}
	for name, designation, department, years, _modules, _team_name in PEOPLE:
		employees[name] = _employee(name, designation, _department(department, company), years, company)
	for name, designation, department, years, _consent, _modules in ALUMNI:
		employees[name] = _employee(name, designation, _department(department, company), years, company, left=True)

	for module, (complexity, duration, sub_en, sub_de) in MODULES.items():
		if not frappe.db.exists("Implementation Module", module):
			frappe.get_doc({"doctype": "Implementation Module", "module_name": module}).insert()
		_upsert("Module Web Profile", {"module": module}, {
			"complexity": complexity, "typical_duration": duration,
			"workspace": MODULE_WORKSPACES[module] if frappe.db.exists("Workspace", MODULE_WORKSPACES[module]) else None,
			"translations": _texts(en={"summary": sub_en, "content": f"<p>{DEMO_NOTE_EN}</p>"},
				de={"summary": sub_de, "content": f"<p>{DEMO_NOTE_DE}</p>"}),
		})

	for industry, (title_de, modules) in INDUSTRIES.items():
		_upsert("Industry Web Profile", {"industry": industry}, {
			"modules": [{"module": m} for m in modules],
			"translations": _texts(en={"summary": f"How we introduce ERPNext in {industry.lower()}."},
				de={"title": title_de, "summary": f"Wie wir ERPNext in der Branche {title_de} einführen."}),
		})

	_supplier("Datenwerk IT-Services")
	_customer("Nordwerk Maschinenbau GmbH", "Manufacturing")
	_customer("Alpenfrisch Handels AG", "Retail & Wholesale")
	profiles = {}
	for name, designation, party_type, party, email, contactable in EXTERNAL_PEOPLE:
		contact = _contact(name, designation, email, party_type, party)
		values = {
			"contact": contact, "publication_consent": 1, "publication_consent_date": nowdate(),
			"contact_consent": 1 if contactable else 0, "contact_consent_date": nowdate() if contactable else None,
			"translations": [],
			"languages": [{"language": "de"}, {"language": "en"}], "sort_order": 50,
			"profile_links": [{"profile_link": url} for url in SOCIALS.get(name, [])],
		}
		profiles[name] = _upsert("Person Web Profile", {"party_type": party_type, "party": party, "contact": contact}, values)

	for index, (name, _designation_name, _department_name, _years, modules, _team_name) in enumerate(PEOPLE):
		profiles[name] = _person_profile(employees[name], modules, consent=False, sort_order=index, languages=["en"])
	for name, _designation_name, _department_name, _years, consent, modules in ALUMNI:
		profile = _person_profile(employees[name], modules, consent=consent, sort_order=100, languages=["de", "en"])
		if name in SOCIALS:
			_upsert("Person Web Profile", {"name": profile}, {"profile_links": [{"profile_link": url} for url in SOCIALS[name]]})

	for team, (lead, founded, tag_en, tag_de) in TEAMS.items():
		members = [employees[p[0]] for p in PEOPLE if p[5] == team and p[0] != lead]
		_team(team, employees[lead], members)
		_upsert("Team Web Profile", {"team": team}, {
			"founded": founded,
			"translations": _texts(en={"summary": tag_en, "content": f"<p>{DEMO_NOTE_EN}</p>"},
				de={"summary": tag_de, "content": f"<p>{DEMO_NOTE_DE}</p>"}),
		})

	for department, lead in DEPARTMENT_LEADS.items():
		_upsert("Department Web Profile", {"department": _department(department, company)}, {
			"lead": employees[lead],
			"translations": _texts(en={"summary": f"The {department} department of phamos.", "content": f"<p>{DEMO_NOTE_EN}</p>"},
				de={"summary": f"Die Abteilung {department} bei phamos.", "content": f"<p>{DEMO_NOTE_DE}</p>"}),
		})

	for customer, industry, approved, region, team, status, year, modules, title_en, title_de in CUSTOMERS:
		_customer(customer, industry)
		implementation = _implementation(customer, team, status, year, modules)
		_upsert("Implementation Web Profile", {"implementation": implementation}, {
			"customer_approved": 1 if approved else 0,
			"customer_approval_date": nowdate() if approved else None,
			"region": region,
			"translations": _texts(en={"title": title_en}, de={"title": title_de}),
			"people": [{"person": profiles[p], "role": _label(en, de), "key_person": 1 if p in KEY_PEOPLE else 0}
				for p, en, de in PROJECT_PEOPLE.get(customer, [])],
		})

	# Named customer pages: only for customers that approved naming (the others stay anonymous).
	for customer, industry, approved, region, *_rest in CUSTOMERS:
		if not approved and customer != "Alpenfrisch Handels AG":
			continue  # Alpenfrisch: published without approval -> anonymous customer page
		frappe.db.set_value("Customer", customer, "website", f"www.{customer.split()[0].lower()}.example")
		key_contact = next((profiles[p[0]] for p in EXTERNAL_PEOPLE if p[3] == customer), None)
		_upsert("Stakeholder Web Profile", {"stakeholder_type": "Customer", "party_type": "Customer", "party": customer}, {
			"publish_as": "Named" if approved else "Anonymous",
			"naming_approved": 1 if approved else 0, "naming_approval_date": nowdate() if approved else None, "region": region,
			"key_person": key_contact, "account_manager": employees["Gunther Schmidt"] if "Klinik" in customer else employees["Rainer Kloker"],
			"translations": [],
		})

	# Fallback contact for pages without an identifiable person (Web Profile Settings).
	settings = frappe.get_single("Web Profile Settings")
	settings.sales_contact = profiles["Wolfram Schmidt"]
	settings.sales_contact_role = _label("Sales · phamos", "Vertrieb · phamos")
	settings.flags.ignore_permissions = True
	settings.save()

	# Partners: one fictional (the supplier of Mira Hoffmann), one real (phamos is a Frappe partner).
	_supplier("Frappe Technologies Pvt. Ltd.")
	for supplier, industry, region, key in [("Datenwerk IT-Services", "Technology", "DACH", "Mira Hoffmann"),
			("Frappe Technologies Pvt. Ltd.", "Software", "India", None)]:
		frappe.db.set_value("Supplier", supplier, "website",
			"frappe.io" if supplier.startswith("Frappe") else "www.datenwerk-it.example")
		_upsert("Stakeholder Web Profile", {"stakeholder_type": "Partner", "party_type": "Supplier", "party": supplier}, {
			"publish_as": "Named", "naming_approved": 1, "naming_approval_date": nowdate(), "industry": industry, "region": region,
			"key_person": profiles.get(key), "account_manager": employees["Wolfram Schmidt"],
			"translations": _texts(en={"content": f"<p>{DEMO_NOTE_EN}</p>"}, de={"content": f"<p>{DEMO_NOTE_DE}</p>"}),
		})

	for (doctype, name), person in TOPIC_CONTACTS.items():
		_upsert(doctype, {doctype.split(" ")[0].lower(): name}, {"key_person": profiles[person]})

	frappe.db.commit()
	frappe.cache.delete_value("web_profile_items")
	return "Web Profile demo data ready: open /en/people or /de/personen"


# --- helpers --------------------------------------------------------------------------------------


def _upsert(doctype, key, values, publish=True):
	name = frappe.db.get_value(doctype, key)
	doc = frappe.get_doc(doctype, name) if name else frappe.get_doc({"doctype": doctype, **key})
	doc.update(values)
	if publish:
		doc.published = 1
	doc.flags.ignore_permissions = True
	doc.save()
	return doc.name


def _department(department_name, company):
	name = frappe.db.get_value("Department", {"department_name": department_name, "company": company})
	if name:
		return name
	return frappe.get_doc({"doctype": "Department", "department_name": department_name, "company": company,
		"parent_department": "All Departments"}).insert().name


def _designation(designation):
	if not frappe.db.exists("Designation", designation):
		frappe.get_doc({"doctype": "Designation", "designation_name": designation}).insert()
	return designation


def _gender():
	for gender in ("Prefer not to say", "Other"):
		if frappe.db.exists("Gender", gender):
			return gender
	return frappe.get_doc({"doctype": "Gender", "gender": "Other"}).insert().name


def _employee(full_name, designation, department, years, company, left=False):
	first_name, _, last_name = full_name.partition(" ")
	name = frappe.db.get_value("Employee", {"employee_name": full_name})
	if name:
		return name
	joined = add_years(getdate(nowdate()), -(years + (2 if left else 0)))
	doc = frappe.get_doc({
		"doctype": "Employee", "first_name": first_name, "last_name": last_name, "company": company,
		"gender": _gender(), "date_of_birth": "1985-01-01", "date_of_joining": joined,
		"designation": _designation(designation), "department": department, "status": "Active",
	}).insert()
	if left:
		doc.status = "Left"
		doc.relieving_date = add_years(joined, years)
		doc.save()
	return doc.name


def _texts(**languages):
	"""Rows for the "Web Profile Content" table: _texts(en={"summary": …}, de={"title": …})."""
	return [{"language": lang, **values} for lang, values in languages.items()]


def _label(en, de):
	"""English label for a single-language field, German via Frappe's Translation list."""
	if de and de != en and not frappe.db.exists("Translation", {"source_text": en, "language": "de"}):
		frappe.get_doc({"doctype": "Translation", "language": "de", "source_text": en, "translated_text": de}).insert()
	return en


def _person_profile(employee, modules, consent, sort_order, languages):
	designation, department = frappe.db.get_value("Employee", employee, ["designation", "department"])
	department_name = frappe.db.get_value("Department", department, "department_name")
	values = {
		"modules": [{"module": m} for m in modules],
		"languages": [{"language": code} for code in languages],
		"sort_order": sort_order,
		"translations": [],
		"alumni_consent": 1 if consent else 0,
		"alumni_consent_date": nowdate() if consent else None,
	}
	return _upsert("Person Web Profile", {"party_type": "Employee", "party": employee}, values)


def _team(team_name, lead, members):
	if frappe.db.exists("Team", team_name):
		return team_name
	doc = frappe.get_doc({
		"doctype": "Team", "team_name": team_name, "team_lead": lead, "co_team_lead": members[0] if members else lead,
		"team_members": [{"employee": e, "designation": frappe.db.get_value("Employee", e, "designation")} for e in members],
	})
	doc.insert(ignore_permissions=True)
	return doc.name


def _contact(full_name, designation, email, party_type, party):
	first_name, _, last_name = full_name.partition(" ")
	name = frappe.db.get_value("Contact", {"email_id": email})
	if name:
		return name
	return frappe.get_doc({
		"doctype": "Contact", "first_name": first_name, "last_name": last_name, "designation": designation,
		"email_ids": [{"email_id": email, "is_primary": 1}],
		"links": [{"link_doctype": party_type, "link_name": party}],
	}).insert(ignore_permissions=True).name


def _supplier(supplier):
	if not frappe.db.exists("Supplier", supplier):
		frappe.get_doc({"doctype": "Supplier", "supplier_name": supplier, "supplier_type": "Company",
			"supplier_group": frappe.db.get_value("Supplier Group", {"is_group": 0}) or "All Supplier Groups"}).insert()
	return supplier


def _customer(customer, industry):
	if not frappe.db.exists("Customer", customer):
		frappe.get_doc({"doctype": "Customer", "customer_name": customer, "customer_type": "Company",
			"customer_group": frappe.db.get_value("Customer Group", {"is_group": 0}) or "All Customer Groups",
			"territory": frappe.db.get_value("Territory", {"is_group": 0}) or "All Territories",
			"industry": industry}).insert()
	return customer


def _implementation(customer, team, status, year, modules):
	name = f"DEMO {customer}"
	if frappe.db.exists("Implementation", name):
		return name
	doc = frappe.get_doc({
		"doctype": "Implementation", "customer": customer, "team": team, "status": status,
		"start_date": f"{year}-03-01", "modules": [{"module": m} for m in modules],
	})
	doc.name = name
	doc.insert(ignore_permissions=True, set_name=name)
	return doc.name
