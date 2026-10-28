"""CRM resolution for attendees. bench --site <site> run-tests --module phamos.tests.test_marketing_crm"""

import frappe
from frappe.tests.utils import FrappeTestCase

from phamos.marketing import crm
from phamos.tests.marketing_fixtures import ensure_company, make_attendee, make_customer, make_event


class TestMarketingCrm(FrappeTestCase):
	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		frappe.set_user("Administrator")
		ensure_company()
		cls.event = make_event(paid=False)

	def setUp(self):
		frappe.set_user("Administrator")
		frappe.db.savepoint("crm_test")

	def tearDown(self):
		frappe.set_user("Administrator")
		frappe.db.rollback(save_point="crm_test")

	def test_contact_of_a_customer_is_a_strong_match(self):
		make_customer("CRM Test Kunde GmbH", "einkauf@crm-kunde.example")
		found = crm.find_party("Einkauf@crm-kunde.example")
		self.assertEqual(found.customer, "CRM Test Kunde GmbH")
		self.assertEqual(found.confidence, "strong")

	def test_new_person_becomes_lead_with_contact_source_and_campaign(self):
		result = crm.resolve_party(email="new.person@example.com", first_name="New", last_name="Person",
			company_name="Neu GmbH", event=self.event)
		lead = frappe.get_doc("Lead", result.lead)
		self.assertEqual(lead.source, "Event")
		self.assertEqual(lead.campaign_name, self.event.campaign)
		self.assertEqual(lead.company_name, "Neu GmbH")
		self.assertTrue(result.contact)
		links = frappe.get_all("Dynamic Link", filters={"parent": result.contact, "parenttype": "Contact"},
			fields=["link_doctype", "link_name"])
		self.assertIn(("Lead", result.lead), {(l.link_doctype, l.link_name) for l in links})
		self.assertEqual(result.crm_status, "Linked")

	def test_existing_lead_is_reused(self):
		first = crm.resolve_party(email="twice@example.com", first_name="Twice", event=self.event)
		second = crm.resolve_party(email="twice@example.com", first_name="Twice", event=self.event)
		self.assertEqual(first.lead, second.lead)
		self.assertEqual(second.created, [])

	def test_works_without_auto_contact_creation(self):
		frappe.db.set_single_value("CRM Settings", "auto_creation_of_contact", 0)
		result = crm.resolve_party(email="nocontact@example.com", first_name="No", event=self.event)
		self.assertTrue(result.contact)
		self.assertIn(("Contact", result.contact), result.created)

	def test_company_name_match_needs_review(self):
		make_customer("Review Maschinenbau GmbH")
		found = crm.find_party("someone@other.example", "Review Maschinenbau")
		self.assertEqual(found.confidence, "review")
		self.assertEqual(found.company_match, "Review Maschinenbau GmbH")
		self.assertIsNone(found.customer)

	def test_unverified_email_never_reuses_or_changes_existing_records(self):
		make_customer("Unverified Kunde GmbH", "known@crm-kunde.example")
		contact = crm.contact_for_email("known@crm-kunde.example")
		lead = crm.resolve_party(email="lead@crm-kunde.example", first_name="Known", event=self.event).lead
		for email in ("known@crm-kunde.example", "lead@crm-kunde.example"):
			result = crm.resolve_party(email=email, first_name="Stranger", company_name="Fremd GmbH", event=self.event,
				link_to_customer="Some Order Customer", verified=False)
			self.assertEqual((result.contact, result.lead, result.created), (None, None, []))
			self.assertEqual(result.customer, "Some Order Customer")  # the order's own Customer only
			self.assertEqual(result.crm_status, "Needs Review")
			self.assertIn("Possible match", result.review_note)
		self.assertEqual(frappe.get_all("Dynamic Link", filters={"parenttype": "Contact", "parent": contact},
			pluck="link_name"), ["Unverified Kunde GmbH"])
		self.assertFalse(frappe.db.get_value("Lead", lead, "company_name"))

	def test_unverified_new_email_still_becomes_lead(self):
		result = crm.resolve_party(email="brand.new@example.com", first_name="Brand", event=self.event, verified=False)
		self.assertTrue(result.lead and result.contact)
		self.assertEqual(result.crm_status, "Linked")
		self.assertIsNone(result.review_note)

	def test_link_attendee_stores_links(self):
		att = make_attendee(self.event.name, "linkme@example.com", "Link", "Me")
		crm.link_attendee(att.name)
		att.reload()
		self.assertTrue(att.lead and att.contact)
		self.assertEqual(att.crm_status, "Linked")

	# --- the shared website step (phamos/phamos#1724) ---------------------------------------------------

	def test_match_or_create_lead_links_a_customer_first(self):
		make_customer("Match Kunde GmbH", "match@crm-kunde.example")
		lead = frappe.get_doc({"doctype": "Lead", "first_name": "Match", "email_id": "match@crm-kunde.example",
			"status": "Lead"}).insert(ignore_permissions=True)
		result = crm.match_or_create_lead(email="Match@crm-kunde.example", first_name="Match")
		self.assertEqual((result.customer, result.lead, result.created), ("Match Kunde GmbH", None, False))
		self.assertTrue(result.contact)
		self.assertTrue(frappe.db.exists("Lead", lead.name))

	def test_match_or_create_lead_links_an_existing_lead(self):
		lead = frappe.get_doc({"doctype": "Lead", "first_name": "Only", "email_id": "only.lead@crm.example",
			"status": "Lead"}).insert(ignore_permissions=True)
		result = crm.match_or_create_lead(email="only.lead@crm.example", first_name="Only", phone="+49 711 1")
		self.assertEqual((result.lead, result.created), (lead.name, False))
		self.assertEqual(frappe.db.get_value("Lead", lead.name, "mobile_no"), "+49 711 1")

	def test_match_or_create_lead_creates_a_guest_owned_lead(self):
		result = crm.match_or_create_lead(email="brand.new@crm.example", first_name="Brand", last_name="New",
			campaign=None, source=crm.ensure_lead_source())
		lead = frappe.get_doc("Lead", result.lead)
		self.assertTrue(result.created)
		self.assertEqual((lead.lead_owner, lead.email_id, lead.lead_name), ("Guest", "brand.new@crm.example", "Brand New"))

