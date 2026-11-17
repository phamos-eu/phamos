"""Shared fixtures for the Marketing tests (events, ticket item, guests)."""

from contextlib import contextmanager

import frappe
from frappe.utils import add_days, now_datetime

TICKET_ITEM = "TEST-EVENT-TICKET"
EVENT_TITLE = "Test ERPNext Event"


def ensure_company():
	"""The CI site is bare (`bench run-tests --app phamos` does not run ERPNext's own before_tests)."""
	from phamos.install import load_test_records

	load_test_records()
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


def ensure_vat_template():
	"""An Item Tax Template with 19 % on the company's first tax account (created once)."""
	name = frappe.db.get_value("Item Tax Template", {"title": "Test Ticket VAT 19"})
	if name:
		return name
	company = frappe.defaults.get_global_default("company")
	# The standard chart marks "Duties and Taxes" as Tax, but that account is a group.
	# Item Tax Template only accepts a leaf of type Tax, Chargeable, Income Account, or Expense Account.
	account = frappe.db.get_value(
		"Account",
		{
			"company": company,
			"is_group": 0,
			"account_type": ["in", ["Tax", "Chargeable", "Income Account", "Expense Account"]],
		},
	)
	return frappe.get_doc({"doctype": "Item Tax Template", "title": "Test Ticket VAT 19", "company": company,
		"taxes": [{"tax_type": account, "tax_rate": 19}]}).insert(ignore_permissions=True).name


def ensure_sales_taxes_template():
	"""A Sales Taxes and Charges Template with the VAT account at rate 0 (the German pattern: the Item Tax
	Template sets the rate per account)."""
	name = frappe.db.get_value("Sales Taxes and Charges Template", {"title": "Test Ticket Domestic"})
	if name:
		return name
	company = frappe.defaults.get_global_default("company")
	account = frappe.db.get_value("Item Tax Template Detail", {"parent": ensure_vat_template()}, "tax_type")
	return frappe.get_doc({"doctype": "Sales Taxes and Charges Template", "title": "Test Ticket Domestic", "company": company,
		"taxes": [{"charge_type": "On Net Total", "account_head": account, "rate": 0, "description": "VAT"}]}).insert(
		ignore_permissions=True).name


def make_event(title=EVENT_TITLE, paid=True, prices=None, **kwargs):
	"""Published, open event. ``prices``: rows for the Ticket Prices table (default one "Regular" at 119 gross)."""
	values = {
		"doctype": "Marketing Content", "title": title, "event_type": "Meetup", "status": "Upcoming",
		"starts_on": add_days(now_datetime(), 30), "ends_on": add_days(now_datetime(), 30),
		"published": 1, "registration_open": 1, "city": "Reutlingen", "location": "Test Venue",
		"organizer_is_phamos": 1,
	}
	if paid:
		values.update(ticket_item=make_ticket_item(), item_tax_template=ensure_vat_template(),
			taxes_and_charges=ensure_sales_taxes_template(), ticket_price_includes_tax=1,
			ticket_prices=prices or [{"title": "Regular", "rate": 119}])
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


CONTACT = {"full_name": "Erika Mustermann", "email": "erika@ticket.example"}
BILLING = {"full_name": "Erika Mustermann", "email": "erika@ticket.example", "address_line1": "Hauptstr. 1",
	"postcode": "72764", "city": "Reutlingen", "country": "Germany"}


@contextmanager
def as_guest():
	user = frappe.session.user
	frappe.set_user("Guest")
	try:
		yield
	finally:
		frappe.set_user(user)
