# Copyright (c) 2026, phamos.eu and contributors
# For license information, please see license.txt

"""Open Graph tags of the Web Profile pages (phamos/phamos#1738).

Social networks build their link preview from og:image and og:url. Pages without an image of
their own fall back to Web Profile Settings > Share Image. Run with
    bench --site <site> run-tests --module phamos.tests.test_web_profile_seo
"""

import frappe
from frappe.tests.utils import FrappeTestCase
from frappe.utils import get_url, set_request
from frappe.website.serve import get_response_content

from phamos.web_profile.page import set_seo

SHARE_IMAGE = "/files/wp-test-share.png"
OWN_IMAGE = "/files/wp-test-own.jpg"


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
		frappe.db.rollback(save_point="web_profile_seo_test")
		frappe.db.value_cache.pop("Web Profile Settings", None)

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
		frappe.set_user("Guest")
		set_request(method="GET", path="/en/people")
		try:
			html = get_response_content("/en/people")
		finally:
			frappe.set_user("Administrator")
		self.assertIn(f'property="og:image"  content="{get_url(SHARE_IMAGE)}"', html)
		self.assertIn(f'property="og:url"  content="{get_url("/en/people")}"', html)
		self.assertIn('name="twitter:card" content="summary_large_image"', html)
