# Copyright (c) 2026, phamos.eu and contributors
# For license information, please see license.txt

"""Fetch receipt e-mails now instead of waiting for the scheduler (#1964).

Frappe pulls incoming mail every 10 minutes (`email_account.pull`). The "Fetch e-mails" button
on the receipt lists starts the same pull right away for every Email Account that delivers to
Accounting Receipt, in the background, and tells the clicking user how many receipts arrived.

The job uses Frappe's own job name `pull_from_email_account|<account>`, so a click never queues
a second pull of an account the scheduler (or an earlier click) has already queued.
"""

import frappe
from frappe import _
from frappe.email.doctype.email_account.email_account import pull_from_email_account
from frappe.utils import now_datetime
from frappe.utils.background_jobs import get_jobs

DOCTYPE = "Accounting Receipt"
REALTIME_EVENT = "receipt_emails_fetched"


def receipt_email_accounts():
	"""Names of the incoming Email Accounts that create Accounting Receipts.

	An IMAP account delivers per folder (`IMAP Folder.append_to`); a POP3 account through its own
	`append_to`. OAuth accounts without a token are skipped, the same rule as Frappe's `pull`.
	"""
	from frappe.integrations.doctype.connected_app.connected_app import has_token

	via_folder = frappe.get_all("IMAP Folder", filters={"append_to": DOCTYPE, "parenttype": "Email Account"}, pluck="parent")
	via_account = frappe.get_all("Email Account", filters={"append_to": DOCTYPE}, pluck="name")
	names = sorted(n for n in set(via_folder) | set(via_account) if n)
	if not names:
		return []

	accounts = frappe.get_all(
		"Email Account",
		filters={"name": ("in", names), "enable_incoming": 1, "awaiting_password": 0},
		fields=["name", "auth_method", "backend_app_flow", "connected_app", "connected_user"],
		order_by="name",
	)
	return [
		a.name
		for a in accounts
		if not (a.auth_method == "OAuth" and not a.backend_app_flow and not has_token(a.connected_app, a.connected_user))
	]


@frappe.whitelist(methods=["POST"])
def fetch_receipt_emails():
	"""Queue a mail pull for every account that delivers to Accounting Receipt.

	Anyone who may create a receipt may click; Email Account permission is not needed because the
	method returns only account names, never mail content.

	Returns {"queued": [...], "running": [...]}: accounts queued by this click, and accounts whose
	pull was already queued or running.
	"""
	frappe.has_permission(DOCTYPE, "create", throw=True)

	accounts = receipt_email_accounts()
	if not accounts:
		frappe.throw(
			_("No e-mail account delivers to Accounting Receipt. Ask your administrator to set one up."),
			title=_("No e-mail account"),
		)

	queued_jobs = set(get_jobs(site=frappe.local.site, key="job_name").get(frappe.local.site, []))
	since = now_datetime()
	result = {"queued": [], "running": []}
	for account in accounts:
		job_name = f"pull_from_email_account|{account}"
		if job_name in queued_jobs:
			result["running"].append(account)
			continue
		frappe.enqueue(
			"phamos.accounting.email_pull.pull_and_notify",
			queue="short",
			job_name=job_name,
			email_account=account,
			user=frappe.session.user,
			since=since,
		)
		result["queued"].append(account)
	return result


def pull_and_notify(email_account, user, since):
	"""Background job: pull one account, then tell `user` how many receipts were created.

	The count is every Accounting Receipt created since the click, so a receipt uploaded by
	hand in the same seconds is counted too. That is close enough for a toast.

	The pull runs as Administrator, like the scheduler's: the account may also deliver to other
	doctypes (Issue, Lead, …), and those documents must not be created in the clicking user's name.
	"""
	frappe.set_user("Administrator")
	try:
		pull_from_email_account(email_account)
	except Exception:  # noqa: BLE001 - receive() raises a bare Exception for failed mails
		# receive() commits each mail itself and raises once at the end for the mails that
		# failed; those are in the Error Log and in "Unhandled Email".
		frappe.db.rollback()
		frappe.log_error(title=f"Fetch receipt e-mails: {email_account}")
		frappe.publish_realtime(
			REALTIME_EVENT,
			{"email_account": email_account, "error": _("Some e-mails from {0} could not be read. See the Error Log.").format(email_account)},
			user=user,
		)
		return

	created = frappe.db.count(DOCTYPE, filters={"creation": (">=", since)})
	frappe.publish_realtime(REALTIME_EVENT, {"email_account": email_account, "created": created}, user=user)
