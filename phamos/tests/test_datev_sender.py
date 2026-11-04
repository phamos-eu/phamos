# Copyright (c) 2026, phamos.eu and contributors
# For license information, please see license.txt

"""DATEV send: the sender is always the user's own outgoing Email Account (#1820)."""

from unittest.mock import MagicMock, patch

import frappe
from frappe.tests.utils import FrappeTestCase

from phamos.phamos.doctype.accounting_receipt import accounting_receipt as ar_module


def _email_account(email_id, enable_outgoing=1, default_outgoing=0):
	# db_insert skips Email Account.validate, which would try to log in to the mail server.
	frappe.get_doc({"doctype": "Email Account", "email_account_name": f"DATEV test {email_id}", "email_id": email_id,
		"enable_outgoing": enable_outgoing, "default_outgoing": default_outgoing}).db_insert()


def _receipt():
	# The receipt's fields differ between branches; send_to_datev only reads these.
	return frappe._dict(name="AR-TEST", title="Test", receipt_type="Rechnung", attachment="/private/files/r.pdf",
		datev_mail_recipient="up@datev.test", datev_mail_recipient_2=None, sent_to_datev=0,
		datev_email_queue_ref=None, db_set=MagicMock())


class TestDatevSender(FrappeTestCase):
	def setUp(self):
		frappe.set_user("Administrator")
		self.email = frappe.db.get_value("User", "Administrator", "email")
		frappe.db.delete("Email Account", {"email_id": self.email})
		_email_account("default@phamos.test", default_outgoing=1)

	def tearDown(self):
		frappe.set_user("Administrator")
		frappe.db.rollback()

	def _send(self):
		with patch.object(ar_module.frappe.db, "exists", return_value=True), \
			patch.object(ar_module.frappe, "get_doc", return_value=_receipt()), \
			patch.object(ar_module.frappe, "sendmail") as sendmail:
			return ar_module.send_to_datev("AR-TEST"), sendmail

	def test_sender_is_the_users_own_outgoing_account(self):
		_email_account(self.email)
		self.assertEqual(ar_module.resolve_datev_sender(), self.email)

	def test_default_or_incoming_only_account_does_not_count(self):
		self.assertIsNone(ar_module.resolve_datev_sender())
		_email_account(self.email, enable_outgoing=0)
		self.assertIsNone(ar_module.resolve_datev_sender())

	def test_send_uses_the_users_account_as_sender(self):
		_email_account(self.email)
		result, sendmail = self._send()
		self.assertTrue(result["ok"], result)
		self.assertEqual(sendmail.call_args.kwargs["sender"], self.email)

	def test_send_refuses_without_own_account(self):
		result, sendmail = self._send()
		self.assertFalse(result["ok"])
		self.assertIn(self.email, result["message"])
		sendmail.assert_not_called()
