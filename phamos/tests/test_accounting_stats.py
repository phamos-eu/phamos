# Copyright (c) 2026, phamos.eu and contributors
# For license information, please see license.txt

"""Accounting Cockpit statistics and payment calendar (#1369): spike rules, comparison
windows, dashboard assembly with patched queries and calendar grouping."""

from datetime import date
from unittest.mock import patch

import frappe
from frappe.tests.utils import FrappeTestCase

from phamos.accounting import statistics as st
from phamos.api import accounting_stats as stats


class TestSpikeDetection(FrappeTestCase):
	def test_flat_series_has_no_spikes(self):
		self.assertEqual(st.detect_spikes([1000] * 12), [None] * 12)

	def test_peak_against_sigma_and_avg3(self):
		series = [1000, 1100, 900, 1000, 1050, 950, 1000, 1000, 5000, 1000, 1100, 1000]
		spikes = st.detect_spikes(series)
		self.assertEqual(spikes[8]["kind"], "peak")
		self.assertIn("sigma", spikes[8]["reasons"])
		self.assertIn("avg3", spikes[8]["reasons"])
		self.assertEqual([i for i, s in enumerate(spikes) if s], [8])

	def test_avg3_rule_alone(self):
		# Rising costs: the jump from ~1000 to 1600 is > 1.5 × avg3 but within 2σ of a volatile year.
		series = [3000, 200, 2800, 300, 2500, 400, 1000, 1000, 1000, 1600, 2000, 2200]
		spikes = st.detect_spikes(series)
		self.assertEqual(spikes[9]["reasons"], ["avg3"])

	def test_same_month_last_year_marks_recurring(self):
		year1 = [1000] * 12
		year2 = [1000] * 12
		year1[2] = 4000  # March insurance last year
		year2[2] = 4400  # +10 % this year → recurring
		year2[7] = 4000  # August is new → peak
		spikes = st.detect_spikes(year1 + year2)
		self.assertIsNone(spikes[2], "history months are not judged")
		self.assertEqual(spikes[14]["kind"], "recurring")
		self.assertEqual(spikes[14]["last_year"], 4000)
		self.assertEqual(spikes[19]["kind"], "peak")

	def test_recurring_needs_last_year_within_twenty_percent(self):
		year1 = [1000] * 12
		year1[2] = 3000
		year2 = [1000] * 12
		year2[2] = 4000  # +33 % → still a peak
		self.assertEqual(st.detect_spikes(year1 + year2)[14]["kind"], "peak")

	def test_min_points_keeps_young_series_quiet(self):
		series = [0, 0, 0, 0, 0, 0, 0, 100, 100, 100, 100, 900]
		self.assertEqual(st.detect_spikes(series), [None] * 12)
		self.assertTrue(st.detect_spikes(series, min_points=5)[11])

	def test_min_amount_ignores_small_months(self):
		series = [10, 10, 10, 10, 10, 10, 10, 10, 10, 10, 10, 80]
		self.assertTrue(st.detect_spikes(series)[11])
		self.assertIsNone(st.detect_spikes(series, min_amount=100)[11])


