import json
import os

import frappe
from frappe.query_builder import DocType
from frappe.utils import flt

STASH_FILE = "phamos_mis_legacy_so_dn.json"


def _stash_path():
	return frappe.get_site_path("private", "files", STASH_FILE)


def capture_legacy_links():
	has_so = frappe.db.has_column("Monthly Implementation Summary", "sales_order")
	has_dn = frappe.db.has_column("Monthly Implementation Summary", "delivery_note")
	if not (has_so or has_dn):
		return
	MIS = DocType("Monthly Implementation Summary")
	query = frappe.qb.from_(MIS).select(MIS.name)
	conditions = []
	if has_so:
		query = query.select(MIS.sales_order)
		conditions.append(MIS.sales_order.isnotnull())
	if has_dn:
		query = query.select(MIS.delivery_note)
		conditions.append(MIS.delivery_note.isnotnull())
	condition = conditions[0]
	for c in conditions[1:]:
		condition = condition | c
	rows = query.where(condition).run(as_dict=True)
	links = [
		{
			"mis_name": r["name"],
			"sales_order": r.get("sales_order"),
			"delivery_note": r.get("delivery_note"),
		}
		for r in rows
	]
	with open(_stash_path(), "w") as f:
		json.dump(links, f)


def _restore_legacy_links():
	path = _stash_path()
	try:
		with open(path) as f:
			links = json.load(f)
	except FileNotFoundError:
		return

	by_mis = {}
	for link in links:
		dn = link.get("delivery_note")
		if dn and frappe.db.exists("Delivery Note", dn):
			by_mis.setdefault(link["mis_name"], []).append(link)

	for mis_name, entries in by_mis.items():
		docstatus = frappe.db.get_value("Monthly Implementation Summary", mis_name, "docstatus")
		if docstatus is None:
			continue
		if docstatus == 2:
			continue
		doc = frappe.get_doc("Monthly Implementation Summary", mis_name)
		existing = {r.delivery_note for r in (doc.mis_delivery_notes or [])}
		changed = False
		for entry in entries:
			dn = entry["delivery_note"]
			if dn in existing:
				continue
			dn_status, dn_total = frappe.db.get_value(
				"Delivery Note", dn, ["status", "grand_total"]
			) or ("", 0)
			doc.append("mis_delivery_notes", {
				"delivery_note": dn,
				"sales_order": entry.get("sales_order"),
				"status": dn_status or "",
				"grand_total": flt(dn_total),
			})
			changed = True
		if changed:
			doc.flags.ignore_permissions = True
			doc.flags.ignore_validate_update_after_submit = True
			doc.flags.ignore_links = True
			doc.save()

	os.remove(path)


def execute():
	_restore_legacy_links()

	names = frappe.get_all(
		"Monthly Implementation Summary",
		filters={"docstatus": 1, "status": "Draft"},
		pluck="name",
	)
	for i, name in enumerate(names, start=1):
		doc = frappe.get_doc("Monthly Implementation Summary", name)
		doc.status = "Open"
		doc.flags.ignore_permissions = True
		doc.flags.ignore_validate_update_after_submit = True
		doc.save()
		doc.sync_and_auto_close()
		if i % 50 == 0:
			frappe.db.commit()
	frappe.db.commit()
