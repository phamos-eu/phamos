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
ALLOWED_DATA = {"starts_on", "ends_on", "date_note", "when", "upcoming", "cancelled", "online", "location", "street",
	"postal_code", "city", "country", "latitude", "longitude",
	"organizer", "stakeholders", "key_person", "speakers", "sponsors", "offer", "interest", "has_newsletter", "terms",
	"languages", "ics"}
CONTACT = json.dumps({"full_name": "Web Guest", "email": "web.guest@example.com"})
COMPANIONS = json.dumps([{"full_name": "Plus One", "email": ""}])
BILLING = json.dumps({"full_name": "Web Guest", "email": "web.guest@example.com", "address_line1": "Weg 1",
	"postcode": "72764", "city": "Reutlingen", "country": "Germany"})
VOTER_A = "voter-aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa"
VOTER_B = "voter-bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb"


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
		frappe.local.request = None  # page renders leave a request behind, which switches rate limits on
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
		frappe.cache.delete_keys("event_interest:")  # the voters' answers live in Redis, not in the rollback
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
		args = dict(event=self.event.route, lang="en", contact=CONTACT, attends=1, companions=COMPANIONS, billing=BILLING)
		args.update(kwargs)
		frappe.set_user("Guest")
		try:
			return web.order_tickets(**args)
		finally:
			frappe.set_user("Administrator")

	@patch("phamos.marketing.web.ticketing.register_attendees", return_value={"reference": "SO-1",
		"reference_doctype": "Sales Order", "tickets_to": "web.guest@example.com", "consent_token": "t"})
	def test_order_validation(self, register):
		self.assertEqual(self.order(website="bot")["ok"], True)
		register.assert_not_called()
		for bad in (dict(contact=json.dumps({"full_name": "No Mail"})),
				dict(contact=json.dumps({"full_name": "X Y", "email": "bad@example.com/"})),
				dict(companions=json.dumps([{"full_name": "B", "email": ""}])),
				dict(companions=json.dumps([{"full_name": "Bad Mail", "email": "nope"}])),
				dict(attends=0, companions="[]"),
				dict(billing=None), dict(billing=json.dumps({**json.loads(BILLING), "is_company": 1})),
				dict(billing=json.dumps({**json.loads(BILLING), "country": "Atlantis"})),
				dict(event=self.hidden.route)):
			self.assertRaises(frappe.ValidationError, self.order, **bad)
		register.assert_not_called()
		result = self.order(expected_total="238.00")
		self.assertEqual((result["reference"], result["tickets_to"], result["token"]), ("SO-1", "web.guest@example.com", "t"))
		args = register.call_args
		self.assertEqual(args.args[0], self.event.name)
		self.assertEqual(args.kwargs["companions"], [{"full_name": "Plus One", "email": "", "phone": ""}])
		self.assertEqual(args.kwargs["billing_data"]["country"], "Germany")
		self.assertEqual(args.kwargs["expected_total"], "238.00")

	def test_order_end_to_end_as_guest(self):
		with patch("frappe.enqueue"):
			result = self.order(expected_total="238.00")
		self.assertEqual(result["reference_doctype"], "Sales Order")
		self.assertEqual(frappe.db.get_value("Sales Order", result["reference"], "docstatus"), 1)
		self.assertEqual(frappe.db.get_value("Attendee", {"email": "web.guest@example.com"}, "event"), self.event.name)
		self.assertEqual(frappe.db.count("Attendee", {"event": self.event.name, "order_reference": result["reference"]}), 2)

		# The optional questions afterwards, signed with the returned token.
		frappe.set_user("Guest")
		try:
			with patch("frappe.sendmail") as sendmail:
				saved = web.save_consents(self.event.route, "en", result["reference"], result["token"],
					json.dumps({"newsletter": 1, "attendee_contact": 1}))
			self.assertEqual(saved["status"], "confirmation_sent")
			sendmail.assert_called_once()
			self.assertRaises(frappe.PermissionError, web.save_consents, self.event.route, "en", result["reference"],
				"1.forged", json.dumps({"newsletter": 1}))
		finally:
			frappe.set_user("Administrator")
		buyer = frappe.get_all("Attendee", filters={"order_reference": result["reference"], "is_buyer": 1},
			fields=["newsletter_consent", "share_with_attendees_consent", "public_listing_consent"])[0]
		self.assertEqual((buyer.newsletter_consent, buyer.share_with_attendees_consent, buyer.public_listing_consent), (1, 1, 0))

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
				web.order_tickets(self.event.route, "en", CONTACT, website="bot")
			self.assertRaises(frappe.RateLimitExceededError, web.order_tickets, self.event.route, "en", CONTACT,
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
		# A member gets the same answer as a new address, and no mail (phamos/phamos#1702).
		sendmail.reset_mock()
		self.assertEqual(web.subscribe(self.event.route, "en", "fan@example.com", privacy_consent=1), result)
		sendmail.assert_not_called()

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

	def test_price_note_and_early_bird_ladder(self):
		event = make_event("Web Early Bird Event", prices=[
			{"title": "Early Bird", "rate": 59.5, "quota": 30, "valid_until": add_days(now_datetime(), 10)},
			{"title": "Regular", "rate": 119}])
		reset_items()
		profile = build_profile(self.item(event), "en")
		hint = next(a for a in profile["actions"] if a.get("hint"))["label"]
		self.assertIn("Early Bird", hint)
		self.assertIn("30 left", hint)
		self.assertIn("then", hint)
		self.assertEqual(profile["ticket"]["price_title"], "Early Bird")

	def test_dialog_has_the_legal_notices(self):
		frappe.set_user("Guest")
		html = get_html_for_route(f"/en/events/{self.event.route}")
		self.assertIn("Order with obligation to pay", html)
		self.assertIn("312g", html)
		self.assertIn("data-wp-step=\"3\"", html)
		self.assertIn("data-wp-add-person", html)  # ticket holders as a table with "+ Add person"
		self.assertIn('data-response="maybe"', html)
		self.assertNotIn('name="terms"', html)  # no checkbox before the order

	def test_sponsor_and_organizer_as_named_stakeholders(self):
		from phamos.tests.marketing_fixtures import make_customer

		party = make_customer("Sponsor Test GmbH")
		named = frappe.get_doc({"doctype": "Stakeholder Web Profile", "stakeholder_type": "Partner", "party_type": "Customer",
			"party": party, "publish_as": "Named", "naming_approved": 1, "naming_approval_date": frappe.utils.nowdate(),
			"published": 1}).insert(ignore_permissions=True)
		hidden_party = make_customer("Secret Sponsor GmbH")
		anonymous = frappe.get_doc({"doctype": "Stakeholder Web Profile", "stakeholder_type": "Partner",
			"party_type": "Customer", "party": hidden_party, "publish_as": "Anonymous", "published": 1}).insert(
			ignore_permissions=True)
		self.event.reload()
		self.event.organizer_is_phamos = 0
		self.event.organizer = named.name
		self.event.append("sponsors", {"published": 1, "stakeholder": named.name, "sponsor_label": "Gold"})
		self.event.append("sponsors", {"published": 1, "stakeholder": anonymous.name})
		self.event.save()
		reset_items()
		item = self.item()
		self.assertEqual([s["name"] for s in item.data["sponsors"]], ["Sponsor Test GmbH"])
		self.assertTrue(item.data["sponsors"][0]["url"].startswith("/en/partners/"))
		self.assertEqual(item.data["organizer"]["name"], "Sponsor Test GmbH")
		self.assertNotIn("Secret Sponsor", json.dumps(item, default=str))
		self.assertEqual(item.data["stakeholders"], [named.name])
		partner = find_item("partners", named.route, "en")
		titles = [block["title"] for block in build_profile(partner, "en")["related"]]
		self.assertIn("Events", titles)

	def test_interest_counts(self):
		frappe.set_user("Guest")
		try:
			self.assertEqual(web.interest(self.event.route, "en", "yes", voter=VOTER_A)["counts"], {"yes": 1, "maybe": 0, "no": 0})
			self.assertEqual(web.interest(self.event.route, "en", "maybe", voter=VOTER_A)["counts"], {"yes": 0, "maybe": 1, "no": 0})
			self.assertRaises(frappe.ValidationError, web.interest, self.event.route, "en", "perhaps", voter=VOTER_A)
		finally:
			frappe.set_user("Administrator")
		reset_items()
		self.assertEqual(self.item().data["interest"], {"yes": 0, "maybe": 1, "no": 0})
		self.assertEqual(build_profile(self.item(), "en")["interest"]["maybe"], 1)

	def test_interest_takes_back_only_the_stored_answer(self):
		# phamos/phamos#1703: a "previous" from the browser never lowers a count.
		frappe.set_user("Guest")
		try:
			web.interest(self.event.route, "en", "yes", voter=VOTER_A)
			counts = web.interest(self.event.route, "en", "no", voter=VOTER_B, previous="yes")["counts"]
			self.assertEqual(counts, {"yes": 1, "maybe": 0, "no": 1})
			self.assertEqual(web.interest(self.event.route, "en", "no", voter=VOTER_A)["counts"], {"yes": 0, "maybe": 0, "no": 2})
			self.assertEqual(web.interest(self.event.route, "en", "no", voter=VOTER_A)["counts"], {"yes": 0, "maybe": 0, "no": 2})
			for bad in (None, "short", "x" * 65, "a b" * 16):
				self.assertRaises(frappe.ValidationError, web.interest, self.event.route, "en", "yes", voter=bad)
		finally:
			frappe.set_user("Administrator")
		key = web._interest_key(self.event.name, VOTER_A)
		self.assertNotIn(VOTER_A, frappe.safe_decode(key))  # a hash of the id, never the id
		self.assertGreater(frappe.cache.ttl(key), 0)

	def test_bookings_shown_publicly(self):
		from phamos.tests.marketing_fixtures import make_attendee

		for i in range(3):
			make_attendee(self.event.name, f"booked{i}@example.com")
		reset_items()
		item = self.item()
		self.assertIn("3/20 booked", item.chips)
		bookings = next(a for a in build_profile(item, "en")["actions"] if a.get("bookings"))
		self.assertEqual((bookings["label"], bookings["percent"]), ("3 of 20 seats taken", 15))
		self.event.reload()
		self.event.show_bookings_publicly = 0
		self.event.save()
		reset_items()
		self.assertFalse([a for a in build_profile(self.item(), "en")["actions"] if a.get("bookings")])
		self.assertNotIn("3/20 booked", self.item().chips)

	def test_hold_endpoint(self):
		frappe.set_user("Guest")
		try:
			result = web.hold(self.event.route, "en", "hold-web-test-1", 2)
			self.assertTrue(result["ok"])
			self.assertGreater(result["expires"], frappe.utils.now_datetime().timestamp() * 1000)
			self.assertRaises(frappe.ValidationError, web.hold, self.event.route, "en", "bad id!", 1)
		finally:
			frappe.set_user("Administrator")
			from phamos.marketing import ticketing

			frappe.cache.delete_value(ticketing._holds_key(self.event.name))

	def test_sidebar_order_and_buy_button_with_price(self):
		profile = build_profile(self.item(), "en")
		actions = profile["actions"]
		buy = actions[0]
		self.assertTrue(buy["primary"])
		self.assertTrue(buy["label"].startswith("Buy from "))
		self.assertIn("119", buy["label"])
		self.assertEqual(buy["sub"], "incl. VAT")
		self.assertEqual([a["label"] for a in actions if a.get("pair")], ["Add to calendar", "Create reminder"])
		self.assertTrue(all(a.get("secondary") for a in actions if a.get("pair") or a.get("dialog") == "subscribe"))
		# Secondary actions come after the main group.
		first_secondary = next(i for i, a in enumerate(actions) if a.get("secondary"))
		self.assertFalse([a for a in actions[first_secondary:] if not a.get("secondary")])

	def test_sold_out_note_shows_with_bookings(self):
		from phamos.tests.marketing_fixtures import make_attendee

		self.event.reload()
		self.event.max_attendees = 2
		self.event.save()
		for i in range(2):
			make_attendee(self.event.name, f"full{i}@example.com")
		reset_items()
		actions = build_profile(self.item(), "en")["actions"]
		self.assertIn("Sold out", [a["label"] for a in actions if a.get("note")])
		self.assertTrue([a for a in actions if a.get("bookings")])

	def test_speakers_and_sponsors_are_cards(self):
		profile = build_profile(self.item(), "en")
		speakers = next(b for b in profile["blocks"] if b["kind"] == "people")
		self.assertEqual(speakers["entries"][0]["title"], "Speaker Searchable")
		self.assertEqual(speakers["entries"][0]["subtitle"], "Keynote")
		self.assertEqual(speakers["entries"][0]["initials"], "SS")
		frappe.set_user("Guest")
		html = get_html_for_route(f"/en/events/{self.event.route}")
		self.assertIn("wp-tile-person", html)
		self.assertNotIn("wp-rows", html)

	def test_reminders(self):
		future = add_days(now_datetime(), 3)
		at = ",".join([future.strftime("%Y-%m-%dT09:00"), future.strftime("%Y-%m-%dT09:00"),
			add_days(future, 1).strftime("%Y-%m-%dT18:30"), "2001-01-01T10:00", "nonsense"])
		web.reminders(self.event.route, "en", at=at, tz="Europe/Berlin")
		self.assertEqual(frappe.response["type"], "download")
		content = frappe.response["filecontent"].decode()
		self.assertEqual(content.count("BEGIN:VEVENT"), 2)  # duplicate and past dates dropped
		self.assertEqual(content.count("BEGIN:VALARM"), 2)
		self.assertIn("SUMMARY:Reminder: Web Test Event", content)
		self.assertRaises(frappe.ValidationError, web.reminders, self.event.route, "en", at="2001-01-01T10:00")
		self.assertEqual(len(web.parse_reminders(",".join(
			add_days(future, i).strftime("%Y-%m-%dT10:00") for i in range(5)), "Not/AZone")), 3)

	def test_subscription_confirmed_page(self):
		self.assertEqual(frappe.db.get_value("Email Group", GROUP, "welcome_url"),
			frappe.utils.get_url(f"/de/anmeldung-bestaetigt?event={self.event.route}"))
		frappe.set_user("Guest")
		frappe.form_dict.event = self.event.route  # page renders in tests don't parse the query string
		html = get_html_for_route(f"/en/subscription-confirmed?event={self.event.route}")
		self.assertIn("Subscription confirmed", html)
		self.assertIn("Web Test Event", html)
		self.assertIn("Back to the event", html)
		self.assertIn("noindex", html)

	def test_dialog_round5_markup(self):
		frappe.set_user("Guest")
		html = get_html_for_route(f"/en/events/{self.event.route}")
		for marker in ("data-wp-hold-clock", "wp-step-no", "data-wp-invoice", "data-wp-success-invoice", "wp-switch-track",
				"data-wp-reminder-dialog", "wp-interest-yes"):
			self.assertIn(marker, html)
		self.assertNotIn("data-wp-print", html)

	def test_period_slider_by_month(self):
		from phamos.web_profile.listing import build_listing

		past_month = self.item(self.past).numbers["month"]
		next_month = self.item().numbers["month"]
		self.assertLess(past_month, next_month)
		try:
			# Upcoming (default): the slider spans only upcoming months.
			set_request(method="GET", path="/en/events")
			facet = next(f for f in build_listing("events", "en")["facets"] if f["key"] == "month")
			today = frappe.utils.getdate()
			self.assertEqual(facet["min"], today.year * 12 + today.month - 1)  # from this month
			self.assertGreaterEqual(facet["max"], facet["min"] + 11)  # at least a year ahead
			# All events, limited to the past event's month.
			set_request(method="GET", path=f"/en/events?when=all&month_min={past_month}&month_max={past_month}")
			listing = build_listing("events", "en")
			names = [i.name for i in listing["results"]]
			self.assertIn(self.past.name, names)
			self.assertNotIn(self.event.name, names)
			facet = next(f for f in listing["facets"] if f["key"] == "month")
			self.assertEqual(len(facet["labels"]), facet["max"] - facet["min"] + 1)
			self.assertRegex(facet["low_label"], r"\d{4}")
			self.assertTrue(any("Period" in chip["label"] for chip in listing["active_filters"]))
		finally:
			frappe.local.request = None

