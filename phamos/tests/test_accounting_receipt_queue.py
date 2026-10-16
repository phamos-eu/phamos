# Copyright (c) 2026, phamos.eu and contributors
# For license information, please see license.txt

"""Work queue (grouped by next action), the filterable receipt list and bulk DATEV sending."""

from unittest.mock import patch

import frappe
from frappe.tests.utils import FrappeTestCase

from phamos.api import accounting_receipts as api


def row(**values):
	base = dict(name="AR-X", status="Inbox", attachment="/private/files/a.pdf", is_paid=0, sent_to_datev=0,
		supplier="S", sum=100, posting_date="2026-10-01", ai_confidence=95, receipt_type="Invoice")
	base.update(values)
	return frappe._dict(base)


RUN_OK = {"status": "Completed", "flags": []}


class TestNextAction(FrappeTestCase):
	def test_clear_open_receipt_is_ready(self):
		self.assertEqual(api.next_action(row(), RUN_OK), ("ready", []))

	def test_missing_data_and_flags_need_a_decision_with_reasons(self):
		section, reasons = api.next_action(
			row(supplier=None, ai_confidence=70),
			{"status": "Completed", "flags": [{"severity": "warn", "message": "Supplier X is not in the system yet."}, {"severity": "info", "message": "ignore me"}]},
		)
		self.assertEqual(section, "decide")
		self.assertEqual(reasons[0], "Supplier X is not in the system yet.")
		self.assertIn("No supplier", reasons)
		self.assertIn("The AI is unsure (70 %)", reasons)
		self.assertNotIn("ignore me", reasons)

	def test_unread_receipt_and_non_vouchers_need_a_decision(self):
		self.assertEqual(api.next_action(row(), None)[0], "decide")
		self.assertIn("Reminder: not a voucher", api.next_action(row(receipt_type="Reminder"), RUN_OK)[1])

	def test_problems_come_before_everything(self):
		self.assertEqual(api.next_action(row(attachment=""), RUN_OK)[0], "problems")
		self.assertEqual(api.next_action(row(), {"status": "Failed", "flags": []})[0], "problems")

	def test_payment_and_datev_states(self):
		self.assertEqual(api.next_action(row(status="Approved to Pay"), RUN_OK)[0], "ready")
		self.assertEqual(api.next_action(row(status="Approved to Pay", sent_to_datev=1), RUN_OK)[0], "waiting")
		self.assertEqual(api.next_action(row(status="Sent to DATEV", sent_to_datev=1), RUN_OK)[0], "waiting")
		self.assertEqual(api.next_action(row(status="Inbox", sent_to_datev=1), RUN_OK)[0], "waiting")
		self.assertEqual(api.next_action(row(status="Paid", is_paid=1), RUN_OK)[0], "ready")
		self.assertEqual(api.next_action(row(status="Do Not Pay", sent_to_datev=1), RUN_OK), (None, []))
		self.assertEqual(api.next_action(row(status="Paid", is_paid=1, sent_to_datev=1), RUN_OK), (None, []))
		self.assertEqual(api.next_action(row(status="Cancelled"), RUN_OK), (None, []))

	def test_sort_puts_overdue_first_then_due_date_then_amount(self):
		items = [
			{"name": "late", "overdue_days": 3, "due_date": "2026-10-01", "sum": 10, "posting_date": "2026-09-01"},
			{"name": "big", "overdue_days": 0, "due_date": None, "sum": 900, "posting_date": "2026-10-02"},
			{"name": "small", "overdue_days": 0, "due_date": None, "sum": 5, "posting_date": "2026-10-01"},
			{"name": "soon", "overdue_days": 0, "due_date": "2026-10-20", "sum": 1, "posting_date": "2026-10-03"},
		]
		self.assertEqual([i["name"] for i in sorted(items, key=api._sort_key)], ["late", "soon", "big", "small"])


class TestQueueAndList(FrappeTestCase):
	def setUp(self):
		frappe.set_user("Administrator")

	def tearDown(self):
		frappe.db.rollback()

	def make(self, **values):
		return frappe.get_doc({"doctype": "Accounting Receipt", "title": "Queue test", "currency": "EUR", "conversion_rate": 1, **values}).insert(ignore_permissions=True)

	def test_queue_groups_receipts_and_counts_overdue(self):
		no_pdf = self.make()
		waiting = self.make(attachment="/private/files/q.pdf", status="Sent to DATEV", due_date="2020-01-01")
		done = self.make(attachment="/private/files/d.pdf", status="Paid", is_paid=1)
		for doc in (waiting, done):  # before_insert resets the DATEV flag
			doc.db_set("sent_to_datev", 1)
		queue = api.get_receipt_queue()
		where = {item["name"]: s["key"] for s in queue["sections"] for item in s["items"]}
		self.assertEqual(where[no_pdf.name], "problems")
		self.assertEqual(where[waiting.name], "waiting")
		self.assertNotIn(done.name, where)
		self.assertGreaterEqual(queue["overdue"], 1)
		self.assertEqual([s["key"] for s in queue["sections"]], ["decide", "ready", "waiting", "problems"])

	def test_list_filters_and_truncates(self):
		a = self.make(title="Zebra Hosting Oktober", posting_date="2026-10-05", receipt_type="Invoice")
		self.make(title="Something else", posting_date="2026-01-05")
		result = api.list_receipts(search="Zebra Hosting", from_date="2026-10-01", to_date="2026-10-31")
		self.assertEqual([i["name"] for i in result["items"]], [a.name])
		self.assertEqual(api.list_receipts(receipt_type="Invoice", search="Zebra")["items"][0]["name"], a.name)
		self.assertTrue(api.list_receipts(limit=1)["truncated"])

	def test_bulk_send_reports_each_result(self):
		with patch(
			"phamos.phamos.doctype.accounting_receipt.accounting_receipt.send_to_datev",
			side_effect=[{"ok": True}, {"ok": False, "message": "PDF missing"}],
		):
			result = api.send_receipts_to_datev(["AR-1", "AR-2"])
		self.assertEqual(result, {"sent": ["AR-1"], "failed": [{"name": "AR-2", "message": "PDF missing"}]})
