"""Events on the website: listing, event page, privacy, guest endpoints, go-live plan.

bench --site <site> run-tests --module phamos.tests.test_web_profile_events
"""

import json
from unittest.mock import patch

import frappe
from frappe.tests.utils import FrappeTestCase
from frappe.utils import add_days, get_html_for_route, now_datetime, set_request

from phamos.marketing import web
from phamos.tests.marketing_fixtures import ensure_company, make_event
from phamos.web_profile import golive
from phamos.web_profile.listing import search_texts
from phamos.web_profile.sections import build_profile, find_item, get_items

GROUP = "Events: Test Updates"
ALLOWED_DATA = {"starts_on", "ends_on", "date_note", "when", "upcoming", "cancelled", "location", "city", "map_url",
	"organizer", "key_person", "speakers", "sponsors", "offer", "has_newsletter", "terms", "languages", "ics"}
ATTENDEES = json.dumps([{"full_name": "Web Guest", "email": "web.guest@example.com"}])
BILLING = json.dumps({"full_name": "Web Guest", "email": "web.guest@example.com", "address_line1": "Weg 1",
	"postcode": "72764", "city": "Reutlingen", "country": "Germany"})
CONSENTS = json.dumps({"terms": 1, "privacy": 1})


def reset_items():
	frappe.local.web_profile_items = None
	frappe.cache.delete_value("web_profile_items")


