# Copyright (c) 2026, phamos.eu and contributors
# For license information, please see license.txt

from frappe.model.document import Document


class TeamAttentionNotice(Document):
	"""One item the morning summary already announced to a team (#2235); keeps it from repeating."""
