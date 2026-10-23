# Copyright (c) 2026, phamos.eu and contributors
# Local seed for trying the Implementation Cockpit (#1671) as an internal and as a customer user.
# Run: bench --site dev.localhost execute phamos.scripts.seed_implementation_cockpit_playground.run
# Safe to run again; it only touches records whose names start with SEED_TAG.
#
# The customer user has no password: open the User in Desk as Administrator and use
# "Impersonate" to see the cockpit as that customer.

import frappe
from frappe.utils import add_days, today

SEED_TAG = "IC-SEED"
CUSTOMER_USER = "ic-seed-customer@example.com"

CUSTOMERS = [
	{
		"customer_name": f"{SEED_TAG} Nordwind Logistik GmbH",
		"shared_with_user": True,
		"implementations": [
			{
				"name": f"{SEED_TAG} ERPNext Core System",
				"maturity_level": "4 - Go Live Phase. Go Live, first modules in use with real life data",
				"trend": "Improving",
				"review_cadence": "Weekly",
				"status": "Escalated",  # shows as "Active" to the customer
				"forecast": "5 ⛈️ - Kunde zahlt Rechnungen nicht, Kunde hat keine Gedult",  # must never show
				"notes": "<p>Internal note: must never reach the cockpit.</p>",
				"status_statement": (
					"Warehouse go-live is confirmed for 15 November. Scanner fixes are in testing on the "
					"test system. We need your sign-off on the pick list layout by 6 November."
				),
			},
			{
				"name": f"{SEED_TAG} Webshop Integration",
				"maturity_level": "2 - Initial Development Phase. Initial development work, Power user can navigate system",
				"trend": "Stable",
				"review_cadence": "Biweekly",
				"status_statement": "Shopware order import is in development; first test orders expected next week.",
			},
			{
				# Same customer, not shared on the portal: the customer user must not see it.
				"name": f"{SEED_TAG} Internal Only Pilot",
				"maturity_level": "1 - Inception Phase. Early Implementation, no previous Frappe experience",
				"show_on_customer_portal": 0,
			},
		],
	},
	{
		"customer_name": f"{SEED_TAG} Bäckerei Sommer KG",
		"shared_with_user": False,
		"implementations": [
			{
				"name": f"{SEED_TAG} ERPNext Bakery",
				"maturity_level": "5 - Live Development Phase. Ongoing development in parallel to system in daily use with live data",
				"trend": "Stable",
				"review_cadence": "Monthly",
				"status_statement": "Recipe costing is live; next up is the delivery tour planning.",
			}
		],
	},
]


def run():
	manager = _pick_manager()
	contact = _ensure_customer_user()
	for spec in CUSTOMERS:
		customer = _ensure_customer(spec["customer_name"])
		if spec["shared_with_user"]:
			_link_contact(contact, customer)
		for impl in spec["implementations"]:
			_ensure_implementation(impl, customer, manager, contact if spec["shared_with_user"] else None)
	frappe.db.commit()
	print(f"Seeded. Customer user: {CUSTOMER_USER} (use Impersonate on the User in Desk).")
	print("Open http://dev.localhost:8000/implementation-cockpit")


def _pick_manager():
	"""Any enabled System User other than Administrator, so the contact card shows a person."""
	users = frappe.get_all(
		"User",
		filters={"user_type": "System User", "enabled": 1, "name": ["not in", ["Administrator", "Guest"]]},
		pluck="name",
		order_by="creation asc",
		limit=1,
	)
	return users[0] if users else "Administrator"


def _ensure_customer(customer_name):
	if not frappe.db.exists("Customer", customer_name):
		frappe.get_doc(
			{
				"doctype": "Customer",
				"customer_name": customer_name,
				"customer_type": "Company",
				"customer_group": frappe.db.get_value("Customer Group", {"is_group": 0}, "name"),
				"territory": frappe.db.get_value("Territory", {"is_group": 0}, "name"),
			}
		).insert(ignore_permissions=True)
	return frappe.db.get_value("Customer", {"customer_name": customer_name}, "name")


def _ensure_customer_user():
	if not frappe.db.exists("User", CUSTOMER_USER):
		frappe.get_doc(
			{
				"doctype": "User",
				"email": CUSTOMER_USER,
				"first_name": "Julia",
				"last_name": f"Brandt ({SEED_TAG})",
				"user_type": "Website User",
				"send_welcome_email": 0,
			}
		).insert(ignore_permissions=True)
	contact = frappe.db.get_value("Contact", {"user": CUSTOMER_USER}, "name")
	if contact:
		return contact
	return (
		frappe.get_doc(
			{
				"doctype": "Contact",
				"first_name": "Julia",
				"last_name": f"Brandt ({SEED_TAG})",
				"user": CUSTOMER_USER,
				"email_ids": [{"email_id": CUSTOMER_USER, "is_primary": 1}],
			}
		)
		.insert(ignore_permissions=True)
		.name
	)


def _link_contact(contact, customer):
	doc = frappe.get_doc("Contact", contact)
	if not any(l.link_doctype == "Customer" and l.link_name == customer for l in doc.links):
		doc.append("links", {"link_doctype": "Customer", "link_name": customer})
		doc.save(ignore_permissions=True)


def _ensure_implementation(spec, customer, manager, contact):
	values = {
		"customer": customer,
		"status": spec.get("status", "Open"),
		"maturity_level": spec.get("maturity_level"),
		"trend": spec.get("trend"),
		"review_cadence": spec.get("review_cadence"),
		"next_review_due": add_days(today(), 4) if spec.get("review_cadence") else None,
		"status_statement": spec.get("status_statement"),
		"forecast": spec.get("forecast"),
		"notes": spec.get("notes"),
		"show_on_customer_portal": spec.get("show_on_customer_portal", 1),
		"account_manager": manager,
		"start_date": add_days(today(), -400),
	}
	if frappe.db.exists("Implementation", spec["name"]):
		frappe.db.set_value("Implementation", spec["name"], values)
	else:
		# db_insert skips Implementation.before_save (financial snapshot, chapters), which the
		# seed does not need and which expects Sales Orders and Timesheets to exist.
		frappe.get_doc({"doctype": "Implementation", "name": spec["name"], **values}).db_insert()

	frappe.db.delete("Implementation Stakeholder", {"parent": spec["name"], "email": CUSTOMER_USER})
	if contact:
		frappe.get_doc(
			{
				"doctype": "Implementation Stakeholder",
				"parent": spec["name"],
				"parenttype": "Implementation",
				"parentfield": "stakeholders",
				"idx": 1,
				"contact": contact,
				"full_name": f"Julia Brandt ({SEED_TAG})",
				"email": CUSTOMER_USER,
				"stakeholder_organisation": "Customer",
				"stakeholder_type": "Sponsor",
			}
		).db_insert()
