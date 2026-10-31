# Copyright (c) 2026, phamos.eu and contributors
# For license information, please see license.txt

"""Accounting Cockpit receivables (#1777): aging rules, credits, contacts, last contact,
grouping, the endpoint with patched queries, permissions, and one run of the real report."""

from datetime import date
from unittest.mock import patch

import frappe
from frappe.tests.utils import FrappeTestCase
from frappe.utils import add_days, flt, getdate, today

from phamos.accounting import receivables as rc
from phamos.api import accounting_receivables as api

TODAY = date(2026, 10, 31)


def _row(voucher_no, party, outstanding, due_date=None, voucher_type="Sales Invoice", posting_date="2026-09-01", **extra):
	"""A row shaped like ERPNext's Accounts Receivable report."""
	return frappe._dict(
		voucher_type=voucher_type,
		voucher_no=voucher_no,
		party_type=extra.pop("party_type", "Customer"),
		party=party,
		customer_name=extra.pop("customer_name", f"{party} GmbH"),
		posting_date=getdate(posting_date),
		due_date=getdate(due_date) if due_date else None,
		invoiced=max(outstanding, 0),
		paid=0,
		credit_note=0,
		outstanding=outstanding,
		**extra,
	)


def _build(rows, invoice_details=None, customer_details=None, contact_rows=None, currency="EUR"):
	return api.build_receivables(
		company="Test Co",
		currency=currency,
		today_date=TODAY,
		report_rows=rows,
		invoice_details=invoice_details or {},
		customer_details=customer_details or {},
		contact_rows=contact_rows or {},
		companies=["Test Co"],
	)


class TestAgingRules(FrappeTestCase):
	def test_days_overdue_and_bucket_boundaries(self):
		cases = {
			"2026-11-10": (0, "not_due"),
			"2026-10-31": (0, "not_due"),
			"2026-10-30": (1, "d1_30"),
			"2026-10-01": (30, "d1_30"),
			"2026-09-30": (31, "d31_60"),
			"2026-09-01": (60, "d31_60"),
			"2026-08-31": (61, "d61_90"),
			"2026-08-02": (90, "d61_90"),
			"2026-08-01": (91, "d91_120"),
			"2026-07-03": (120, "d91_120"),
			"2026-07-02": (121, "d120_plus"),
		}
		for due, (days, bucket) in cases.items():
			with self.subTest(due=due):
				self.assertEqual(rc.days_overdue(due, TODAY), days)
				self.assertEqual(rc.aging_bucket(days), bucket)
		self.assertEqual(rc.days_overdue(None, TODAY), 0)

	def test_aging_buckets_keep_order_and_skip_credits(self):
		result = _build([
			_row("SI-1", "C1", 100, "2026-10-20"),
			_row("SI-2", "C1", 50, "2026-11-20"),
			_row("PE-1", "C1", -70, voucher_type="Payment Entry"),
		])
		buckets = result["buckets"]
		self.assertEqual([b["key"] for b in buckets], list(rc.BUCKET_KEYS))
		by_key = {b["key"]: b for b in buckets}
		self.assertEqual((by_key["d1_30"]["value"], by_key["d1_30"]["amount"]), (1, 100))
		self.assertEqual((by_key["not_due"]["value"], by_key["not_due"]["amount"]), (1, 50))
		self.assertEqual(sum(b["amount"] for b in buckets), 150)


