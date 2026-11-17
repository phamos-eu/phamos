# Copyright (c) 2026, phamos.eu and contributors
# For license information, please see license.txt

"""Create a dedicated ledger account per party (Debitorenkonto / Kreditorenkonto). #1529

German bookkeeping, and the DATEV export, expect every customer and supplier to
have its own personal account below a group such as "Debitoren" / "Kreditoren".
The parent account and the number range per company are configured in
phamos Settings → Party Accounts. The account gets the next free number in that
range and is linked in the party's "Accounts" (Party Account) table.

Ported from the lillesisters app (lillesisters/lillesisters/party_account.py).
"""

import frappe
from frappe import _
from frappe.utils import get_link_to_form

SETTINGS = "phamos Settings"

# Maximum length of a document name (varchar column of tabAccount.name).
MAX_NAME_LENGTH = 140

PARTY_CONFIG = {
	"Customer": {
		"kind": "debtor",
		"account_type": "Receivable",
		"name_field": "customer_name",
	},
	"Supplier": {
		"kind": "creditor",
		"account_type": "Payable",
		"name_field": "supplier_name",
	},
}


@frappe.whitelist()
def get_configured_companies(party_type: str) -> list[str]:
	"""Companies with a parent account for this party type in phamos Settings."""
	parent_field = f"{get_party_config(party_type)['kind']}_parent_account"
	return [
		row.company
		for row in frappe.get_single(SETTINGS).party_account_settings
		if row.get(parent_field)
	]


@frappe.whitelist()
def create_party_account(party_type: str, party: str, company: str) -> dict:
	"""Create the party's ledger account for `company` and link it on the party.

	Called by the "Create Debtor/Creditor Account" button. Returns the new
	account's name and number.
	"""
	get_party_config(party_type)

	frappe.has_permission(party_type, "write", party, throw=True)
	frappe.has_permission("Account", "create", throw=True)

	party_doc = frappe.get_doc(party_type, party)

	existing_account = next(
		(row.account for row in party_doc.accounts if row.company == company and row.account), None
	)
	if existing_account:
		frappe.throw(
			_("{0} {1} already has the account {2} for company {3}.").format(
				_(party_type),
				frappe.bold(party),
				frappe.bold(existing_account),
				frappe.bold(company),
			)
		)

	account = add_party_account(party_doc, company)
	party_doc.save()

	return {"account": account.name, "account_number": account.account_number}


def ensure_party_accounts(doc, method=None):
	"""Create missing party accounts while a Customer or Supplier is saved.

	doc_events `before_validate` hook. For every company whose settings row has
	"Create Automatically and Require" ticked for this side, a party without an
	account for that company gets one. This makes the account mandatory without
	blocking the save. If the account cannot be created, e.g. because the number
	range is used up, the whole save fails.

	Runs before ERPNext's own validation, so validate_party_accounts also checks
	the new row.
	"""
	kind = PARTY_CONFIG[doc.doctype]["kind"]
	companies_with_account = {row.company for row in doc.accounts if row.account}

	for setting in frappe.get_single(SETTINGS).party_account_settings:
		if (
			setting.get(f"auto_create_{kind}_account")
			and setting.get(f"{kind}_parent_account")
			and setting.company not in companies_with_account
		):
			# System rights for the Account insert: Frappe has already checked that
			# the user may save this party, and every value of the account comes
			# from the settings. Purchasing users typically may not create Accounts.
			add_party_account(doc, setting.company, ignore_permissions=True)


