# Copyright (c) 2023, phamos.eu and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.model.document import Document

# root_type the parent account must have for each kind of party account (#1529).
PARENT_ROOT_TYPES = {
	"debtor": "Asset",
	"creditor": "Liability",
}


class phamosSettings(Document):
	def validate(self):
		self.validate_party_account_settings()

	def validate_party_account_settings(self):
		"""Party Accounts tab: one row per company, a valid parent and number range per configured side."""
		seen_companies = set()
		for row in self.party_account_settings:
			if row.company in seen_companies:
				frappe.throw(
					_("Row #{0}: Company {1} is configured more than once.").format(
						row.idx, frappe.bold(row.company)
					)
				)
			seen_companies.add(row.company)

			configured_kinds = [kind for kind in PARENT_ROOT_TYPES if row.get(f"{kind}_parent_account")]

			# Automatic creation needs a parent. The checkbox is hidden without one,
			# so clear it instead of raising an error about a field the user cannot see.
			for kind in PARENT_ROOT_TYPES:
				if kind not in configured_kinds:
					row.set(f"auto_create_{kind}_account", 0)
			if not configured_kinds:
				frappe.throw(_("Row #{0}: Please set a debtor or a creditor parent account.").format(row.idx))

			for kind in configured_kinds:
				validate_parent_account(row, row.get(f"{kind}_parent_account"), PARENT_ROOT_TYPES[kind])
				validate_number_range(row, kind)

			# Only both ranges together can overlap.
			if len(configured_kinds) == len(PARENT_ROOT_TYPES):
				validate_ranges_do_not_overlap(row)

	def before_save(self):
		self._sync_mattermost_scheduler()
		self._sync_raven_scheduler()

	def _sync_mattermost_scheduler(self):
		job_name = "mattermost_daily_thread.create_mattermost_thread"
		if not frappe.db.exists("Scheduled Job Type", job_name):
			return

		cron_doc = frappe.get_doc("Scheduled Job Type", job_name)
		cron_doc.stopped = 0 if self.enable_daily_thread_creation else 1

		if self.thread_posting_hour:
			cron_doc.cron_format = f"0 {self.thread_posting_hour} * * 1-5"

		cron_doc.save(ignore_permissions=True)

	def _sync_raven_scheduler(self):
		job_name = "raven_daily_thread.create_raven_thread"
		if not frappe.db.exists("Scheduled Job Type", job_name):
			return

		cron_doc = frappe.get_doc("Scheduled Job Type", job_name)
		cron_doc.stopped = 0 if self.enable_raven_daily_thread else 1

		hour = self.thread_posting_hour_raven or 6
		cron_doc.cron_format = f"0 {hour} * * 1-5"
		cron_doc.save(ignore_permissions=True)


def validate_parent_account(row, account: str, root_type: str):
	# Frappe's link check catches a wrong name first; this covers saves with ignore_links.
	values = frappe.db.get_value("Account", account, ["company", "is_group", "root_type"])
	if not values:
		frappe.throw(_("Row #{0}: Account {1} does not exist.").format(row.idx, frappe.bold(account)))
	company, is_group, account_root_type = values
	if company != row.company:
		frappe.throw(
			_("Row #{0}: Account {1} does not belong to company {2}.").format(
				row.idx, frappe.bold(account), frappe.bold(row.company)
			)
		)
	if not is_group:
		frappe.throw(
			_("Row #{0}: Account {1} must be a group account.").format(row.idx, frappe.bold(account))
		)
	if account_root_type != root_type:
		frappe.throw(
			_("Row #{0}: Account {1} must have root type {2}.").format(
				row.idx, frappe.bold(account), _(root_type)
			)
		)


def validate_number_range(row, kind: str):
	start = row.get(f"{kind}_number_start")
	end = row.get(f"{kind}_number_end")
	# 0 is a valid number, only an empty field is missing.
	if start is None or end is None:
		frappe.throw(
			_("Row #{0}: {1} and {2} are required.").format(
				row.idx,
				_(row.meta.get_label(f"{kind}_number_start")),
				_(row.meta.get_label(f"{kind}_number_end")),
			)
		)
	if start > end:
		frappe.throw(
			_("Row #{0}: The first number ({1}) must not be greater than the last number ({2}).").format(
				row.idx, start, end
			)
		)


def validate_ranges_do_not_overlap(row):
	if (
		row.debtor_number_start <= row.creditor_number_end
		and row.creditor_number_start <= row.debtor_number_end
	):
		frappe.throw(_("Row #{0}: The debtor and creditor number ranges overlap.").format(row.idx))
