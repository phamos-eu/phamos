# Copyright (c) 2026, phamos.eu and contributors
# For license information, please see license.txt

"""Marketing Content: anything phamos releases with a date. Events are shown on the website.

The public pages (/de/veranstaltungen, /en/events) are rendered by the Web Profile engine
(``phamos.web_profile.events``); this record is the public record itself, so nothing is mirrored.
Texts per language live in the "Web Profile Content" table, the URL slug is set once from the title.
"""

import frappe
from frappe import _
from frappe.utils import flt, get_url

from phamos.web_profile.document import WebProfileDocument

CONFIRMATION_TEMPLATE = "Event Subscription Confirmation"


class MarketingContent(WebProfileDocument):
	def validate(self):
		# No refresh_mirrored_fields (WebProfileDocument.validate): there is no source record to mirror.
		self.validate_dates()
		self.validate_location()
		self.validate_tickets()
		self.validate_translations()
		self.set_route()

	def validate_dates(self):
		if not self.starts_on and not self.date_note:
			frappe.throw(_("Please set either a confirmed Start Date or a Date Note (e.g. 'Expected: July 2026')."))
		if self.starts_on and self.date_note:
			frappe.throw(_("Set either a confirmed Start Date or a Date Note, not both."))
		if self.starts_on and self.ends_on and self.ends_on < self.starts_on:
			frappe.throw(_("The event cannot end before it starts."))

	def validate_location(self):
		"""Online: ``location`` is the meeting link, there is no address. In person: ``location`` is the venue,
		the pin comes from the address unless one is set (phamos/phamos#1665)."""
		from phamos.marketing import location

		self.attendance_mode = self.attendance_mode or location.IN_PERSON
		self.location = (self.location or "").strip() or None
		if location.is_online(self):
			if not location.is_https_url(self.location):
				frappe.throw(_("For an online event, enter the meeting link in Venue / Video Link. It must start with https://."))
			for field in (*location.ADDRESS_FIELDS, "geolocation", "latitude", "longitude"):
				self.set(field, None)
			if self.published and not (self.registration_open or self.ticket_item):
				frappe.msgprint(_("The video link is never shown on the website, only sent to registered attendees. "
					"Open the registration so people can get it."), indicator="orange", alert=True)
			return

		if location.looks_like_url(self.location):
			frappe.throw(_("Venue / Video Link holds a link. For an online event, set Attendance to Online."))
		if not self.country and any(self.get(f) for f in ("street", "postal_code", "city")):
			self.country = frappe.db.get_default("country")
		if not self.geolocation:
			# Only with a street: a lookup of the city alone would pin the town centre, and a set pin is never
			# moved again. Never during imports, patches or migrate: one request per second would stall them.
			if self.street and not (frappe.flags.in_import or frappe.flags.in_patch or frappe.flags.in_migrate):
				found = location.geocode(self.street, self.postal_code, self.city, self.country)
				if found:
					self.geolocation = location.point(found["latitude"], found["longitude"])
		elif not self.is_new() and not self.has_value_changed("geolocation") and any(
				self.has_value_changed(f) for f in location.ADDRESS_FIELDS):
			frappe.msgprint(_("The address changed but the map pin did not. Use Find on Map to move the pin."),
				indicator="orange", alert=True)
		self.latitude, self.longitude = location.coordinates(self.geolocation)

	def validate_tickets(self):
		"""Prices live on the event (Ticket Prices table); a ticket sale needs a date (no right of withdrawal
		for leisure events on a specific date, § 312g (2) no. 9 BGB) and at least one price."""
		from phamos.marketing.billing import price_summary

		if self.organizer_is_phamos:
			self.organizer = None
		titles = [row.title.strip() for row in self.ticket_prices or []]
		if len(set(titles)) != len(titles):
			frappe.throw(_("Every ticket price needs its own title."))
		for row in self.ticket_prices or []:
			row.title = row.title.strip()
			if flt(row.rate) <= 0:
				frappe.throw(_("Row {0}: the ticket price must be greater than 0.").format(row.idx))
			if row.valid_from and row.valid_until and row.valid_until < row.valid_from:
				frappe.throw(_("Row {0}: the price ends before it starts.").format(row.idx))
		if self.ticket_item:
			if not self.ticket_prices:
				frappe.throw(_("Please add at least one ticket price (Tickets & Sales tab)."))
			if self.registration_open and not self.starts_on:
				frappe.throw(_("Tickets can only be sold for events with a start date."))
			if self.registration_open and not self.item_tax_template:
				# The rate shown on the page and the tax on the order both come from it (phamos/phamos#1710).
				frappe.throw(_("Please choose the Item Tax Template for the tickets before opening ticket sales."))
			self.validate_tax_company()
		self.ticket_price_summary = price_summary(self) if self.ticket_item else None

	def validate_tax_company(self):
		from phamos.marketing.billing import default_company

		company = default_company()
		for doctype, name in (("Item Tax Template", self.item_tax_template),
				("Sales Taxes and Charges Template", self.taxes_and_charges)):
			if name and frappe.db.get_value(doctype, name, "company") != company:
				frappe.throw(_("{0} {1} belongs to another company than {2}.").format(_(doctype), name, company))

	def on_update(self):
		super().on_update()
		self.prepare_email_group()

	def prepare_email_group(self):
		"""Double opt-in of "Keep me posted": the group's confirmation mail and the page visitors return to.

		``add_query_parameters`` stays off: it would append the visitor's email address to that URL.
		"""
		if not self.email_group or not self.route:
			return
		group = frappe.db.get_value("Email Group", self.email_group,
			["confirmation_email_template", "welcome_url", "add_query_parameters"], as_dict=True)
		if not group:
			return
		values = {}
		if not group.confirmation_email_template and frappe.db.exists("Email Template", CONFIRMATION_TEMPLATE):
			values["confirmation_email_template"] = CONFIRMATION_TEMPLATE
		url = subscription_confirmed_url(self.route)
		# Empty, or the old "event page ?subscribed=1" target: the confirmation page explains what happened.
		if not group.welcome_url or group.welcome_url.endswith("?subscribed=1"):
			values["welcome_url"] = url
		if group.add_query_parameters:
			values["add_query_parameters"] = 0
		if values:
			frappe.db.set_value("Email Group", self.email_group, values)


