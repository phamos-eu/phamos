"""Employment Contracts created before #1601 get a planning rate and a company-currency amount.

Contracts in the company currency get rate 1. Others get ERPNext's rate on their
Effective From; a contract without a known rate is left empty and HR sets it by hand.
Only touches rows without a rate, so it is safe to run twice.
"""

import frappe
from frappe.query_builder.functions import IfNull
from frappe.utils import flt

from phamos.phamos.doctype.employment_contract.employment_contract import get_planning_rate


def execute():
	contract = frappe.qb.DocType("Employment Contract")
	rows = (
		frappe.qb.from_(contract)
		.select(contract.name, contract.company, contract.currency, contract.effective_from, contract.monthly_gross)
		.where(IfNull(contract.conversion_rate, 0) == 0)
	).run(as_dict=True)
	for row in rows:
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
