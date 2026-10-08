"""Employee Profile becomes Person Web Profile (phamos/phamos#1487, naming rule from #1492).

Runs before the model sync so the existing table and records are renamed, not recreated.
Also covers dev sites that briefly had the interim name "Employee Web Profile".
"""

import frappe


def execute():
	if frappe.db.exists("DocType", "Person Web Profile"):
		return
	for old in ("Employee Web Profile", "Employee Profile"):
		if frappe.db.exists("DocType", old):
			frappe.rename_doc("DocType", old, "Person Web Profile", force=True)
			return