class TestBuildReceivables(FrappeTestCase):
	def test_groups_invoices_per_customer_most_overdue_first(self):
		result = _build([
			_row("SI-1", "SMALL", 100, "2026-10-21"),
			_row("SI-2", "BIG", 1000, "2026-11-30"),
			_row("SI-3", "BIG", 300, "2026-08-01"),
			_row("SI-4", "BIG", 200, "2026-10-01"),
		])
		customers = result["customers"]
		self.assertEqual([c["customer"] for c in customers], ["BIG", "SMALL"])
		big = customers[0]
		self.assertEqual(big["outstanding"], 1500)
		self.assertEqual(big["overdue"], 500)
		self.assertEqual(big["not_due"], 1000)
		self.assertEqual(big["invoice_count"], 3)
		self.assertEqual(big["overdue_count"], 2)
		self.assertEqual(big["oldest_days_overdue"], 91)
		self.assertEqual(big["buckets"]["d91_120"], 300)
		self.assertEqual(big["buckets"]["d1_30"], 200)
		self.assertEqual(big["buckets"]["not_due"], 1000)
		# Flat list: most overdue first.
		self.assertEqual([i["voucher_no"] for i in result["invoices"]], ["SI-3", "SI-4", "SI-1", "SI-2"])

	def test_credits_are_kept_apart(self):
		result = _build([
			_row("SI-1", "C1", 400, "2026-09-15"),
			_row("ACC-PAY-1", "C1", -100, voucher_type="Payment Entry"),
		])
		credit = next(i for i in result["invoices"] if i["voucher_no"] == "ACC-PAY-1")
		self.assertEqual(credit["kind"], "credit")
		self.assertIsNone(credit["bucket"])
		self.assertEqual(credit["days_overdue"], 0)
		self.assertEqual(result["invoices"][-1]["voucher_no"], "ACC-PAY-1")
		customer = result["customers"][0]
		self.assertEqual((customer["outstanding"], customer["overdue"], customer["credits"]), (300, 400, -100))
		self.assertEqual(customer["invoice_count"], 1)
		totals = result["totals"]
		self.assertEqual((totals["outstanding"], totals["overdue_amount"]), (300, 400))
		self.assertEqual((totals["credits_amount"], totals["credits_count"], totals["invoice_count"]), (-100, 1, 1))

	def test_rows_without_due_date_age_by_posting_date(self):
		result = _build([_row("ACC-JV-1", "C1", 30, voucher_type="Journal Entry", posting_date="2026-08-01")])
		item = result["invoices"][0]
		self.assertIsNone(item["due_date"])
		self.assertEqual((item["days_overdue"], item["bucket"]), (91, "d91_120"))

	def test_other_party_types_are_dropped(self):
		result = _build([_row("SI-1", "C1", 100, "2026-10-01"), _row("JV-9", "EMP-1", 50, party_type="Employee")])
		self.assertEqual([i["voucher_no"] for i in result["invoices"]], ["SI-1"])

	def test_contact_falls_back_from_invoice_to_primary_contact_to_customer_email(self):
		customer_details = {
			"C1": {"primary_contact": "CONT-1", "primary_contact_name": "Erika Muster", "primary_email": "erika@c1.example",
				"email_id": "office@c1.example"},
			"C2": {"email_id": "office@c2.example", "mobile_no": "+49 1"},
		}
		invoice_details = {
			"SI-1": frappe._dict(contact_person="CONT-7", contact_display="Max Muster", contact_email="max@c1.example"),
		}
		result = _build(
			[_row("SI-1", "C1", 100, "2026-10-01"), _row("SI-2", "C1", 100, "2026-10-01"), _row("SI-3", "C2", 100, "2026-10-01"),
			 _row("SI-4", "C3", 100, "2026-10-01")],
			invoice_details=invoice_details,
			customer_details=customer_details,
		)
		contacts = {i["voucher_no"]: i["contact"] for i in result["invoices"]}
		self.assertEqual((contacts["SI-1"]["name"], contacts["SI-1"]["email"], contacts["SI-1"]["source"]),
			("Max Muster", "max@c1.example", "invoice"))
		self.assertEqual((contacts["SI-2"]["name"], contacts["SI-2"]["email"], contacts["SI-2"]["source"]),
			("Erika Muster", "erika@c1.example", "primary_contact"))
		self.assertEqual((contacts["SI-3"]["email"], contacts["SI-3"]["phone"], contacts["SI-3"]["source"]),
			("office@c2.example", "+49 1", "customer"))
		self.assertIsNone(contacts["SI-4"])

	def test_contact_never_mixes_people(self):
		"""An invoice contact without email keeps no email, not the primary contact's."""
		contact = rc.pick_contact(
			{"contact_person": "CONT-7", "contact_display": "Max Muster"},
			{"primary_contact": "CONT-1", "primary_email": "erika@c1.example", "email_id": "office@c1.example"},
		)
		self.assertEqual((contact["name"], contact["email"], contact["source"]), ("Max Muster", None, "invoice"))

	def test_customer_contact_is_the_newest_invoice_contact(self):
		invoice_details = {
			"SI-OLD": frappe._dict(contact_person="A", contact_display="Old Contact", contact_email="old@x.example"),
			"SI-NEW": frappe._dict(contact_person="B", contact_display="New Contact", contact_email="new@x.example"),
		}
		result = _build(
			[_row("SI-OLD", "C1", 100, "2026-10-01", posting_date="2026-08-01"),
			 _row("SI-NEW", "C1", 100, "2026-10-20", posting_date="2026-09-20")],
			invoice_details=invoice_details,
		)
		self.assertEqual(result["customers"][0]["contact"]["name"], "New Contact")

	def test_last_contact_is_the_latest_of_email_and_dunning(self):
		self.assertIsNone(rc.latest_contact(None, None))
		self.assertEqual(rc.latest_contact("2026-10-10 09:00:00", {"date": "2026-10-01", "level": 1}),
			{"date": "2026-10-10", "kind": "email", "level": None})
		self.assertEqual(rc.latest_contact("2026-10-01", {"date": "2026-10-12", "level": 2}),
			{"date": "2026-10-12", "kind": "dunning", "level": 2})
		self.assertEqual(rc.latest_contact("2026-10-12", {"date": "2026-10-12", "level": 3})["kind"], "dunning")

		result = _build(
			[_row("SI-1", "C1", 100, "2026-10-01"), _row("SI-2", "C1", 100, "2026-10-01")],
			contact_rows={
				"SI-1": {"email_date": "2026-10-05", "dunning": None},
				"SI-2": {"email_date": None, "dunning": {"date": "2026-10-20", "level": 2}},
			},
		)
		by_no = {i["voucher_no"]: i["last_contact"] for i in result["invoices"]}
		self.assertEqual(by_no["SI-1"]["kind"], "email")
		self.assertEqual(result["customers"][0]["last_contact"], {"date": "2026-10-20", "kind": "dunning", "level": 2})

	def test_document_currency_only_for_foreign_invoices(self):
		result = _build(
			[_row("SI-EUR", "C1", 100, "2026-10-01"), _row("SI-USD", "C1", 92, "2026-10-01")],
			invoice_details={
				"SI-EUR": frappe._dict(currency="EUR", outstanding_amount=100),
				"SI-USD": frappe._dict(currency="USD", outstanding_amount=100),
			},
		)
		by_no = {i["voucher_no"]: i for i in result["invoices"]}
		self.assertIsNone(by_no["SI-EUR"]["document_currency"])
		self.assertEqual((by_no["SI-USD"]["document_currency"], by_no["SI-USD"]["document_outstanding"]), ("USD", 100))
		self.assertEqual(by_no["SI-USD"]["outstanding"], 92)

	def test_totals(self):
		result = _build([
			_row("SI-1", "C1", 100, "2026-10-01"),
			_row("SI-2", "C2", 200, "2026-06-01", customer_name="Oldie AG"),
			_row("SI-3", "C3", 300, "2026-12-01"),
		])
		totals = result["totals"]
		self.assertEqual(totals["outstanding"], 600)
		self.assertEqual((totals["overdue_amount"], totals["overdue_count"], totals["customers_overdue"]), (300, 2, 2))
		self.assertEqual((totals["not_due_amount"], totals["not_due_count"]), (300, 1))
		self.assertEqual((totals["customer_count"], totals["invoice_count"]), (3, 3))
		self.assertEqual((totals["oldest_days_overdue"], totals["oldest_customer_name"]), (152, "Oldie AG"))

	def test_empty(self):
		result = _build([])
		self.assertEqual((result["customers"], result["invoices"]), ([], []))
		self.assertEqual(result["totals"]["outstanding"], 0)
		self.assertIsNone(result["totals"]["oldest_customer_name"])


