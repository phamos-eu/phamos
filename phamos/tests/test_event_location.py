"""Where an event takes place: online / in person, the private meeting link, address, map pin (phamos/phamos#1665).

bench --site <site> run-tests --module phamos.tests.test_event_location
"""

import json
from unittest.mock import patch

import frappe
from frappe.tests.utils import FrappeTestCase
from frappe.utils import get_html_for_route

from phamos.marketing import location, ticketing, web
from phamos.patches.v1_0 import set_event_attendance_mode
from phamos.tests.marketing_fixtures import ensure_company, make_event
from phamos.web_profile.sections import build_profile, find_item

LINK = "https://meet.example.com/phamos-secret-room"
FOUND = [{"lat": "48.4914", "lon": "9.2043", "display_name": "Marktplatz 1, 72764 Reutlingen"}]


def reset_items():
	frappe.local.web_profile_items = None
	frappe.cache.delete_value("web_profile_items")


class TestEventLocation(FrappeTestCase):
	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		frappe.set_user("Administrator")
		frappe.local.lang = "en"
		ensure_company()

	def setUp(self):
		frappe.set_user("Administrator")
		frappe.local.request = None
		frappe.db.savepoint("event_location_test")
		reset_items()

	def tearDown(self):
		frappe.set_user("Administrator")
		frappe.db.rollback(save_point="event_location_test")
		reset_items()

	def online_event(self, **kwargs):
		return make_event("Location Online Event", attendance_mode="Online", location=LINK, city="Reutlingen", **kwargs)

	def in_person_event(self, **kwargs):
		values = {"location": "Rathaus", "street": "Marktplatz 1", "postal_code": "72764", "city": "Reutlingen",
			"country": "Germany", **kwargs}
		with patch("phamos.marketing.location._search", return_value=FOUND):
			return make_event("Location In Person Event", **values)

	def item(self, event, lang="en"):
		reset_items()
		return find_item("events", event.route, lang)

	# --- validation -------------------------------------------------------------------------------------

	def test_online_needs_an_https_link(self):
		for value in (None, "Zoom", "http://meet.example.com/room", "https://"):
			with self.assertRaises(frappe.ValidationError, msg=value):
				make_event("Location Online Event", attendance_mode="Online", location=value)

	def test_online_clears_the_address(self):
		event = self.online_event(street="Weg 1", postal_code="72764", geolocation=location.point(48.5, 9.2))
		self.assertEqual(event.location, LINK)
		for field in ("street", "postal_code", "city", "country", "geolocation"):
			self.assertFalse(event.get(field), field)

	def test_in_person_rejects_a_link(self):
		for value in (LINK, "www.example.com/room"):
			with self.assertRaises(frappe.ValidationError, msg=value):
				make_event("Location In Person Event", location=value)

	def test_mode_defaults_to_in_person(self):
		self.assertEqual(make_event("Location Default Event").attendance_mode, "In person")

	# --- map pin ----------------------------------------------------------------------------------------

	def test_address_is_looked_up_once_and_a_set_pin_is_kept(self):
		event = self.in_person_event()
		self.assertAlmostEqual(event.latitude, 48.4914, places=4)
		self.assertAlmostEqual(event.longitude, 9.2043, places=4)

		# Pin dragged by hand, then the address changes: the pin stays, no lookup.
		event.geolocation = location.point(48.5, 9.21)
		event.save()
		event.street = "Marktplatz 2"
		with patch("phamos.marketing.location._search", return_value=FOUND) as search:
			event.save()
		search.assert_not_called()
		self.assertEqual((event.latitude, event.longitude), (48.5, 9.21))

	def test_lookup_failure_does_not_block_saving(self):
		with patch("phamos.marketing.location._search", side_effect=OSError("offline")):
			event = make_event("Location In Person Event", location="Rathaus", city="Nowhere")
		self.assertFalse(event.geolocation)
		self.assertFalse(event.latitude)

	def test_find_on_map(self):
		with patch("phamos.marketing.location._search", return_value=FOUND):
			self.assertAlmostEqual(location.find_on_map(city="Reutlingen")["latitude"], 48.4914, places=4)
		with patch("phamos.marketing.location._search", return_value=[]):
			self.assertRaises(frappe.ValidationError, location.find_on_map, city="Nowhere")

	def test_map_links(self):
		links = location.map_links(48.4914, 9.2043, "Rathaus Reutlingen")
		self.assertEqual(links["osm"], "https://www.openstreetmap.org/?mlat=48.491400&mlon=9.204300#map=18/48.491400/9.204300")
		self.assertEqual(links["geo"], "geo:48.491400,9.204300?q=48.491400,9.204300(Rathaus%20Reutlingen)")
		self.assertTrue(links["apple"].startswith("https://maps.apple.com/?ll=48.491400%2C9.204300&q=Rathaus"))
		self.assertIsNone(location.map_links(None, None))

	def test_coordinates_from_old_map_links(self):
		for url, expected in (
				("https://www.openstreetmap.org/?mlat=48.4914&mlon=9.2043#map=17/48.49/9.20", (48.4914, 9.2043)),
				("https://www.openstreetmap.org/#map=17/48.49140/9.20430", (48.4914, 9.2043)),
				("https://www.google.com/maps/place/Rathaus/@48.49,9.20,17z/data=!3m1!4b1!4m6!3m5!1s0x0:0x0!8m2!3d48.4914!4d9.2043",
					(48.4914, 9.2043)),
				("https://www.google.com/maps/@48.4914,9.2043,15z", (48.4914, 9.2043)),
				("https://maps.app.goo.gl/AbCdEf", (None, None))):
			self.assertEqual(location.coordinates_from_map_link(url), expected, url)

	# --- website ----------------------------------------------------------------------------------------

	def test_online_event_never_shows_the_link(self):
		event = self.online_event()
		item = self.item(event)
		self.assertTrue(item.data["online"])
		self.assertIsNone(item.data["location"])
		self.assertEqual(item.facets["city"], ["online"])
		self.assertIn("Online", item.chips)
		self.assertNotIn("meet.example.com", json.dumps(item, default=str))

		profile = build_profile(item, "en")
		self.assertEqual(profile["schema"]["eventAttendanceMode"], "https://schema.org/OnlineEventAttendanceMode")
		self.assertEqual(profile["schema"]["location"]["@type"], "VirtualLocation")
		self.assertTrue(profile["schema"]["location"]["url"].endswith(item.url))
		self.assertIn("online", profile["overview"])

		frappe.set_user("Guest")
		html = get_html_for_route(f"/en/events/{event.route}")
		self.assertNotIn("meet.example.com", html)
		self.assertNotIn("data-wp-maps", html)

	def test_in_person_event_has_address_pin_and_maps_button(self):
		event = self.in_person_event()
		item = self.item(event)
		self.assertFalse(item.data["online"])
		self.assertEqual(item.facets["city"], ["reutlingen"])

		profile = build_profile(item, "en")
		where = next(line for line in profile["hero"]["lines"] if line["kind"] == "where")
		self.assertEqual(where["text"], "Rathaus, Marktplatz 1, 72764 Reutlingen")
		self.assertIn("mlat=48.491400", where["maps"]["osm"])
		place = profile["schema"]["location"]
		self.assertEqual(place["address"]["streetAddress"], "Marktplatz 1")
		self.assertEqual(place["address"]["addressCountry"], "DE")
		self.assertAlmostEqual(place["geo"]["latitude"], 48.4914, places=4)

		frappe.set_user("Guest")
		html = get_html_for_route(f"/en/events/{event.route}")
		self.assertIn("data-wp-maps", html)
		self.assertIn("geo:48.491400,9.204300", html)

	# --- calendar file and emails -----------------------------------------------------------------------

	def test_meeting_link_only_in_the_attendees_calendar_file(self):
		item = self.item(self.online_event())
		public = web.build_ics(item).decode()
		self.assertIn("LOCATION:Online", public)
		self.assertNotIn("meet.example.com", public)
		private = web.build_ics(item, for_attendee=True).decode().replace("\r\n ", "")
		self.assertIn(f"LOCATION:{LINK}", private)

	def test_in_person_calendar_file_has_address_and_geo(self):
		content = web.build_ics(self.item(self.in_person_event())).decode().replace("\r\n ", "")
		self.assertIn("LOCATION:Rathaus\\, Marktplatz 1\\, 72764 Reutlingen", content)
		self.assertIn("GEO:48.4914;9.2043", content)

	def test_email_venue(self):
		self.assertEqual(ticketing.venue(self.online_event()), {"online": True, "link": LINK})
		venue = ticketing.venue(self.in_person_event())
		self.assertEqual(venue["text"], "Rathaus, Marktplatz 1, 72764 Reutlingen")
		self.assertIn("openstreetmap.org", venue["maps_url"])

	# --- patch ------------------------------------------------------------------------------------------

	def test_patch_sets_mode_and_reads_old_map_links(self):
		online = make_event("Location Patch Online", location="Venue")
		in_person = make_event("Location Patch In Person", location="Rathaus")
		frappe.db.set_value("Marketing Content", online.name, {"location": LINK, "attendance_mode": None})
		frappe.db.set_value("Marketing Content", in_person.name, "attendance_mode", None)
		has_map_link = frappe.db.has_column("Marketing Content", "map_link")
		if has_map_link:
			frappe.db.sql("update `tabMarketing Content` set map_link=%s where name=%s",
				("https://www.openstreetmap.org/?mlat=48.4914&mlon=9.2043", in_person.name))
		set_event_attendance_mode.execute()
		self.assertEqual(frappe.db.get_value("Marketing Content", online.name, "attendance_mode"), "Online")
		self.assertEqual(frappe.db.get_value("Marketing Content", in_person.name, "attendance_mode"), "In person")
		if has_map_link:
			self.assertAlmostEqual(frappe.db.get_value("Marketing Content", in_person.name, "latitude"), 48.4914, places=4)
