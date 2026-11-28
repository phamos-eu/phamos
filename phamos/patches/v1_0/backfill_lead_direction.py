"""Inbound / Outbound on existing Leads (phamos/phamos#574).

Creates the fields (``after_migrate`` runs only after the patches), sets the standard Lead Sources' directions,
then copies each source's direction into its leads. Leads without a source, or with an unmapped one, stay empty:
the lead overview shows them as "Not set" until someone chooses.
"""

import frappe

from phamos.marketing.defaults import LEAD_DIRECTION_FIELD
from phamos.marketing.setup import ensure_lead_direction


def execute():
	ensure_lead_direction()
	sources = frappe.get_all(
		"Lead Source", filters={LEAD_DIRECTION_FIELD: ["in", ["Inbound", "Outbound"]]},
		fields=["name", LEAD_DIRECTION_FIELD],
	)
	for source in sources:
		frappe.db.sql(
			f"""update `tabLead` set `{LEAD_DIRECTION_FIELD}` = %s
			where `source` = %s and ifnull(`{LEAD_DIRECTION_FIELD}`, '') = ''""",
			(source[LEAD_DIRECTION_FIELD], source.name),
		)
