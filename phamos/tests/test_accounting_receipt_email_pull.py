# Copyright (c) 2026, phamos.eu and contributors
# For license information, please see license.txt

"""The "Fetch e-mails" button on the receipt lists (#1964). No real mail server: enqueue,
the job list and the pull itself are patched."""

from unittest.mock import patch

import frappe
from frappe.tests.utils import FrappeTestCase
from frappe.utils import add_to_date, now_datetime

from phamos.accounting import email_pull

MODULE = "phamos.accounting.email_pull"


class TestFetchReceiptEmails(FrappeTestCase):
	def setUp(self):
		frappe.set_user("Administrator")
		self.receipt_account = self.make_account("_Test Receipt Inbox", "Accounting Receipt")
		self.issue_account = self.make_account("_Test Support Inbox", "Issue")

	def tearDown(self):
		frappe.set_user("Administrator")
		frappe.db.rollback()

	def make_account(self, name, append_to, enable_incoming=1):
		"""An IMAP account whose single folder creates `append_to` documents.

		Inserted through the DB so Email Account's validate doesn't log in to a mail server.
		"""
		frappe.db.delete("Email Account", {"name": name})
		frappe.db.delete("IMAP Folder", {"parent": name})
		account = frappe.new_doc("Email Account")
		account.name = name
		account.update(
			{
				"email_account_name": name,
				"email_id": f"{frappe.scrub(name)}@example.com",
				"enable_incoming": enable_incoming,
				"use_imap": 1,
				"awaiting_password": 0,
				"auth_method": "Basic",
			}
		)
		account.append("imap_folder", {"folder_name": "INBOX", "append_to": append_to})
		account.db_insert()
		for row in account.imap_folder:
			row.db_insert()
		return name

	def fetch(self, queued_jobs=()):
		with (
			patch(f"{MODULE}.get_jobs", return_value={frappe.local.site: list(queued_jobs)}),
			patch(f"{MODULE}.frappe.enqueue") as enqueue,
		):
			result = email_pull.fetch_receipt_emails()
		return result, enqueue

	def test_queues_only_accounts_that_deliver_to_receipts(self):
		result, enqueue = self.fetch()
		self.assertIn(self.receipt_account, result["queued"])
		self.assertNotIn(self.issue_account, result["queued"])
		job_names = [c.kwargs["job_name"] for c in enqueue.call_args_list]
		self.assertIn(f"pull_from_email_account|{self.receipt_account}", job_names)
		self.assertNotIn(f"pull_from_email_account|{self.issue_account}", job_names)
		call = next(c for c in enqueue.call_args_list if c.kwargs["email_account"] == self.receipt_account)
		self.assertEqual(call.args[0], "phamos.accounting.email_pull.pull_and_notify")
		self.assertEqual(call.kwargs["queue"], "short")
		self.assertEqual(call.kwargs["user"], "Administrator")

	def test_account_with_queued_pull_is_not_queued_twice(self):
		result, enqueue = self.fetch(queued_jobs=[f"pull_from_email_account|{self.receipt_account}"])
		self.assertIn(self.receipt_account, result["running"])
		self.assertNotIn(self.receipt_account, result["queued"])
		self.assertFalse([c for c in enqueue.call_args_list if c.kwargs["email_account"] == self.receipt_account])

	def test_disabled_incoming_account_is_skipped(self):
		frappe.db.set_value("Email Account", self.receipt_account, "enable_incoming", 0)
		self.assertNotIn(self.receipt_account, email_pull.receipt_email_accounts())

	def test_pop3_account_append_to_counts(self):
		frappe.db.delete("IMAP Folder", {"parent": self.receipt_account})
		frappe.db.set_value("Email Account", self.receipt_account, {"use_imap": 0, "append_to": "Accounting Receipt"})
		self.assertIn(self.receipt_account, email_pull.receipt_email_accounts())

	def test_no_account_explains_whom_to_ask(self):
		frappe.db.delete("IMAP Folder", {"append_to": "Accounting Receipt"})
		frappe.db.set_value("Email Account", {"append_to": "Accounting Receipt"}, "append_to", None)
		with self.assertRaises(frappe.ValidationError) as ctx:
			self.fetch()
		self.assertIn("administrator", str(ctx.exception))

	def test_user_without_create_permission_is_refused(self):
		user = "test-no-receipts@example.com"
		if not frappe.db.exists("User", user):
			frappe.get_doc({"doctype": "User", "email": user, "first_name": "No Receipts", "send_welcome_email": 0}).insert()
		frappe.set_user(user)
		with self.assertRaises(frappe.PermissionError):
			self.fetch()

	def test_job_tells_the_clicking_user_how_many_receipts_arrived(self):
		since = add_to_date(now_datetime(), seconds=-1)
		frappe.set_user("Guest")  # the worker starts as the clicking user
		with (
			patch(f"{MODULE}.pull_from_email_account") as pull,
			patch(f"{MODULE}.receipts_created", return_value=2) as count,
			patch(f"{MODULE}.frappe.publish_realtime") as publish,
		):
			email_pull.pull_and_notify(self.receipt_account, "someone@example.com", since)
		pull.assert_called_once_with(self.receipt_account)
		self.assertEqual(frappe.session.user, "Administrator")  # like the scheduler, not the clicking user
		count.assert_called_once_with(self.receipt_account, since)
		publish.assert_called_once_with(
			"receipt_emails_fetched", {"email_account": self.receipt_account, "created": 2}, user="someone@example.com"
		)

	def test_job_reports_a_failed_pull(self):
		with (
			patch(f"{MODULE}.pull_from_email_account", side_effect=Exception("bad mail")),
			patch(f"{MODULE}.frappe.db.rollback"),
			patch(f"{MODULE}.frappe.log_error") as log_error,
			patch(f"{MODULE}.frappe.publish_realtime") as publish,
		):
			email_pull.pull_and_notify(self.receipt_account, "someone@example.com", now_datetime())
		log_error.assert_called_once()
		payload = publish.call_args.args[1]
		self.assertIn("error", payload)
		self.assertNotIn("created", payload)
		self.assertEqual(publish.call_args.kwargs["user"], "someone@example.com")

	def test_count_only_new_receipts_from_this_account(self):
		since = add_to_date(now_datetime(), seconds=-5)
		older = add_to_date(since, days=-1)
		new_here = self.make_receipt()
		new_other = self.make_receipt()
		old_reply = self.make_receipt(creation=older)
		self.make_mail(self.receipt_account, new_here)
		self.make_mail(self.receipt_account, new_here)  # a second mail on the same receipt
		self.make_mail(self.issue_account, new_other)
		self.make_mail(self.receipt_account, old_reply)
		self.assertEqual(email_pull.receipts_created(self.receipt_account, since), 1)
		self.assertEqual(email_pull.receipts_created(self.issue_account, since), 1)

	def make_receipt(self, creation=None):
		doc = frappe.new_doc("Accounting Receipt")
		doc.name = frappe.generate_hash(length=10)
		doc.title = "Mail receipt"
		doc.db_insert()
		if creation:
			frappe.db.set_value("Accounting Receipt", doc.name, "creation", creation, update_modified=False)
		return doc.name

	def make_mail(self, account, receipt):
		comm = frappe.new_doc("Communication")
		comm.update(
			{
				"communication_type": "Communication",
				"communication_medium": "Email",
				"sent_or_received": "Received",
				"email_account": account,
				"reference_doctype": "Accounting Receipt",
				"reference_name": receipt,
				"subject": "Invoice",
			}
		)
		comm.name = frappe.generate_hash(length=10)
		comm.db_insert()
