# Copyright (c) 2026, phamos.eu and contributors
# For license information, please see license.txt

"""Privacy, URL and contact rules of the Web Profile pages (phamos/phamos#1492, #1505–#1512).

Integration tests: they create their own Employee, Customer, Contact and Web Profiles and roll
everything back afterwards. Run with
    bench --site <site> run-tests --module phamos.tests.test_web_profile
"""

import frappe
from frappe.tests.utils import FrappeTestCase
from frappe.utils import add_years, nowdate

from phamos.web_profile import contact
from phamos.web_profile.i18n import localized
from phamos.web_profile.sections import build_profile, find_item, get_items

CUSTOMER = "WP Test Kunde GmbH"


def _reset_items():
	"""Rendered items are cached in redis and per request; tests change records between reads."""
	frappe.local.web_profile_items = None
	frappe.cache.delete_value("web_profile_items")


def _person_item(profile_name):
	_reset_items()
	return next(i for i in get_items("people", "en") if i.name == profile_name)


class TestWebProfile(FrappeTestCase):
	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		frappe.local.lang = "en"
		company = frappe.defaults.get_global_default("company") or frappe.get_all("Company", pluck="name", limit=1)[0]
		gender = frappe.get_all("Gender", pluck="name", limit=1)[0]

		cls.employee = frappe.get_doc({
			"doctype": "Employee", "first_name": "Testa", "last_name": "Webprofil", "company": company,
			"gender": gender, "date_of_birth": "1990-01-01", "date_of_joining": add_years(nowdate(), -3),
			"status": "Active",
		}).insert(ignore_permissions=True).name
		cls.person = frappe.get_doc({
			"doctype": "Person Web Profile", "party_type": "Employee", "party": cls.employee, "published": 1,
		}).insert(ignore_permissions=True)

		if not frappe.db.exists("Customer", CUSTOMER):
			frappe.get_doc({
				"doctype": "Customer", "customer_name": CUSTOMER, "customer_type": "Company",
				"customer_group": frappe.db.get_value("Customer Group", {"is_group": 0}) or "All Customer Groups",
				"territory": frappe.db.get_value("Territory", {"is_group": 0}) or "All Territories",
			}).insert(ignore_permissions=True)
		cls.stakeholder = frappe.get_doc({
			"doctype": "Stakeholder Web Profile", "stakeholder_type": "Customer", "party_type": "Customer",
			"party": CUSTOMER, "publish_as": "Anonymous", "region": "DACH", "published": 1,
		}).insert(ignore_permissions=True)

		cls.contact = frappe.get_doc({
			"doctype": "Contact", "first_name": "Tina", "last_name": "Kontakt",
			"email_ids": [{"email_id": "tina.kontakt@example.com", "is_primary": 1}],
			"links": [{"link_doctype": "Customer", "link_name": CUSTOMER}],
		}).insert(ignore_permissions=True).name
		cls.external = frappe.get_doc({
			"doctype": "Person Web Profile", "party_type": "Customer", "party": CUSTOMER, "contact": cls.contact,
			"publication_consent": 1, "publication_consent_date": nowdate(),
			"contact_consent": 1, "contact_consent_date": nowdate(), "published": 1,
		}).insert(ignore_permissions=True)

	@classmethod
	def tearDownClass(cls):
		super().tearDownClass()  # rolls back the records above
		_reset_items()  # the cache may still hold items built from them

	def setUp(self):
		frappe.local.lang = "en"
		_reset_items()
		# Every test starts from the records of setUpClass: changes are undone after each test.
		frappe.db.savepoint("web_profile_test")

	def tearDown(self):
		frappe.db.rollback(save_point="web_profile_test")
		_reset_items()

	def _submit(self, slug, section="people", **overrides):
		values = {"section": section, "slug": slug, "lang": "en", "sender_name": "Test Visitor",
			"sender_email": "visitor@example.com", "message": "Hello", "privacy_consent": 1}
		values.update(overrides)
		return contact.submit(**values)

	# --- texts -------------------------------------------------------------------------------------

	def test_localized_falls_back_to_german_then_any_language(self):
		record = frappe._dict(texts={"de": {"summary": "Deutsch"}, "fr": {"summary": "Français", "title": "Titre"}})
		self.assertEqual(localized(record, "summary", "en"), "Deutsch")
		self.assertEqual(localized(record, "title", "en"), "Titre")
		self.assertEqual(localized(record, "title", "en", fallback=False), "")

	def test_one_text_row_per_language(self):
		doc = frappe.get_doc("Person Web Profile", self.person.name)
		doc.append("translations", {"language": "de", "summary": "Eins"})
		doc.append("translations", {"language": "de", "summary": "Zwei"})
		self.assertRaises(frappe.ValidationError, doc.save)

	# --- person URLs -------------------------------------------------------------------------------

	def test_person_route_is_a_neutral_code(self):
		self.assertRegex(self.person.route, r"^p-[a-z2-9]{5}$")
		self.assertNotIn("testa", self.person.route)

	def test_person_route_with_a_name_is_refused(self):
		for route in ("testa-w", "webprofil"):
			doc = frappe.get_doc("Person Web Profile", self.person.name)
			doc.route = route
			self.assertRaises(frappe.ValidationError, doc.save)

	# --- anonymous people --------------------------------------------------------------------------

	def _make_anonymous(self):
		doc = frappe.get_doc("Person Web Profile", self.person.name)
		doc.publish_as = "Anonymous"
		doc.save(ignore_permissions=True)
		return doc

	def test_anonymous_person_hides_name_and_cannot_be_contacted(self):
		doc = self._make_anonymous()
		item = _person_item(doc.name)
		self.assertTrue(item.masked)
		self.assertNotIn("Testa", item.title)
		self.assertIsNone(item.image)
		self.assertFalse(item.data["contactable"])

		profile = build_profile(item, "en")
		self.assertIsNone(profile["cta"])
		self.assertTrue(all(not card["contact"] for card in profile["key_people"]))
		self.assertIsNone(profile["schema"])

	def test_url_stays_the_same_when_a_person_becomes_anonymous(self):
		route = self.person.route
		doc = self._make_anonymous()
		self.assertEqual(doc.route, route)
		_reset_items()
		item = find_item("people", route, "en")
		self.assertTrue(item and item.masked)

	def test_contact_request_to_anonymous_person_is_refused(self):
		doc = self._make_anonymous()
		_reset_items()
		self.assertRaises(frappe.PermissionError, self._submit, doc.route)

	# --- external people and anonymous stakeholders ------------------------------------------------

	def test_anonymous_stakeholder_is_not_named_through_its_people(self):
		item = _person_item(self.external.name)
		self.assertFalse(item.masked)  # the person itself agreed to be named
		self.assertNotEqual(item.data["organization"], CUSTOMER)
		self.assertNotIn(CUSTOMER, item.chips)
		self.assertNotIn(CUSTOMER.lower(), item.search)
		self.assertNotIn(CUSTOMER, item.subtitle)
		stakeholder = frappe.get_doc("Stakeholder Web Profile", self.stakeholder.name)
		self.assertEqual(item.data["organization_url"], f"/en/customers/{stakeholder.route}")

	def test_named_stakeholder_is_shown_with_its_name(self):
		frappe.db.set_value("Stakeholder Web Profile", self.stakeholder.name,
			{"publish_as": "Named", "naming_approved": 1, "naming_approval_date": nowdate()})
		item = _person_item(self.external.name)
		self.assertEqual(item.data["organization"], CUSTOMER)
		self.assertIn(CUSTOMER, item.chips)

	def test_named_stakeholder_needs_approval(self):
		doc = frappe.get_doc("Stakeholder Web Profile", self.stakeholder.name)
		doc.publish_as = "Named"
		self.assertRaises(frappe.ValidationError, doc.save)

	def test_anonymous_stakeholder_text_must_not_name_it(self):
		doc = frappe.get_doc("Stakeholder Web Profile", self.stakeholder.name)
		doc.append("translations", {"language": "de", "summary": "WP Test Kunde führt ERPNext ein."})
		self.assertRaises(frappe.ValidationError, doc.save)

	def test_stakeholder_route_never_names_it(self):
		doc = frappe.get_doc("Stakeholder Web Profile", self.stakeholder.name)
		self.assertTrue(doc.route)
		self.assertNotIn("kunde", doc.route)
		doc.route = "wp-test-kunde-dach"
		self.assertRaises(frappe.ValidationError, doc.save)

	def test_stakeholder_url_stays_the_same_when_named(self):
		route = self.stakeholder.route
		doc = frappe.get_doc("Stakeholder Web Profile", self.stakeholder.name)
		doc.update({"publish_as": "Named", "naming_approved": 1, "naming_approval_date": nowdate()})
		doc.save(ignore_permissions=True)
		self.assertEqual(doc.route, route)

	# --- contact workflow --------------------------------------------------------------------------

	def test_contact_request_needs_consent(self):
		self.assertRaises(frappe.ValidationError, self._submit, self.person.route, privacy_consent=0)

	def test_contact_request_to_phamos_person_creates_opportunity(self):
		result = self._submit(self.person.route)
		self.assertEqual(result["flow"], "opportunity")
		opportunity = frappe.get_all("Opportunity", filters={"contact_email": "visitor@example.com"},
			fields=["name", "title"], order_by="creation desc", limit=1)
		self.assertTrue(opportunity)
		self.assertTrue(frappe.db.exists("Communication",
			{"reference_doctype": "Opportunity", "reference_name": opportunity[0].name}))

	def test_honeypot_is_ignored_silently(self):
		before = frappe.db.count("Opportunity")
		self.assertEqual(self._submit(self.person.route, website="http://spam.example")["ok"], True)
		self.assertEqual(frappe.db.count("Opportunity"), before)