class TestWindows(FrappeTestCase):
	def test_month_windows_cross_the_year(self):
		windows = st.month_windows(date(2026, 2, 10), months=4)
		self.assertEqual([w["start"] for w in windows], [date(2025, 11, 1), date(2025, 12, 1), date(2026, 1, 1), date(2026, 2, 1)])
		self.assertEqual(windows[-1]["end"], date(2026, 3, 1))
		self.assertTrue(windows[-1]["mtd"])
		self.assertEqual(windows[0]["label"], "Nov 2025")
		self.assertEqual(windows[2]["label"], "Jan 2026")
		self.assertEqual(windows[1]["label"], "Dec")

	def test_comparison_windows_in_january(self):
		w = st.comparison_windows(date(2026, 1, 16))
		self.assertEqual((w["current"]["start"], w["current"]["end"]), (date(2026, 1, 1), date(2026, 1, 17)))
		self.assertEqual((w["previous_to_date"]["start"], w["previous_to_date"]["end"]), (date(2025, 12, 1), date(2025, 12, 17)))
		self.assertEqual(w["previous_to_date"]["label"], "1–16 Dec")
		self.assertEqual((w["previous"]["start"], w["previous"]["end"]), (date(2025, 12, 1), date(2026, 1, 1)))
		self.assertEqual((w["avg3"]["start"], w["avg3"]["end"], w["avg3"]["divisor"]), (date(2025, 10, 1), date(2026, 1, 1), 3))
		self.assertEqual(w["avg3"]["label"], "Oct–Dec avg")
		self.assertEqual((w["last_year"]["start"], w["last_year"]["end"]), (date(2025, 1, 1), date(2025, 2, 1)))

	def test_previous_to_date_is_capped_at_month_end(self):
		w = st.comparison_windows(date(2026, 3, 31))
		self.assertEqual(w["previous_to_date"]["end"], date(2026, 3, 1))
		self.assertEqual(w["previous_to_date"]["label"], "1–28 Feb")

	def test_aging_buckets(self):
		today = date(2026, 10, 16)
		rows = [
			{"due_date": date(2026, 9, 1), "amount": 10},
			{"due_date": date(2026, 10, 15), "amount": 20},
			{"due_date": date(2026, 10, 16), "amount": 30},
			{"due_date": date(2026, 10, 23), "amount": 40},
			{"due_date": date(2026, 10, 24), "amount": 50},
			{"due_date": date(2026, 12, 1), "amount": 60},
			{"due_date": None, "amount": 70},
		]
		buckets = {b["key"]: (b["value"], b["amount"]) for b in st.aging_buckets(rows, today)}
		self.assertEqual(
			buckets,
			{"overdue_30": (1, 10), "overdue": (1, 20), "due_7": (2, 70), "due_30": (1, 50), "later": (1, 60), "none": (1, 70)},
		)

	def test_iso_weeks_across_year_end(self):
		weeks = st.iso_weeks(date(2026, 12, 28), date(2027, 1, 10))
		self.assertEqual([w["key"] for w in weeks], ["2026-W53", "2027-W01"])
		self.assertEqual(weeks[0]["start"], date(2026, 12, 28))


def _dashboard(receipts, gl=(), open_rows=(), today_date=date(2026, 10, 16), **extra):
	return stats.build_dashboard(
		company="Test Co",
		currency="EUR",
		abbr="TC",
		today_date=today_date,
		months=12,
		receipts=list(receipts),
		gl=list(gl),
		open_rows=list(open_rows),
		status_rows=extra.get("status_rows", []),
		waiting_rows=extra.get("waiting_rows", []),
		ai_rows=extra.get("ai_rows"),
	)


def _monthly_receipts(amounts_by_month, supplier="SUP-1", day=10):
	"""One row per (year, month) → amount."""
	return [
		{"posting_date": date(y, m, day), "supplier": supplier, "supplier_name": supplier, "count": 1, "amount": amount}
		for (y, m), amount in amounts_by_month.items()
	]


