# Copyright (c) 2026, phamos.eu and contributors
# For license information, please see license.txt

from frappe.model.document import Document


class PartyAccountSetting(Document):
	# begin: auto-generated types
	# This code is auto-generated. Do not modify anything in this block.

	from typing import TYPE_CHECKING

	if TYPE_CHECKING:
		from frappe.types import DF

		auto_create_creditor_account: DF.Check
		auto_create_debtor_account: DF.Check
		company: DF.Link
		creditor_number_end: DF.Int
		creditor_number_start: DF.Int
		creditor_parent_account: DF.Link
		debtor_number_end: DF.Int
		debtor_number_start: DF.Int
		debtor_parent_account: DF.Link
		parent: DF.Data
		parentfield: DF.Data
		parenttype: DF.Data
	# end: auto-generated types

	pass
