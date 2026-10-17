# Copyright (c) 2026, phamos.eu and contributors
# For license information, please see license.txt

"""The supplier's bank account: where a Payment Request pays to.

ERPNext puts the supplier's *default* Bank Account on a Payment Request
(`get_party_bank_account` reads only `is_default = 1`), so every account created here is
made the default when the supplier has none.
"""

import frappe
from frappe import _
from frappe.utils import cstr


def normalize_iban(iban):
	return cstr(iban).replace(" ", "").replace("-", "").upper()


def is_valid_iban(iban):
	"""ISO 13616 check: country code, two check digits, mod 97 == 1."""
	iban = normalize_iban(iban)
	if len(iban) < 15 or len(iban) > 34 or not iban[:2].isalpha() or not iban[2:4].isdigit() or not iban.isalnum():
		return False
	rearranged = iban[4:] + iban[:4]
	digits = "".join(str(int(c, 36)) for c in rearranged)
	return int(digits) % 97 == 1


def bank_for(iban, bank_name=None):
	"""Bank record for a supplier account: the given name, else one named after the German
	bank code (BLZ) in the IBAN, else after the IBAN country."""
	name = cstr(bank_name).strip() or (f"BLZ {iban[4:12]}" if iban.startswith("DE") and len(iban) >= 12 else f"Bank {iban[:2]}")
	if not frappe.db.exists("Bank", name):
		frappe.get_doc({"doctype": "Bank", "bank_name": name}).insert(ignore_permissions=True)
	return name


def default_account(supplier):
	if not supplier:
		return None
	return frappe.db.get_value("Bank Account", {"party_type": "Supplier", "party": supplier, "is_default": 1, "disabled": 0}, "name")


def any_account(supplier):
	"""The default account, else the newest enabled one."""
	if not supplier:
		return None
	return default_account(supplier) or frappe.db.get_value(
		"Bank Account", {"party_type": "Supplier", "party": supplier, "disabled": 0}, "name", order_by="creation desc"
	)


def ensure_supplier_bank_account(supplier, iban, bank_name=None, account_name=None):
	"""The supplier's Bank Account for this IBAN, created if missing and made the default
	when the supplier has no default yet. Returns its name."""
	iban = normalize_iban(iban)
	if not supplier:
		frappe.throw(_("Set the supplier first."))
	if not is_valid_iban(iban):
		frappe.throw(_("{0} is not a valid IBAN.").format(iban or _("(empty)")))
	name = frappe.db.get_value("Bank Account", {"party_type": "Supplier", "party": supplier, "iban": iban}, "name")
	if not name:
		doc = frappe.get_doc(
			{
				"doctype": "Bank Account",
				"account_name": account_name or frappe.db.get_value("Supplier", supplier, "supplier_name") or supplier,
				"bank": bank_for(iban, bank_name),
				"party_type": "Supplier",
				"party": supplier,
				"iban": iban,
				"is_company_account": 0,
				"is_default": 0 if default_account(supplier) else 1,
			}
		)
		doc.insert(ignore_permissions=True)
		return doc.name
	values = {}
	if frappe.db.get_value("Bank Account", name, "disabled"):
		values["disabled"] = 0
	if not default_account(supplier):
		values["is_default"] = 1
	if values:
		account = frappe.get_doc("Bank Account", name)
		account.update(values)
		account.save(ignore_permissions=True)
	return name