def add_party_account(party_doc, company: str, ignore_permissions: bool = False):
	"""Insert the party's account for `company` and link it on `party_doc`.

	The party document itself is not saved. Returns the new Account.

	Note: on a parent company with child companies, ERPNext copies a new account
	into the child companies as well (see Account.validate_root_company_and_sync_account_to_children).
	"""
	config = get_party_config(party_doc.doctype)
	kind = config["kind"]
	setting = get_party_account_setting(company, kind)
	parent_account = setting.get(f"{kind}_parent_account")

	# Queue concurrent requests for this parent: the second one waits here until
	# the first has committed its account. get_next_free_number must then use a
	# locking read to actually see that account (see its docstring).
	frappe.db.get_value("Account", parent_account, "name", for_update=True)

	number = get_next_free_number(
		company, setting.get(f"{kind}_number_start"), setting.get(f"{kind}_number_end")
	)

	account = frappe.get_doc(
		{
			"doctype": "Account",
			"account_name": get_account_name(
				party_doc.get(config["name_field"]), number, company, party_doc.name
			),
			"account_number": str(number),
			"parent_account": parent_account,
			"company": company,
			"is_group": 0,
			# Not inherited from the parent; without it the account does not show up
			# in the party's account picker and cannot carry a party in GL entries.
			"account_type": config["account_type"],
			"account_currency": party_doc.get("default_currency")
			or frappe.get_cached_value("Company", company, "default_currency"),
		}
	).insert(ignore_permissions=ignore_permissions)

	party_account_row = next((row for row in party_doc.accounts if row.company == company), None)
	if not party_account_row:
		party_account_row = party_doc.append("accounts", {"company": company})
	party_account_row.account = account.name

	# The DATEV app adds a "Debtor/Creditor Number" to Party Account. Fill it when present.
	if frappe.get_meta("Party Account").has_field("debtor_creditor_number"):
		party_account_row.debtor_creditor_number = str(number)

	return account


def get_party_config(party_type: str) -> dict:
	if party_type not in PARTY_CONFIG:
		frappe.throw(_("Party Type must be Customer or Supplier."))
	return PARTY_CONFIG[party_type]


def get_party_account_setting(company: str, kind: str):
	"""Settings row of `company`, provided it has a parent account for `kind` (debtor/creditor)."""
	settings = frappe.get_single(SETTINGS)
	setting = next((row for row in settings.party_account_settings if row.company == company), None)
	if not setting or not setting.get(f"{kind}_parent_account"):
		parent_field_label = frappe.get_meta("Party Account Setting").get_label(f"{kind}_parent_account")
		frappe.throw(
			_("Company {0} has no {1}. Please set it in {2}.").format(
				frappe.bold(company),
				_(parent_field_label),
				get_link_to_form(SETTINGS, SETTINGS),
			),
			title=_("Missing Configuration"),
		)
	return setting


def get_next_free_number(company: str, start: int, end: int) -> int:
	"""Return the number after the highest account number used in [start, end].

	All accounts of the company are considered, not only those below the parent,
	because ERPNext requires account numbers to be unique per company.

	The read is a locking read (FOR UPDATE) on purpose. MariaDB runs at
	REPEATABLE READ, where a plain SELECT returns the snapshot taken at the
	request's first read. A request that waited for the parent lock would then
	miss the account another request committed meanwhile and reuse its number.
	Locking reads always see the latest committed rows.
	"""
	account_numbers = frappe.db.get_values(
		"Account",
		{"company": company, "account_number": ("is", "set")},
		"account_number",
		pluck=True,
		for_update=True,
	)
	numbers_in_range = [
		int(number)
		for number in account_numbers
		# isdecimal, not isdigit: "²" is a digit but int() cannot parse it.
		if number.strip().isdecimal() and start <= int(number) <= end
	]

	next_number = max(numbers_in_range) + 1 if numbers_in_range else start
	if next_number > end:
		frappe.throw(
			_("The number range {0} to {1} of company {2} is used up.").format(
				start, end, frappe.bold(company)
			),
			title=_("No Free Account Number"),
		)
	return next_number


def get_account_name(party_name: str | None, number: int, company: str, party: str) -> str:
	"""Party name made safe for an Account name of the form "<number> - <name> - <abbr>".

	Falls back to the party's ID when the name is empty after cleaning, because
	Account.account_name is mandatory.
	"""

	def clean(name):
		# Frappe rejects "<" and ">" in document names.
		return " ".join((name or "").replace("<", " ").replace(">", " ").split())

	account_name = clean(party_name) or clean(party)
	abbr = frappe.get_cached_value("Company", company, "abbr")
	max_length = MAX_NAME_LENGTH - len(str(number)) - len(abbr) - len(" - ") * 2
	return account_name[:max_length].strip()
