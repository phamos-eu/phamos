# Copyright (c) 2026, phamos.eu and contributors
# For license information, please see license.txt

"""Open Graph tags of the Web Profile pages (phamos/phamos#1738).

Social networks build their link preview from og:image and og:url. Pages without an image of
their own fall back to Web Profile Settings > Share Image; a record with an image (an event
banner, a person's photo) keeps it. Run with
    bench --site <site> run-tests --module phamos.tests.test_web_profile_seo
"""

import frappe
from frappe.tests.utils import FrappeTestCase
from frappe.utils import get_url, set_request
from frappe.website.serve import get_response_content

from phamos.tests.marketing_fixtures import ensure_company, make_event
from phamos.web_profile.page import set_seo

SHARE_IMAGE = "/files/wp-test-share.png"
OWN_IMAGE = "/files/wp-test-own.jpg"
EVENT_IMAGE = "/files/wp-test-event.jpg"


def _reset_items():
	frappe.local.web_profile_items = None
	frappe.cache.delete_value("web_profile_items")


def _render(path):
	"""The page as a social network's crawler gets it: as Guest, without a session."""
	frappe.set_user("Guest")
	set_request(method="GET", path=path)
	try:
		return get_response_content(path)
	finally:
		frappe.set_user("Administrator")


def _seo(**overrides):
	context = frappe._dict(lang="en")
	values = {"title": "People · phamos", "description": "Who we are", "path": "/en/people",
		"alternates": {"de": "/de/personen", "en": "/en/people"}}
	values.update(overrides)
	set_seo(context, **values)
	return context


class TestWebProfileSeo(FrappeTestCase):
	def setUp(self):
		frappe.local.lang = "en"
		frappe.db.savepoint("web_profile_seo_test")
		frappe.db.set_single_value("Web Profile Settings", "share_image", None)

	def tearDown(self):
		frappe.set_user("Administrator")
		frappe.local.request = None  # page renders leave a request behind, which switches rate limits on
		frappe.db.rollback(save_point="web_profile_seo_test")
		frappe.db.value_cache.pop("Web Profile Settings", None)
		_reset_items()

	def _set_share_image(self, url):
		frappe.db.set_single_value("Web Profile Settings", "share_image", url)

	def test_a_private_share_image_is_refused(self):
		settings = frappe.get_single("Web Profile Settings")
		settings.share_image = "/private/files/wp-test-share.png"
		self.assertRaises(frappe.ValidationError, settings.save)

	def test_without_share_image_the_page_has_no_image_but_og_url_and_site_name(self):
		tags = _seo().metatags
		self.assertIsNone(tags["image"])
		self.assertEqual(tags["og:url"], get_url("/en/people"))
		self.assertEqual(tags["og:site_name"], "phamos")

	def test_share_image_is_the_fallback_for_pages_without_their_own_image(self):
		self._set_share_image(SHARE_IMAGE)
		self.assertEqual(_seo().metatags["image"], get_url(SHARE_IMAGE))

	def test_a_page_with_its_own_image_keeps_it(self):
		self._set_share_image(SHARE_IMAGE)
		self.assertEqual(_seo(image=OWN_IMAGE).metatags["image"], get_url(OWN_IMAGE))

	def test_og_url_is_the_canonical_url_without_the_filter_query(self):
		tags = _seo(path="/en/people?q=erp", canonical_path="/en/people").metatags
		self.assertEqual(tags["og:url"], get_url("/en/people"))

	def test_people_listing_renders_the_open_graph_image_tags(self):
		self._set_share_image(SHARE_IMAGE)
		html = _render("/en/people")
		self.assertIn(f'property="og:image"  content="{get_url(SHARE_IMAGE)}"', html)
		self.assertIn(f'property="og:url"  content="{get_url("/en/people")}"', html)
		self.assertIn('name="twitter:card" content="summary_large_image"', html)

	def test_events_listing_and_event_pages_render_the_open_graph_image_tags(self):
		"""The events overview shares the site image; an event shares its own banner, or the site image without one."""
		ensure_company()
		with_image = make_event("SEO Event With Image", paid=False, image=EVENT_IMAGE)
		without_image = make_event("SEO Event Without Image", paid=False, image=None)
		_reset_items()
		self._set_share_image(SHARE_IMAGE)

		html = _render("/en/events")
		self.assertIn(f'property="og:image"  content="{get_url(SHARE_IMAGE)}"', html)
		self.assertIn(f'property="og:url"  content="{get_url("/en/events")}"', html)
		self.assertIn('name="twitter:card" content="summary_large_image"', html)

		html = _render(f"/de/veranstaltungen/{with_image.route}")
		self.assertIn(f'property="og:image"  content="{get_url(EVENT_IMAGE)}"', html)
		self.assertIn(f'property="og:url"  content="{get_url(f"/de/veranstaltungen/{with_image.route}")}"', html)
		self.assertIn('property="og:title"  content="SEO Event With Image · Veranstaltungen · phamos"', html)
		self.assertIn('name="twitter:card" content="summary_large_image"', html)

		html = _render(f"/en/events/{without_image.route}")
		self.assertIn(f'property="og:image"  content="{get_url(SHARE_IMAGE)}"', html)
		self.assertIn(f'property="og:url"  content="{get_url(f"/en/events/{without_image.route}")}"', html)