class TestEndpoint(FrappeTestCase):
	def setUp(self):
		frappe.set_user("Administrator")
		self.company = frappe.db.get_value("Company", {}, "name")
		if not self.company:
			self.skipTest("needs a company")

	def tearDown(self):
		frappe.set_user("Administrator")

	def test_endpoint_assembles_patched_queries(self):
		rows = [_row("SI-1", "C1", 250, "2026-09-20")]
		with (
			patch.object(api, "today", return_value="2026-10-31"),
			patch.object(api, "_report_rows", return_value=rows) as report_query,
			patch.object(api, "_invoice_details", return_value={}) as invoice_query,
			patch.object(api, "_customer_details", return_value={}),
			patch.object(api, "_last_contact_rows", return_value={"SI-1": {"email_date": "2026-10-02", "dunning": None}}),
		):
			result = api.get_receivables(company=self.company)
		report_query.assert_called_once_with(self.company, "2026-10-31")
		invoice_query.assert_called_once_with(["SI-1"])
		self.assertEqual(result["company"], self.company)
		self.assertEqual(result["totals"]["overdue_amount"], 250)
		self.assertEqual(result["invoices"][0]["bucket"], "d31_60")
		self.assertEqual(result["customers"][0]["last_contact"]["date"], "2026-10-02")
		self.assertIn(self.company, result["companies"])
		self.assertTrue(result["generated_at"])

	def test_requires_sales_invoice_report_permission(self):
		def denied(doctype, ptype="read", *args, **kwargs):
			return not (doctype == "Sales Invoice" and ptype == "report")

		with patch.object(api.frappe, "has_permission", side_effect=denied):
			self.assertFalse(api.can_read_receivables())
			with self.assertRaises(frappe.PermissionError):
				api.get_receivables(company=self.company)

	def test_requires_the_report_roles(self):
		from frappe.core.doctype.report.report import Report

		with patch.object(Report, "is_permitted", return_value=False):
			self.assertFalse(api.can_read_receivables())
			with self.assertRaises(frappe.PermissionError):
				api.get_receivables(company=self.company)

	def test_respects_company_permission(self):
		real = frappe.has_permission

		def denied(doctype, ptype="read", doc=None, *args, **kwargs):
			if doctype == "Company" and doc:
				return False
			return real(doctype, ptype, doc, *args, **kwargs)

		with patch.object(api.frappe, "has_permission", side_effect=denied):
			with self.assertRaises(frappe.PermissionError):
				api.get_receivables(company=self.company)

	def test_user_without_accounts_role_cannot_read(self):
		email = "receivables-no-access@example.com"
		if not frappe.db.exists("User", email):
			frappe.get_doc({"doctype": "User", "email": email, "first_name": "No Access", "send_welcome_email": 0,
				"roles": [{"role": "Projects User"}]}).insert(ignore_permissions=True)
		frappe.set_user(email)
		self.assertFalse(api.can_read_receivables())
		with self.assertRaises(frappe.PermissionError):
			api.get_receivables()


