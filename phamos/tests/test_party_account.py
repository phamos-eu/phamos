# Copyright (c) 2026, phamos.eu and contributors
# For license information, please see license.txt

"""Debtor/creditor accounts per party (#1529). Ported from lillesisters."""

import frappe
from frappe.tests.utils import FrappeTestCase

from phamos.accounting.party_account import (
	SETTINGS,
	create_party_account,
	get_account_name,
	get_configured_companies,
	get_next_free_number,
)

COMPANY = "_Test Company"
DEBTOR_PARENT = "Accounts Receivable - _TC"
CREDITOR_PARENT = "Accounts Payable - _TC"
# Ranges far away from anything the standard test chart of accounts uses.
DEBTOR_START, DEBTOR_END = 910000, 910009
CREDITOR_START, CREDITOR_END = 920000, 920009
SAVEPOINT = "phamos_party_account_test"


class TestPartyAccount(FrappeTestCase):
	def setUp(self):
		super().setUp()
		frappe.db.savepoint(SAVEPOINT)
		configure_company(COMPANY)

	def tearDown(self):
		frappe.db.rollback(save_point=SAVEPOINT)
		super().tearDown()

	def test_configured_companies(self):
		self.assertEqual(get_configured_companies("Customer"), [COMPANY])
		self.assertEqual(get_configured_companies("Supplier"), [COMPANY])

	def test_only_debtor_side_configured(self):
		configure_company(COMPANY, creditor_parent_account=None)

		self.assertEqual(get_configured_companies("Customer"), [COMPANY])
		self.assertEqual(get_configured_companies("Supplier"), [])
		self.assertRaises(frappe.ValidationError, create_party_account, "Supplier", make_supplier(), COMPANY)
		self.assertTrue(create_party_account("Customer", make_customer(), COMPANY)["account"])

	def test_next_free_number_starts_at_range_start(self):
		self.assertEqual(get_next_free_number(COMPANY, DEBTOR_START, DEBTOR_END), DEBTOR_START)

	def test_next_free_number_follows_highest_used_number(self):
		make_account(DEBTOR_START + 3)
		# Numbers outside the range are ignored.
		make_account(DEBTOR_END + 1)
		self.assertEqual(get_next_free_number(COMPANY, DEBTOR_START, DEBTOR_END), DEBTOR_START + 4)

	def test_next_free_number_throws_when_range_is_used_up(self):
		make_account(DEBTOR_END)
		self.assertRaises(frappe.ValidationError, get_next_free_number, COMPANY, DEBTOR_START, DEBTOR_END)

	def test_create_debtor_account(self):
		customer = make_customer()

		result = create_party_account("Customer", customer, COMPANY)

		account = frappe.get_doc("Account", result["account"])
		self.assertEqual(account.account_number, str(DEBTOR_START))
		self.assertEqual(account.parent_account, DEBTOR_PARENT)
		self.assertEqual(account.account_type, "Receivable")
		self.assertEqual(account.root_type, "Asset")
		self.assertFalse(account.is_group)
		self.assertEqual(account.name, f"{DEBTOR_START} - {customer} - _TC")

		accounts = frappe.get_doc("Customer", customer).accounts
		self.assertEqual([(row.company, row.account) for row in accounts], [(COMPANY, account.name)])

		# The next customer gets the next number.
		second = create_party_account("Customer", make_customer(), COMPANY)
		self.assertEqual(second["account_number"], str(DEBTOR_START + 1))

	def test_create_creditor_account(self):
		supplier = make_supplier()

		result = create_party_account("Supplier", supplier, COMPANY)

		account = frappe.get_doc("Account", result["account"])
		self.assertEqual(account.account_number, str(CREDITOR_START))
		self.assertEqual(account.parent_account, CREDITOR_PARENT)
		self.assertEqual(account.account_type, "Payable")
		self.assertEqual(account.root_type, "Liability")
		self.assertEqual(frappe.get_doc("Supplier", supplier).accounts[0].account, account.name)

	def test_debtor_creditor_number_is_filled_when_field_exists(self):
		if not frappe.get_meta("Party Account").has_field("debtor_creditor_number"):
			self.skipTest("Party Account has no debtor_creditor_number field on this site")

		customer = make_customer()
		create_party_account("Customer", customer, COMPANY)

		row = frappe.get_doc("Customer", customer).accounts[0]
		self.assertEqual(row.debtor_creditor_number, str(DEBTOR_START))

	def test_existing_row_without_account_is_filled(self):
		customer = frappe.get_doc("Customer", make_customer())
		customer.append("accounts", {"company": COMPANY})
		customer.save()

		result = create_party_account("Customer", customer.name, COMPANY)

		accounts = frappe.get_doc("Customer", customer.name).accounts
		self.assertEqual(len(accounts), 1)
		self.assertEqual(accounts[0].account, result["account"])

	def test_second_account_for_same_company_is_refused(self):
		customer = make_customer()
		create_party_account("Customer", customer, COMPANY)

		self.assertRaises(frappe.ValidationError, create_party_account, "Customer", customer, COMPANY)

	def test_unconfigured_company_is_refused(self):
		self.assertRaises(
			frappe.ValidationError, create_party_account, "Customer", make_customer(), "_Test Company 1"
		)

	def test_invalid_party_type_is_refused(self):
		self.assertRaises(frappe.ValidationError, create_party_account, "Employee", "x", COMPANY)

	def test_account_name_is_sanitized_and_shortened(self):
		self.assertEqual(get_account_name("  A <b>  Shop </b> ", 10000, COMPANY, "P-1"), "A b Shop /b")

		account_name = get_account_name("x" * 200, 10000, COMPANY, "P-1")
		self.assertEqual(len(f"10000 - {account_name} - _TC"), 140)

	def test_account_name_falls_back_to_party_id(self):
		self.assertEqual(get_account_name(" <> ", 10000, COMPANY, "SUP-0001"), "SUP-0001")
		self.assertEqual(get_account_name(None, 10000, COMPANY, "SUP-0001"), "SUP-0001")

	def test_unusual_digits_are_ignored(self):
		# "²" counts as a digit in Python but cannot be converted with int().
		make_account("91000²")
		self.assertEqual(get_next_free_number(COMPANY, DEBTOR_START, DEBTOR_END), DEBTOR_START)