class TestWebProfileEvents(FrappeTestCase):
	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		frappe.set_user("Administrator")
		frappe.local.lang = "en"
		ensure_company()
		if not frappe.db.exists("Email Group", GROUP):
			frappe.get_doc({"doctype": "Email Group", "title": GROUP}).insert(ignore_permissions=True)

	def setUp(self):
		frappe.set_user("Administrator")
		frappe.db.savepoint("events_web_test")
		self.event = make_event("Web Test Event", email_group=GROUP, organizer_email="hidden-organizer@example.com",
			contact_person_email="hidden-contact@example.com", subtitle="A test", max_attendees=20,
			translations=[{"language": "en", "title": "Web Test Event", "summary": "English summary"}],
			speakers=[{"published": 1, "full_name": "Speaker Searchable", "topic": "<p>Keynote</p>"}])
		self.past = make_event("Web Past Event", paid=False, starts_on=add_days(now_datetime(), -40),
			ends_on=add_days(now_datetime(), -40))
		self.hidden = make_event("Web Hidden Event", published=0)
		reset_items()

	def tearDown(self):
		frappe.set_user("Administrator")
		frappe.db.rollback(save_point="events_web_test")
		reset_items()

	def item(self, event=None, lang="en"):
		return find_item("events", (event or self.event).route, lang)

	def test_route_is_a_slug_of_the_title(self):
		self.assertEqual(self.event.route, "web-test-event")
		again = make_event("Web Test Event 2")
		self.assertEqual(again.route, "web-test-event-2")

	def test_only_published_events_are_listed(self):
		names = {i.name for i in get_items("events", "en")}
		self.assertIn(self.event.name, names)
		self.assertIn(self.past.name, names)
		self.assertNotIn(self.hidden.name, names)

	def test_item_data_is_an_allow_list(self):
		item = self.item()
		self.assertEqual(set(item.data) - ALLOWED_DATA, set())
		dump = json.dumps(item, default=str)
		for secret in ("hidden-organizer@example.com", "hidden-contact@example.com", GROUP):
			self.assertNotIn(secret, dump)

	def test_upcoming_and_past_and_sort(self):
		self.assertEqual(self.item().facets["when"], ["upcoming", "all"])
		self.assertEqual(self.item(self.past).facets["when"], ["past", "all"])
		self.assertLess(self.item().sort["date"], self.item(self.past).sort["date"])

	def test_german_page_falls_back_to_the_english_text(self):
		item = self.item(lang="de")
		self.assertEqual(item.summary, "English summary")
		self.assertTrue(build_profile(item, "de")["notice"])
		self.assertIsNone(build_profile(self.item(), "en")["notice"])

	def test_event_page_has_one_ticket_action_and_event_schema(self):
		profile = build_profile(self.item(), "en")
		primary = [a for a in profile["actions"] if a.get("primary")]
		self.assertEqual(len(primary), 1)
		self.assertEqual(primary[0]["dialog"], "tickets")
		self.assertEqual(profile["schema"]["@type"], "Event")
		self.assertIn("offers", profile["schema"])
		self.assertTrue(profile["ticket"])

	def test_closed_sale_has_no_ticket_action(self):
		self.event.registration_open = 0
		self.event.save()
		reset_items()
		profile = build_profile(self.item(), "en")
		self.assertFalse([a for a in profile["actions"] if a.get("primary")])
		self.assertIsNone(profile["ticket"])

	def test_speakers_are_searchable(self):
		self.assertIn("speaker searchable", search_texts("events", "en")[self.event.name])

	def test_pages_render_and_unpublished_is_not_found(self):
		frappe.set_user("Guest")
		html = get_html_for_route(f"/en/events/{self.event.route}")
		self.assertIn("wp-ticket-dialog", html)
		self.assertNotIn("hidden-organizer@example.com", html)
		self.assertNotIn(GROUP, html)
		listing = get_html_for_route("/de/veranstaltungen")
		self.assertIn(self.event.route, listing)
		self.assertNotIn(self.past.route, listing)  # past events only with ?when=past / all
		missing = get_html_for_route(f"/en/events/{self.hidden.route}")
		self.assertNotIn("wp-ticket-dialog", missing)
		self.assertIn("is_404 = true", missing)

	# --- guest endpoints ---------------------------------------------------------------------------------

	def order(self, **kwargs):
		args = dict(event=self.event.route, lang="en", attendees=ATTENDEES, qty=1, billing=BILLING, consents=CONSENTS)
		args.update(kwargs)
		frappe.set_user("Guest")
		try:
			return web.order_tickets(**args)
		finally:
			frappe.set_user("Administrator")

	@patch("phamos.marketing.web.ticketing.register_attendees", return_value={"reference": "QTN-1", "reference_doctype": "Quotation"})
	def test_order_validation(self, register):
		self.assertEqual(self.order(website="bot")["ok"], True)
		register.assert_not_called()
		for bad in (dict(consents=json.dumps({"terms": 1})), dict(qty=2),
				dict(attendees=json.dumps([{"full_name": "X Y", "email": "bad@example.com/"}])),
				dict(attendees=json.dumps([{"full_name": "A A", "email": "a@example.com"}, {"full_name": "B B", "email": "a@example.com"}]), qty=2),
				dict(billing=None), dict(billing=json.dumps({**json.loads(BILLING), "is_company": 1})),
				dict(event=self.hidden.route)):
			self.assertRaises(frappe.ValidationError, self.order, **bad)
		register.assert_not_called()
		result = self.order()
		self.assertEqual(result["reference"], "QTN-1")
		args = register.call_args
		self.assertEqual(args.args[0], self.event.name)
		self.assertEqual(args.kwargs["billing_data"]["country"], "Germany")

	def test_order_end_to_end_as_guest(self):
		with patch("frappe.enqueue"):
			result = self.order()
		self.assertEqual(result["reference_doctype"], "Quotation")
		self.assertEqual(frappe.db.get_value("Quotation", result["reference"], "docstatus"), 1)
		self.assertEqual(frappe.db.get_value("Attendee", {"email": "web.guest@example.com"}, "event"), self.event.name)

	def test_closed_sale_is_refused(self):
		self.event.registration_open = 0
		self.event.save()
		reset_items()
		self.assertRaises(frappe.ValidationError, self.order)

	def test_rate_limit(self):
		cmd = "phamos.marketing.web.order_tickets"
		set_request(method="POST", path=f"/api/method/{cmd}")
		frappe.local.request_ip = "203.0.113.7"
		key = frappe.cache.make_key(f"rl:{cmd}:203.0.113.7")
		frappe.cache.delete(key)
		frappe.set_user("Guest")  # set_user clears form_dict: set the command afterwards
		frappe.form_dict.cmd = cmd
		try:
			for _i in range(5):
				web.order_tickets(self.event.route, "en", ATTENDEES, website="bot")
			self.assertRaises(frappe.RateLimitExceededError, web.order_tickets, self.event.route, "en", ATTENDEES,
				website="bot")
		finally:
			frappe.cache.delete(key)
			frappe.local.request = None
			frappe.set_user("Administrator")

	@patch("frappe.sendmail")
	def test_subscribe_is_double_opt_in(self, sendmail):
		frappe.set_user("Guest")
		try:
			self.assertRaises(frappe.ValidationError, web.subscribe, self.event.route, "en", "fan@example.com")
			result = web.subscribe(self.event.route, "en", "fan@example.com", privacy_consent=1)
		finally:
			frappe.set_user("Administrator")
		self.assertEqual(result["status"], "confirmation_sent")
		sendmail.assert_called_once()
		self.assertIn("confirm_subscription", json.dumps(sendmail.call_args.kwargs, default=str))
		self.assertFalse(frappe.db.exists("Email Group Member", {"email_group": GROUP, "email": "fan@example.com"}))
		frappe.get_doc({"doctype": "Email Group Member", "email_group": GROUP, "email": "fan@example.com"}).insert(
			ignore_permissions=True)
		self.assertEqual(web.subscribe(self.event.route, "en", "fan@example.com", privacy_consent=1)["status"], "already")

	def test_ics(self):
		web.ics(self.event.route, "en")
		self.assertEqual(frappe.response["type"], "download")
		content = frappe.response["filecontent"].decode()
		for part in ("BEGIN:VEVENT", "METHOD:PUBLISH", "SUMMARY:Web Test Event", "DTSTART;TZID=", "URL:"):
			self.assertIn(part, content)
		self.assertRaises(frappe.DoesNotExistError, web.ics, self.hidden.route, "en")

	def test_golive_plan_redirects_old_urls(self):
		frappe.db.set_value("Marketing Content", self.event.name, "legacy_route", "events/web-test-event-old")
		plan = dict(golive.get_plan("events")["redirects"])
		self.assertEqual(plan["events"], "/de/veranstaltungen")
		self.assertEqual(plan["events/web-test-event-old"], f"/de/veranstaltungen/{self.event.route}")
		self.assertEqual(plan["event-registration"], "/de/veranstaltungen")
		self.assertEqual(plan[f"events/{self.hidden.route}"], "/de/veranstaltungen")