class TestDashboardAssembly(FrappeTestCase):
	def test_monthly_series_windows_and_peaks(self):
		months = [(2025, m) for m in range(1, 13)] + [(2026, m) for m in range(1, 11)]
		amounts = {key: 1000 for key in months}
		amounts[(2026, 6)] = 6000
		receipts = _monthly_receipts(amounts)
		receipts += _monthly_receipts({(2026, 6): 500}, supplier="SUP-2", day=12)
		receipts.append({"posting_date": date(2026, 9, 20), "supplier": "SUP-1", "supplier_name": "SUP-1", "count": 2, "amount": 50})
		gl = [
			{"posting_date": date(2026, 10, 3), "voucher_type": "Purchase Invoice", "account": "4930 Office - TC", "cost_center": "Main - TC", "amount": 300},
			{"posting_date": date(2026, 10, 4), "voucher_type": "Journal Entry", "account": "4120 Wages - TC", "cost_center": "Main - TC", "amount": 200},
			{"posting_date": date(2026, 10, 5), "voucher_type": "Expense Claim", "account": "4660 Travel - TC", "cost_center": None, "amount": 50},
		]
		result = _dashboard(receipts, gl)

		self.assertEqual(len(result["monthly"]), 12)
		self.assertEqual(result["monthly"][0]["start"], "2025-11-01")
		october = result["monthly"][-1]
		self.assertTrue(october["mtd"])
		self.assertEqual((october["booked_pi"], october["booked_je"]), (300, 250))
		self.assertEqual(october["last_year_sum"], 1000)

		june = next(m for m in result["monthly"] if m["start"] == "2026-06-01")
		self.assertEqual(june["spike"]["kind"], "peak")
		self.assertEqual([s["supplier"] for s in june["spike"]["top_suppliers"]], ["SUP-1", "SUP-2"])
		self.assertEqual(len(result["peaks"]), 1)
		self.assertEqual(result["peaks"][0]["route"], {"path": "/receipts", "query": {"from": "2026-06-01", "to": "2026-06-30"}})
		self.assertIsNone(october["spike"], "the running month is never judged")

		windows = result["windows"]
		self.assertEqual(windows["current"]["receipts_sum"], 1000)
		self.assertEqual(windows["previous_to_date"]["receipts_sum"], 1000)  # the 20 Sep rows fall after the cut
		self.assertEqual(windows["previous"]["receipts_sum"], 1050)
		self.assertEqual(windows["previous"]["receipts_count"], 3)
		self.assertEqual(windows["avg3"]["receipts_sum"], 1016.67)
		self.assertEqual(windows["last_year"]["receipts_sum"], 1000)
		self.assertEqual(windows["current"]["booked"], 550)

		self.assertEqual([r["label"] for r in result["by_expense_account"]], ["4930 Office", "4120 Wages", "4660 Travel"])
		self.assertEqual(result["by_cost_center"][0], {"key": "Main - TC", "label": "Main", "value": 500})
		self.assertEqual(result["top_suppliers"][0]["key"], "SUP-1")

	def test_returns_and_open_to_pay(self):
		open_rows = [
			{"name": "AR-1", "due_date": date(2026, 10, 1), "amount": 100},
			{"name": "AR-2", "due_date": date(2026, 10, 20), "amount": 200},
			{"name": "AR-3", "due_date": None, "amount": 300},
		]
		waiting = [
			{"name": "AR-4", "status": "Needs Decision", "created": date(2026, 10, 6)},
			{"name": "AR-5", "status": "Needs Decision", "created": date(2026, 10, 14)},
			{"name": "AR-6", "status": "Inbox", "created": date(2026, 10, 15)},
		]
		status_rows = [{"status": "Paid", "count": 4, "amount": 10}, {"status": "Inbox", "count": 1, "amount": 5}]
		result = _dashboard([], open_rows=open_rows, waiting_rows=waiting, status_rows=status_rows)
		self.assertEqual(result["open_to_pay"], {"count": 3, "amount": 600, "overdue_count": 1, "overdue_amount": 100})
		self.assertEqual(result["queue"], {"needs_decision": 2, "inbox": 1, "oldest_days": 10, "median_days": 2})
		self.assertEqual([s["key"] for s in result["status"]], ["Inbox", "Paid"])
		self.assertEqual(result["ai"], {"available": False})
		self.assertEqual(result["peaks"], [])

	def test_endpoint_uses_patched_queries_and_caches(self):
		frappe.set_user("Administrator")
		company = frappe.db.get_value("Company", {}, "name")
		if not company:
			self.skipTest("needs a company")
		frappe.cache.delete_keys("phamos:accounting_stats:")
		rows = _monthly_receipts({(2026, 10): 123})
		with (
			patch.object(stats, "today", return_value="2026-10-16"),
			patch.object(stats, "_receipt_rows", return_value=rows) as receipt_query,
			patch.object(stats, "_gl_rows", return_value=[]),
			patch.object(stats, "_open_receipt_rows", return_value=[]),
			patch.object(stats, "_status_rows", return_value=[]),
			patch.object(stats, "_waiting_rows", return_value=[]),
			patch.object(stats, "_ai_rows", return_value=None),
		):
			first = stats.get_receipt_dashboard(company=company)
			second = stats.get_receipt_dashboard(company=company)
		self.assertEqual(first["monthly"][-1]["receipts_sum"], 123)
		self.assertEqual(second, first)
		self.assertEqual(receipt_query.call_count, 1)
		start, end = receipt_query.call_args.args[1:]
		self.assertEqual((str(start), str(end)), ("2024-11-01", "2026-10-17"))
		frappe.cache.delete_keys("phamos:accounting_stats:")

	def test_endpoint_requires_gl_entry_read(self):
		with patch.object(stats.frappe, "has_permission", side_effect=lambda doctype, *a, **k: doctype != "GL Entry"):
			self.assertFalse(stats.can_read_statistics())
			with self.assertRaises(frappe.PermissionError):
				stats.get_receipt_dashboard()