class TestAutomaticPartyAccount(FrappeTestCase):
	"""Accounts created while a party is saved ("Create Automatically and Require")."""

	def setUp(self):
		super().setUp()
		frappe.db.savepoint(SAVEPOINT)
		configure_company(COMPANY, auto_create_creditor_account=1)

	def tearDown(self):
		frappe.set_user("Administrator")
		frappe.db.rollback(save_point=SAVEPOINT)
		super().tearDown()

	def test_new_supplier_gets_account_on_insert(self):
		supplier = frappe.get_doc("Supplier", make_supplier())

		self.assertEqual(len(supplier.accounts), 1)
		account = frappe.get_doc("Account", supplier.accounts[0].account)
		self.assertEqual(supplier.accounts[0].company, COMPANY)
		self.assertEqual(account.account_number, str(CREDITOR_START))
		self.assertEqual(account.account_type, "Payable")
		self.assertEqual(account.parent_account, CREDITOR_PARENT)

	def test_existing_supplier_gets_account_on_next_save(self):
		configure_company(COMPANY)  # automation off
		supplier = frappe.get_doc("Supplier", make_supplier())
		self.assertEqual(supplier.accounts, [])

		configure_company(COMPANY, auto_create_creditor_account=1)
		supplier.supplier_details = "changed"
		supplier.save()

		self.assertEqual(len(frappe.get_doc("Supplier", supplier.name).accounts), 1)

	def test_existing_account_is_kept(self):
		supplier = frappe.get_doc("Supplier", make_supplier())
		account = supplier.accounts[0].account

		supplier.supplier_details = "changed"
		supplier.save()

		self.assertEqual([row.account for row in supplier.accounts], [account])
		self.assertEqual(frappe.db.count("Account", {"account_number": str(CREDITOR_START + 1)}), 0)

	def test_unticked_side_is_left_alone(self):
		# Only the creditor side is ticked in setUp.
		self.assertEqual(frappe.get_doc("Customer", make_customer()).accounts, [])

	def test_user_without_account_rights_can_save_supplier(self):
		user = make_user_with_roles("Purchase Master Manager")
		frappe.set_user(user)
		self.assertFalse(frappe.has_permission("Account", "create"))

		supplier = frappe.get_doc("Supplier", make_supplier())

		self.assertEqual(len(supplier.accounts), 1)
		self.assertTrue(frappe.db.exists("Account", supplier.accounts[0].account))

	def test_used_up_range_blocks_save(self):
		configure_company(
			COMPANY,
			auto_create_creditor_account=1,
			creditor_number_start=CREDITOR_START,
			creditor_number_end=CREDITOR_START,
		)
		make_supplier()  # takes the only number

		supplier_count = frappe.db.count("Supplier")
		self.assertRaises(frappe.ValidationError, make_supplier)
		self.assertEqual(frappe.db.count("Supplier"), supplier_count)

	def test_button_on_ticked_company_after_save_reports_existing_account(self):
		supplier = make_supplier()  # already has its account from the hook
		self.assertRaises(frappe.ValidationError, create_party_account, "Supplier", supplier, COMPANY)


def configure_company(company, **overrides):
	settings = frappe.get_single(SETTINGS)
	settings.party_account_settings = []
	settings.append(
		"party_account_settings",
		{
			"company": company,
			"debtor_parent_account": DEBTOR_PARENT,
			"debtor_number_start": DEBTOR_START,
			"debtor_number_end": DEBTOR_END,
			"creditor_parent_account": CREDITOR_PARENT,
			"creditor_number_start": CREDITOR_START,
			"creditor_number_end": CREDITOR_END,
			**overrides,
		},
	)
	settings.save()


def make_account(number, account_name="phamos Party Account Test"):
	return (
		frappe.get_doc(
			{
				"doctype": "Account",
				"account_name": f"{account_name} {number}",
				"account_number": str(number),
				"parent_account": DEBTOR_PARENT,
				"company": COMPANY,
				"account_type": "Receivable",
			}
		)
		.insert()
		.name
	)


def make_customer():
	return (
		frappe.get_doc(
			{
				"doctype": "Customer",
				"customer_name": f"phamos Party Account Test Customer {frappe.generate_hash(length=6)}",
			}
		)
		.insert()
		.name
	)


def make_supplier():
	return (
		frappe.get_doc(
			{
				"doctype": "Supplier",
				"supplier_name": f"phamos Party Account Test Supplier {frappe.generate_hash(length=6)}",
			}
		)
		.insert()
		.name
	)


def make_user_with_roles(*roles):
	email = f"phamos-party-account-test-{frappe.generate_hash(length=6)}@example.com"
	user = frappe.get_doc(
		{"doctype": "User", "email": email, "first_name": "phamos Test", "send_welcome_email": 0}
	).insert()
	user.add_roles(*roles)
	return email
