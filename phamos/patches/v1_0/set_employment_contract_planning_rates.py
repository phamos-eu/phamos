"""Employment Contracts created before #1601 get a planning rate and a company-currency amount.

Contracts in the company currency get rate 1. Others get ERPNext's rate on their
Effective From; a contract without a known rate is left empty and HR sets it by hand.
Only touches rows without a rate, so it is safe to run twice.
"""

import frappe
from frappe.utils import flt

from phamos.phamos.doctype.employment_contract.employment_contract import get_planning_rate


def execute():
	for row in frappe.get_all(
		"Employment Contract",
		filters={"conversion_rate": ("in", (0, None))},
		fields=["name", "company", "currency", "effective_from", "monthly_gross"],
	):
		company_currency = frappe.get_cached_value("Company", row.company, "default_currency")
		currency = row.currency or company_currency
		rate = 1 if currency == company_currency else get_planning_rate(currency, company_currency, row.effective_from)
		if not rate:
			continue
		frappe.db.set_value(
			"Employment Contract",
			row.name,
			{
				"company_currency": company_currency,
				"conversion_rate": rate,
				"base_monthly_gross": flt(row.monthly_gross) * rate,
			},
			update_modified=False,
		)