class TestSettingsFlag(FrappeTestCase):
	def test_accounting_settings_expose_can_read_statistics(self):
		from phamos.api import accounting_spa

		frappe.set_user("Administrator")
		self.assertEqual(accounting_spa.get_accounting_settings()["can_read_statistics"], 1)
		with patch.object(stats, "can_read_statistics", return_value=False), patch.object(
			accounting_spa, "can_read_statistics", return_value=False
		):
			self.assertEqual(accounting_spa.get_accounting_settings()["can_read_statistics"], 0)


class TestCompanyAccess(FrappeTestCase):
	def test_endpoints_respect_company_permission(self):
		frappe.set_user("Administrator")
		company = frappe.db.get_value("Company", {}, "name")
		if not company:
			self.skipTest("needs a company")
		denied = lambda doctype, *args, **kwargs: doctype != "Company"  # noqa: E731
		with patch.object(stats.frappe, "has_permission", side_effect=denied):
			with self.assertRaises(frappe.PermissionError):
				stats.get_receipt_dashboard(company=company)
			with self.assertRaises(frappe.PermissionError):
				stats.get_payment_calendar("2026-10-01", "2026-10-31", company=company)


class TestPaymentRequestAmount(FrappeTestCase):
	def test_same_currency_is_unchanged(self):
		self.assertEqual(stats.payment_request_amount({"grand_total": 120, "currency": "EUR"}, "EUR"), 120)

	def test_uses_the_invoice_rate_when_the_currencies_match(self):
		row = {"grand_total": 100, "currency": "USD", "invoice_currency": "USD", "invoice_conversion_rate": 0.9}
		with patch.object(stats, "get_exchange_rate") as rate:
			self.assertAlmostEqual(stats.payment_request_amount(row, "EUR"), 90)
		rate.assert_not_called()

	def test_falls_back_to_the_exchange_rate_of_the_request_date(self):
		row = {"grand_total": 100, "currency": "USD", "transaction_date": date(2026, 10, 1)}
		with patch.object(stats, "get_exchange_rate", return_value=0.8) as rate:
			self.assertAlmostEqual(stats.payment_request_amount(row, "EUR"), 80)
		rate.assert_called_once_with("USD", "EUR", date(2026, 10, 1))

	def test_calendar_totals_are_in_company_currency(self):
		row = {"name": "PR-USD", "party_name": "Wise", "reference_doctype": "Purchase Invoice", "reference_name": "PI-7",
		       "transaction_date": date(2026, 10, 1), "invoice_due_date": date(2026, 10, 20), "grand_total": 100,
		       "currency": "USD", "invoice_currency": "USD", "invoice_conversion_rate": 0.9, "status": "Initiated"}
		result = stats.build_calendar(
			from_date=date(2026, 10, 1), to_date=date(2026, 10, 31), today_date=date(2026, 10, 16),
			receipt_rows=[], payment_request_rows=[row], currency="EUR",
		)
		self.assertEqual((result["items"][0]["amount"], result["items"][0]["document_amount"]), (90, 100))
		self.assertEqual(result["totals"]["amount"], 90)


