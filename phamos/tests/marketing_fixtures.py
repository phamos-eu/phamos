"""Shared fixtures for the Marketing tests (events, ticket item, guests)."""

from contextlib import contextmanager

import frappe
from frappe.utils import add_days, now_datetime

TICKET_ITEM = "TEST-EVENT-TICKET"
EVENT_TITLE = "Test ERPNext Event"


def ensure_company():
	"""The CI site is bare (`--app phamos` never runs ERPNext's setup wizard): run it once."""
	if not frappe.db.a_row_exists("Company"):
		from erpnext.setup.utils import before_tests

		before_tests()
	company = frappe.defaults.get_global_default("company") or frappe.get_all("Company", pluck="name", limit=1)[0]
	frappe.defaults.set_global_default("company", company)
	for field, doctype in (("customer_group", "Customer Group"), ("territory", "Territory")):
		current = frappe.db.get_single_value("Selling Settings", field)
		if not current or frappe.db.get_value(doctype, current, "is_group"):
			frappe.db.set_single_value("Selling Settings", field, frappe.db.get_value(doctype, {"is_group": 0}))
	frappe.db.set_default("customer_group", frappe.db.get_single_value("Selling Settings", "customer_group"))
	frappe.db.set_default("territory", frappe.db.get_single_value("Selling Settings", "territory"))
	return company


def make_ticket_item(rate=100):
	if not frappe.db.exists("Item", TICKET_ITEM):
		frappe.get_doc({"doctype": "Item", "item_code": TICKET_ITEM, "item_name": "Event Ticket",
			"item_group": frappe.db.get_value("Item Group", {"is_group": 0}) or "All Item Groups",
			"stock_uom": "Nos", "is_stock_item": 0, "include_item_in_manufacturing": 0}).insert(ignore_permissions=True)
	price_list = frappe.db.get_single_value("Selling Settings", "selling_price_list") or "Standard Selling"
	if not frappe.db.exists("Price List", price_list):
		frappe.get_doc({"doctype": "Price List", "price_list_name": price_list, "selling": 1,
			"currency": "EUR"}).insert(ignore_permissions=True)
	if not frappe.db.exists("Item Price", {"item_code": TICKET_ITEM, "price_list": price_list}):
		frappe.get_doc({"doctype": "Item Price", "item_code": TICKET_ITEM, "price_list": price_list,
			"price_list_rate": rate}).insert(ignore_permissions=True)
	return TICKET_ITEM


def make_event(title=EVENT_TITLE, paid=True, **kwargs):
	values = {
		"doctype": "Marketing Content", "title": title, "event_type": "Meetup", "status": "Upcoming",
		"starts_on": add_days(now_datetime(), 30), "ends_on": add_days(now_datetime(), 30),
		"published": 1, "registration_open": 1, "city": "Reutlingen", "location": "Test Venue",
		"ticket_item": make_ticket_item() if paid else None,
	}
	values.update(kwargs)
	name = frappe.db.get_value("Marketing Content", {"title": values["title"]})
	if name:
		frappe.delete_doc("Marketing Content", name, force=True, ignore_permissions=True)
	return frappe.get_doc(values).insert(ignore_permissions=True)


def make_attendee(event, email, first_name="Test", last_name="Person", **kwargs):
	return frappe.get_doc({"doctype": "Attendee", "event": event, "email": email, "first_name": first_name,
		"last_name": last_name, **kwargs}).insert(ignore_permissions=True)


def make_customer(name, email=None):
	if not frappe.db.exists("Customer", name):
		frappe.get_doc({"doctype": "Customer", "customer_name": name, "customer_type": "Company",
			"customer_group": frappe.db.get_single_value("Selling Settings", "customer_group"),
			"territory": frappe.db.get_single_value("Selling Settings", "territory")}).insert(ignore_permissions=True)
	if email:
		contact = frappe.new_doc("Contact")
		contact.first_name = "Existing"
		contact.append("email_ids", {"email_id": email, "is_primary": 1})
		contact.append("links", {"link_doctype": "Customer", "link_name": name})
		contact.insert(ignore_permissions=True)
	return name


CONSENTS = {"terms": 1, "privacy": 1}


@contextmanager
def as_guest():
	user = frappe.session.user
	frappe.set_user("Guest")
	try:
		yield
	finally:
		frappe.set_user(user)
