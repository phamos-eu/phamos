# Copyright (c) 2026, phamos.eu and contributors
# For license information, please see license.txt

"""Validation of phamos Settings → Party Accounts (#1529). Ported from lillesisters."""

import frappe
from frappe.tests.utils import FrappeTestCase

from phamos.accounting.party_account import SETTINGS

# ERPNext's test records: "_Test Company" / "_Test Company 1" with their charts of accounts.
test_dependencies = ["Company"]

COMPANY = "_Test Company"
SAVEPOINT = "phamos_party_account_settings_test"


class TestPartyAccountSettings(FrappeTestCase):
	def setUp(self):
		super().setUp()
		frappe.db.savepoint(SAVEPOINT)

	def tearDown(self):
		frappe.db.rollback(save_point=SAVEPOINT)
		super().tearDown()

	def test_valid_configuration_saves(self):
		make_settings([make_row()]).save()

	def test_only_debtor_side_saves(self):
		make_settings([make_row(creditor_parent_account=None)]).save()

	def test_only_creditor_side_saves(self):
		make_settings([make_row(debtor_parent_account=None)]).save()

	def test_one_side_without_overlap_check(self):
		# The unused creditor range would overlap, but is ignored without a parent.
		row = make_row(creditor_parent_account=None, creditor_number_start=10000)
		make_settings([row]).save()

	def test_auto_create_kept_with_parent(self):
		settings = make_settings([make_row(auto_create_creditor_account=1)])
		settings.save()
		self.assertEqual(settings.party_account_settings[0].auto_create_creditor_account, 1)

	def test_auto_create_cleared_without_parent(self):
		row = make_row(debtor_parent_account=None, auto_create_debtor_account=1)
		settings = make_settings([row])
		settings.save()
		self.assertEqual(settings.party_account_settings[0].auto_create_debtor_account, 0)

	def test_at_least_one_side_required(self):
		row = make_row(debtor_parent_account=None, creditor_parent_account=None)
		self.assertRaises(frappe.ValidationError, make_settings([row]).save)

	def test_company_only_once(self):
		self.assertRaises(frappe.ValidationError, make_settings([make_row(), make_row()]).save)

	def test_parent_must_be_group(self):
		row = make_row(debtor_parent_account="Debtors - _TC")
		self.assertRaises(frappe.ValidationError, make_settings([row]).save)

	def test_parent_must_have_matching_root_type(self):
		row = make_row(creditor_parent_account="Accounts Receivable - _TC")
		self.assertRaises(frappe.ValidationError, make_settings([row]).save)

	def test_parent_must_exist(self):
		row = make_row(debtor_parent_account="No Such Account - _TC")
		# Frappe's link check answers first; with ignore_links the validation message does.
		self.assertRaises(frappe.ValidationError, make_settings([row]).save)
		settings = make_settings([row])
		settings.flags.ignore_links = True
		self.assertRaisesRegex(frappe.ValidationError, "does not exist", settings.save)

	def test_parent_must_belong_to_company(self):
		row = make_row(debtor_parent_account="Accounts Receivable - _TC1")
		self.assertRaises(frappe.ValidationError, make_settings([row]).save)

	def test_range_may_start_at_zero(self):
		row = make_row(debtor_number_start=0, debtor_number_end=9999)
		make_settings([row]).save()

	def test_range_start_not_after_end(self):
		row = make_row(debtor_number_start=20000, debtor_number_end=10000)
		self.assertRaises(frappe.ValidationError, make_settings([row]).save)

	def test_ranges_must_not_overlap(self):
		row = make_row(creditor_number_start=60000, creditor_number_end=99999)
		self.assertRaises(frappe.ValidationError, make_settings([row]).save)

	def test_no_rows_saves(self):
		make_settings([]).save()


def make_settings(rows):
	settings = frappe.get_single(SETTINGS)
	settings.party_account_settings = []
	for row in rows:
		settings.append("party_account_settings", row)
	return settings


def make_row(**overrides):
	return {
		"company": COMPANY,
		"debtor_parent_account": "Accounts Receivable - _TC",
		"debtor_number_start": 10000,
		"debtor_number_end": 69999,
		"creditor_parent_account": "Accounts Payable - _TC",
		"creditor_number_start": 70000,
		"creditor_number_end": 99999,
		**overrides,
	}