class TestSettingsFlag(FrappeTestCase):
	def test_accounting_settings_expose_can_read_receivables(self):
		from phamos.api import accounting_spa

		frappe.set_user("Administrator")
		self.assertEqual(accounting_spa.get_accounting_settings()["can_read_receivables"], 1)
		with patch.object(accounting_spa, "can_read_receivables", return_value=False):
			self.assertEqual(accounting_spa.get_accounting_settings()["can_read_receivables"], 0)


class TestReceivablesIntegration(FrappeTestCase):
	"""ERPNext's real report with one overdue Sales Invoice; everything is rolled back."""

	CUSTOMER = "_Test Receivables Customer"
	EMAIL = "erika@receivables.example"

	def setUp(self):
		from phamos.tests.marketing_fixtures import ensure_company, make_customer, make_ticket_item

		frappe.set_user("Administrator")
		self.company = ensure_company()
		self.item = make_ticket_item(rate=250)
		make_customer(self.CUSTOMER, email=self.EMAIL)
		contact = frappe.db.get_value("Dynamic Link", {"link_doctype": "Customer", "link_name": self.CUSTOMER,
			"parenttype": "Contact"}, "parent")
		frappe.db.set_value("Customer", self.CUSTOMER, "customer_primary_contact", contact)

	def tearDown(self):
		frappe.db.rollback()
		# A Fiscal Year made by _ensure_fiscal_year is rolled back; drop its cached copy too.
		frappe.cache.delete_value("fiscal_years")
		frappe.set_user("Administrator")

	def _ensure_fiscal_year(self):
		"""Today must lie in a Fiscal Year of the company, or the invoice cannot submit.

		On the bare CI site only the setup wizard's company has one; ERPNext's test records
		give `_Test Company` none for the current year.
		"""
		from erpnext.accounts.utils import FiscalYearError, get_fiscal_years

		try:
			get_fiscal_years(today(), company=self.company)
			return
		except FiscalYearError:
			pass
		year = getdate(today()).year
		frappe.get_doc({
			"doctype": "Fiscal Year",
			"year": f"Receivables Test {year}",
			"year_start_date": f"{year}-01-01",
			"year_end_date": f"{year}-12-31",
			"companies": [{"company": self.company}],
		}).insert(ignore_permissions=True)
		frappe.cache.delete_value("fiscal_years")

	def _make_invoice(self):
		self._ensure_fiscal_year()
		company = frappe.get_cached_doc("Company", self.company)
		income_account = company.default_income_account or frappe.db.get_value(
			"Account", {"company": self.company, "root_type": "Income", "is_group": 0}, "name")
		invoice = frappe.get_doc({
			"doctype": "Sales Invoice",
			"company": self.company,
			"customer": self.CUSTOMER,
			"currency": company.default_currency,
			"conversion_rate": 1,
			"debit_to": company.default_receivable_account,
			"items": [{"item_code": self.item, "qty": 1, "rate": 250, "income_account": income_account,
				"cost_center": company.cost_center}],
		})
		invoice.insert(ignore_permissions=True)
		invoice.submit()
		return invoice

	def test_overdue_invoice_appears_with_bucket_contact_and_last_contact(self):
		invoice = self._make_invoice()
		frappe.db.set_value("Sales Invoice", invoice.name, "due_date", add_days(today(), -40))
		frappe.get_doc({
			"doctype": "Communication",
			"communication_type": "Communication",
			"communication_medium": "Email",
			"sent_or_received": "Sent",
			"subject": "Payment reminder",
			"content": "Please pay.",
			"reference_doctype": "Sales Invoice",
			"reference_name": invoice.name,
			"communication_date": add_days(today(), -5),
		}).insert(ignore_permissions=True)

		result = api.get_receivables(company=self.company)

		item = next(i for i in result["invoices"] if i["voucher_no"] == invoice.name)
		self.assertEqual(item["kind"], "invoice")
		self.assertEqual(item["outstanding"], flt(invoice.base_grand_total, 2))
		self.assertEqual((item["days_overdue"], item["bucket"]), (40, "d31_60"))
		self.assertEqual(item["contact"]["email"], self.EMAIL)
		self.assertEqual(item["last_contact"], {"date": str(getdate(add_days(today(), -5))), "kind": "email", "level": None})
		customer = next(c for c in result["customers"] if c["customer"] == self.CUSTOMER)
		self.assertEqual(customer["overdue"], flt(invoice.base_grand_total, 2))
		self.assertGreaterEqual(result["totals"]["overdue_amount"], customer["overdue"])