def subscription_confirmed_url(route, lang="de"):
	from urllib.parse import urlencode

	from phamos.hooks import SUBSCRIPTION_CONFIRMED_ROUTES

	return get_url(f"/{SUBSCRIPTION_CONFIRMED_ROUTES[lang]}?{urlencode({'event': route})}")


@frappe.whitelist()
def create_newsletter_for_event(event_name):
	doc = frappe.get_doc("Marketing Content", event_name)
	doc.check_permission("read")
	if not doc.email_group:
		frappe.throw(_("Please set an Email Group on this Marketing Content before creating a Newsletter."))
	user_info = frappe.db.get_value("User", frappe.session.user, ["full_name", "email"], as_dict=True)
	base_name = f"{frappe.utils.now_datetime().strftime('%Y-%m')}-{frappe.scrub(doc.title).replace('_', '-')}"
	newsletter_name, counter = base_name, 2
	while frappe.db.exists("Newsletter", newsletter_name):
		newsletter_name = f"{base_name}-{counter}"
		counter += 1
	newsletter = frappe.new_doc("Newsletter")
	newsletter.subject = doc.title
	newsletter.sender_name = user_info.full_name or frappe.session.user
	newsletter.sender_email = user_info.email
	newsletter.custom_marketing_content = doc.name
	newsletter.append("email_group", {"email_group": doc.email_group})
	newsletter.insert(set_name=newsletter_name)
	return newsletter.name
