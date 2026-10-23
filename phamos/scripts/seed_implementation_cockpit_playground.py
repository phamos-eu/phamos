# Copyright (c) 2026, phamos.eu and contributors
# Local seed for trying the Implementation Cockpit (#1671) as an internal and as a customer user.
# Run: bench --site dev.localhost execute phamos.scripts.seed_implementation_cockpit_playground.run
# Safe to run again; it only touches records whose names start with SEED_TAG.
#
# The customer user has no password: open the User in Desk as Administrator and use
# "Impersonate" to see the cockpit as that customer.

import random
import zlib

import frappe
from frappe.utils import add_days, getdate, today

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
			_ensure_timesheets(impl["name"], customer)
			_ensure_sales_orders(impl["name"], customer)
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
		"links": LINKS_HTML,
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


ACTIVITIES = ["Development", "Testing", "Meeting", "Support", "Documentation"]
BILLING = ["Billed", "Billed", "Not Billed", "In Question"]
WORK = [
	"#1702 Pick list prints the wrong bin location",
	"#1688 Scanner skips serial numbers on goods receipt",
	"#1695 DATEV export: cost centre per line",
	"Weekly meeting with the customer team",
	"#1709 Monthly sales report per region",
	"Support: user could not post a stock entry",
]


def _ensure_timesheets(implementation, customer):
	"""One Project per seeded Implementation and about 30 Timesheets over the last 6 months.

	Inserted with db_insert (no costing or validation), so no Activity Cost or salary setup is
	needed; the cockpit only reads the header fields and the first time log.
	"""
	project = f"{implementation} Project"
	if not frappe.db.exists("Project", project):
		frappe.get_doc(
			{
				"doctype": "Project",
				"name": project,
				"project_name": project,
				"customer": customer,
				"custom_implementation": implementation,
				"status": "Open",
				"company": frappe.db.get_single_value("Global Defaults", "default_company"),
			}
		).db_insert()

	for name in frappe.get_all("Timesheet", filters={"parent_project": project, "name": ["like", f"{SEED_TAG}%"]}, pluck="name"):
		frappe.db.delete("Timesheet Detail", {"parent": name})
		frappe.db.delete("Timesheet", name)

	employees = frappe.get_all("Employee", filters={"status": "Active"}, fields=["name", "employee_name"], limit=4)
	if not employees:
		return
	rng = random.Random(implementation)  # same data on every run
	start = getdate(add_days(today(), -180))
	for i in range(30):
		day = add_days(start, rng.randint(0, 178))
		hours = rng.choice([1, 2, 2.5, 3, 4, 6, 8])
		billable = hours if rng.random() > 0.3 else round(hours * rng.choice([0, 0.5]), 2)
		employee = rng.choice(employees)
		name = f"{SEED_TAG} TS-{zlib.crc32(implementation.encode()) % 1000:03d}-{i + 1:02d}"
		rated = i in (3, 11)
		frappe.get_doc(
			{
				"doctype": "Timesheet",
				"name": name,
				"customer": customer,
				"parent_project": project,
				"project_name": project,
				"custom_implementation": implementation,
				"employee": employee.name,
				"employee_name": employee.employee_name,
				"start_date": day,
				"end_date": day,
				"total_hours": hours,
				"total_billable_hours": billable,
				"custom_billing_status": rng.choice(BILLING),
				"custom_rating": 2 if rated else 0,
				"customer_comment": "Please check, this looks like two hours too many." if rated else None,
				"docstatus": 0,
			}
		).db_insert()
		frappe.get_doc(
			{
				"doctype": "Timesheet Detail",
				"parent": name,
				"parenttype": "Timesheet",
				"parentfield": "time_logs",
				"idx": 1,
				"activity_type": rng.choice(ACTIVITIES),
				"description": rng.choice(WORK),
				"hours": hours,
				"billing_hours": billable,
				"is_billable": 1 if billable else 0,
				"project": project,
				"custom_implementation": implementation,
			}
		).db_insert()


LINKS_HTML = (
	"<p><strong>Systems</strong></p><ul>"
	'<li><a href="https://example.com/production">Production system</a></li>'
	'<li><a href="https://example.com/test">Test system – try fixes here first</a></li></ul>'
	"<p><strong>Documentation and code</strong></p><ul>"
	'<li><a href="https://example.com/docs">Handbook and how-tos</a></li>'
	'<li><a href="https://example.com/gitlab">GitLab board of this implementation</a></li></ul>'
)

SALES_ORDERS = [
	# (hours, delivered, status, months ago)
	(120, 120, "Completed", 10),
	(200, 86, "To Deliver and Bill", 4),
	(40, 0, "To Deliver and Bill", 1),
]


def _ensure_sales_orders(implementation, customer):
	"""Submitted Sales Orders with delivered hours, inserted without validation (no Item setup)."""
	from frappe.utils import add_months

	tag = zlib.crc32(implementation.encode()) % 1000
	for i, (hours, delivered, status, months_ago) in enumerate(SALES_ORDERS, start=1):
		name = f"{SEED_TAG} SO-{tag:03d}-{i}"
		frappe.db.delete("Sales Order Item", {"parent": name})
		frappe.db.delete("Sales Order", name)
		ordered = add_months(today(), -months_ago)
		frappe.get_doc(
			{
				"doctype": "Sales Order",
				"name": name,
				"customer": customer,
				"customer_name": customer,
				"custom_implementation": implementation,
				"company": frappe.db.get_single_value("Global Defaults", "default_company"),
				"transaction_date": ordered,
				"delivery_date": add_months(ordered, 3),
				"status": status,
				"total_qty": hours,
				"per_delivered": round(delivered / hours * 100, 2),
				"docstatus": 1,
			}
		).db_insert()
		frappe.get_doc(
			{
				"doctype": "Sales Order Item",
				"parent": name,
				"parenttype": "Sales Order",
				"parentfield": "items",
				"idx": 1,
				"item_code": "Consulting",
				"item_name": "Consulting hours",
				"qty": hours,
				"delivered_qty": delivered,
				"uom": "Hour",
			}
		).db_insert()