class TestPaymentRequestQuery(FrappeTestCase):
	"""Requests already represented by a receipt are left out by the query itself."""

	def setUp(self):
		frappe.set_user("Administrator")
		self.company = frappe.db.get_value("Company", {}, "name")
		if not self.company:
			self.skipTest("needs a company")
		self.addCleanup(frappe.db.rollback)
		frappe.get_doc({"doctype": "Accounting Receipt", "name": "TEST-STATS-AR-1", "company": self.company,
		                "status": "Approved to Pay", "purchase_invoice": "TEST-STATS-PI-1"}).db_insert()
		frappe.get_doc({"doctype": "Accounting Receipt", "name": "TEST-STATS-AR-2", "company": self.company,
		                "status": "Approved to Pay"}).db_insert()
		for name, doctype, reference in (
			("TEST-STATS-PR-VIA-PI", "Purchase Invoice", "TEST-STATS-PI-1"),
			("TEST-STATS-PR-VIA-AR", "Accounting Receipt", "TEST-STATS-AR-2"),
			("TEST-STATS-PR-OWN", "Purchase Invoice", "TEST-STATS-PI-2"),
		):
			frappe.get_doc({"doctype": "Payment Request", "name": name, "company": self.company, "docstatus": 1,
			                "payment_request_type": "Outward", "status": "Initiated", "reference_doctype": doctype,
			                "reference_name": reference, "grand_total": 10, "currency": "EUR",
			                "transaction_date": "2026-10-01"}).db_insert()

	def test_requests_with_a_receipt_are_left_out(self):
		names = {row.name for row in stats._payment_request_rows(self.company) if row.name.startswith("TEST-STATS-")}
		self.assertEqual(names, {"TEST-STATS-PR-OWN"})


class TestPaymentCalendar(FrappeTestCase):
	def test_grouping(self):
		receipts = [
			{"name": "AR-1", "supplier_name": "Telekom", "status": "Approved to Pay", "due_date": date(2026, 10, 20), "amount": 50, "sum": 50},
			{"name": "AR-2", "supplier_name": "Allianz", "status": "Sent to DATEV", "due_date": date(2026, 10, 20), "amount": 400, "sum": 400},
			{"name": "AR-3", "supplier_name": "Hetzner", "status": "Approved to Pay", "due_date": date(2026, 10, 2), "amount": 30, "sum": 30},
			{"name": "AR-4", "supplier_name": "Apple", "status": "Approved to Pay", "due_date": None, "amount": 99, "sum": 99},
			{"name": "AR-5", "supplier_name": "Old", "status": "Approved to Pay", "due_date": date(2026, 8, 1), "amount": 10, "sum": 10},
		]
		payment_requests = [
			{"name": "PR-1", "party_type": None, "party": None, "party_name": None, "invoice_supplier": "S1", "invoice_supplier_name": "Wise", "reference_doctype": "Purchase Invoice",
			 "reference_name": "PI-9", "transaction_date": date(2026, 10, 1), "invoice_due_date": date(2026, 10, 27), "grand_total": 70, "status": "Initiated"},
		]
		result = stats.build_calendar(
			from_date=date(2026, 10, 1),
			to_date=date(2026, 10, 31),
			today_date=date(2026, 10, 16),
			receipt_rows=receipts,
			payment_request_rows=payment_requests,
			currency="EUR",
		)
		self.assertEqual([i["name"] for i in result["items"]], ["AR-3", "AR-2", "AR-1", "PR-1"])
		self.assertEqual([i["name"] for i in result["undated"]], ["AR-4"])
		self.assertEqual(result["totals_by_day"]["2026-10-20"], {"count": 2, "amount": 450})
		self.assertEqual(result["totals"], {"count": 4, "amount": 550})
		self.assertEqual(result["overdue"]["count"], 2)
		self.assertEqual(result["overdue"]["amount"], 40)
		self.assertEqual(result["overdue"]["items"][0]["days_overdue"], 76)
		self.assertEqual([w["key"] for w in result["weeks"]], ["2026-W40", "2026-W41", "2026-W42", "2026-W43", "2026-W44"])
		self.assertEqual(next(w for w in result["weeks"] if w["key"] == "2026-W43")["amount"], 450)
		self.assertEqual(result["items"][-1]["kind"], "payment_request")
		self.assertEqual((result["items"][-1]["title"], result["items"][-1]["supplier"]), ("Wise", "S1"))

	def test_range_is_validated(self):
		frappe.set_user("Administrator")
		with self.assertRaises(frappe.ValidationError):
			stats.get_payment_calendar("2026-10-31", "2026-10-01")
		with self.assertRaises(frappe.ValidationError):
			stats.get_payment_calendar("2026-01-01", "2026-12-31")
