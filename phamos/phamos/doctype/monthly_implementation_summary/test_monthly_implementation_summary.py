# Copyright (c) 2026, phamos.eu and Contributors
# See license.txt

from unittest.mock import patch

import frappe
from frappe.tests.utils import FrappeTestCase

PROJECT = "_T-MIS-PROJ"
MOD = "phamos.phamos.doctype.monthly_implementation_summary.monthly_implementation_summary"
_LEGACY = []


def _legacy_table(doctype, link_field):
	"""A stand-in for a child table removed in #1987, as a temporary table: it shadows the real one if
	the site still has it, needs no commit, and disappears with the connection."""
	frappe.db.sql(f"drop temporary table if exists `tab{doctype}`")
	frappe.db.sql(f"""create temporary table `tab{doctype}` (
		name varchar(140) primary key, parent varchar(140), idx int, {link_field} varchar(140))""")
	_LEGACY.append(doctype)


def _drop_legacy_tables():
	while _LEGACY:
		frappe.db.sql(f"drop temporary table if exists `tab{_LEGACY.pop()}`")


class TestMonthlyImplementationSummary(FrappeTestCase):
	"""Timesheet -> Delivery Note stamping when one MIS gets several Delivery Notes.

	Records are written with db_insert (no validation) so the tests only need the rows the
	stamping reads; every test is rolled back."""

	def tearDown(self):
		frappe.db.rollback()

	def _make_mis(self, billable_hours, projects=None):
		projects = projects or [PROJECT] * len(billable_hours)
		names = []
		for i, _hours in enumerate(billable_hours, start=1):
			name = f"_T-MIS-TS-{i}"
			frappe.get_doc({"doctype": "Timesheet", "name": name}).db_insert()
			names.append(name)
		mis = frappe.get_doc({
			"doctype": "Monthly Implementation Summary",
			"name": "_T-MIS-1",
			"timesheets_table": [
				{"timesheet": ts, "project": project, "billable_hours": hours}
				for ts, hours, project in zip(names, billable_hours, projects)
			],
		})
		mis.db_insert()
		mis.set_parent_in_children()
		for row in mis.timesheets_table:
			row.db_insert()
		return mis, names

	def _deliver(self, mis, dn_name, hours, docstatus=0):
		"""What _create_dn_for_so_hours does once the Delivery Note is inserted: the Delivery Note points
		at the MIS, then the MIS stamps its Timesheets."""
		frappe.get_doc({
			"doctype": "Delivery Note", "name": dn_name, "docstatus": docstatus, "project": PROJECT,
			"custom_monthly_implementation_summary": mis.name,
		}).db_insert()
		mis._stamp_timesheets_for_delivered_hours(dn_name, hours, PROJECT)

	def _linked_dns(self, timesheets):
		return [frappe.db.get_value("Timesheet", ts, "custom_delivery_note") for ts in timesheets]

	def test_one_draft_dn_per_sales_order_links_every_timesheet(self):
		# MIS-2026-0075: 2 h + 1 h + 1 h of timesheets, one Delivery Note per Sales Order in one go.
		mis, ts = self._make_mis([2, 1, 1])
		self._deliver(mis, "_T-DN-1", 2)
		self._deliver(mis, "_T-DN-2", 1)
		self._deliver(mis, "_T-DN-3", 1)
		self.assertEqual(self._linked_dns(ts), ["_T-DN-1", "_T-DN-2", "_T-DN-3"])

	def test_each_dn_gets_timesheets_matching_its_hours(self):
		# MIS-2026-0001: Delivery Notes of 1 h, 2 h, 1 h over timesheets of 2 h, 1 h, 1 h.
		mis, ts = self._make_mis([2, 1, 1])
		self._deliver(mis, "_T-DN-1", 1)
		self._deliver(mis, "_T-DN-2", 2)
		self._deliver(mis, "_T-DN-3", 1)
		self.assertEqual(self._linked_dns(ts), ["_T-DN-2", "_T-DN-1", "_T-DN-3"])

	def test_second_dn_while_first_is_draft_links_remaining_timesheet(self):
		# MIS-2026-0074: 2 h delivered and left in Draft, then the remaining 0.5 h.
		mis, ts = self._make_mis([1, 1, 0.5])
		self._deliver(mis, "_T-DN-1", 2)
		self._deliver(mis, "_T-DN-2", 0.5)
		self.assertEqual(self._linked_dns(ts), ["_T-DN-1", "_T-DN-1", "_T-DN-2"])

	def test_second_dn_after_first_is_submitted_links_remaining_timesheet(self):
		mis, ts = self._make_mis([1, 1, 0.5])
		self._deliver(mis, "_T-DN-1", 2, docstatus=1)
		self._deliver(mis, "_T-DN-2", 0.5)
		self.assertEqual(self._linked_dns(ts), ["_T-DN-1", "_T-DN-1", "_T-DN-2"])

	def test_partial_delivery_leaves_undelivered_timesheet_unlinked(self):
		mis, ts = self._make_mis([1, 1, 0.5])
		self._deliver(mis, "_T-DN-1", 2)
		self.assertEqual(self._linked_dns(ts), ["_T-DN-1", "_T-DN-1", None])

	def test_timesheets_without_billable_hours_are_linked(self):
		# MIS-2026-0072 / MIS-October-0016: 0-billable timesheets stayed without a Delivery Note.
		mis, ts = self._make_mis([1, 1, 0.5, 0, 0])
		self._deliver(mis, "_T-DN-1", 2.5)
		self.assertEqual(self._linked_dns(ts), ["_T-DN-1"] * 5)

	def test_timesheets_without_billable_hours_of_other_projects_are_linked(self):
		# A project with no billable hours never gets a Delivery Note of its own.
		mis, ts = self._make_mis([1, 0, 0.5], [PROJECT, "_T-MIS-PROJ-0H", "_T-MIS-PROJ-OTHER"])
		self._deliver(mis, "_T-DN-1", 1)
		self.assertEqual(self._linked_dns(ts), ["_T-DN-1", "_T-DN-1", None])

	def test_linked_timesheet_without_billable_hours_keeps_its_dn(self):
		mis, ts = self._make_mis([1, 1, 0])
		self._deliver(mis, "_T-DN-1", 1)
		self._deliver(mis, "_T-DN-2", 1)
		self.assertEqual(self._linked_dns(ts), ["_T-DN-1", "_T-DN-2", "_T-DN-1"])

	def test_timesheet_longer_than_dn_is_linked_to_first_dn(self):
		mis, ts = self._make_mis([4])
		self._deliver(mis, "_T-DN-1", 2)
		self._deliver(mis, "_T-DN-2", 2)
		self.assertEqual(self._linked_dns(ts), ["_T-DN-1"])


class TestDeliveryNoteMonthlyImplementationSummary(FrappeTestCase):
	"""The Delivery Note shows its MIS in the "phamos" section at the top of the form."""

	def setUp(self):
		# The MIS Delivery Note table is gone after #1987; the patch still reads it on old sites.
		_legacy_table("MIS Delivery Note", "delivery_note")

	def tearDown(self):
		frappe.db.rollback()
		_drop_legacy_tables()

	def test_dn_created_from_mis_links_the_mis(self):
		mis = frappe.get_doc({"doctype": "Monthly Implementation Summary", "name": "_T-MIS-1"})
		dn = frappe.new_doc("Delivery Note")
		dn.append("items", {"so_detail": "_T-SOI-1"})
		mod = "phamos.phamos.doctype.monthly_implementation_summary.monthly_implementation_summary"
		with (
			patch("erpnext.selling.doctype.sales_order.sales_order.make_delivery_note", return_value=dn),
			patch.object(type(dn), "insert"),
			patch.object(type(dn), "run_method"),
			patch(f"{mod}._mirror_dn_items_into_mis"),
			patch("frappe.db.get_value", return_value="_T-PROJ"),
		):
			mis._create_dn_for_so_hours("_T-SO-1", [{"so_detail": "_T-SOI-1", "hours": 2}], "_T-PROJ",
				skip_default_stamp=True)
		self.assertEqual(dn.custom_monthly_implementation_summary, "_T-MIS-1")

	def test_patch_fills_mis_on_existing_dns(self):
		from phamos.patches.v1_0.set_delivery_note_monthly_implementation_summary import execute

		for name in ("_T-MIS-A", "_T-MIS-B"):
			frappe.get_doc({"doctype": "Monthly Implementation Summary", "name": name}).db_insert()
		for name in ("_T-DN-ITEM", "_T-DN-ROW", "_T-DN-NONE"):
			frappe.get_doc({"doctype": "Delivery Note", "name": name}).db_insert()
		frappe.get_doc({
			"doctype": "Delivery Note Item", "name": "_T-DNI-1", "parent": "_T-DN-ITEM",
			"parenttype": "Delivery Note", "parentfield": "items",
			"custom_against_monthly_implementation_summary": "_T-MIS-A",
		}).db_insert()
		frappe.db.sql("insert into `tabMIS Delivery Note` (name, parent, idx, delivery_note) values "
			"('_T-MDN-1', '_T-MIS-B', 1, '_T-DN-ROW')")

		with patch("frappe.db.table_exists", return_value=True):
			execute()

		got = {n: frappe.db.get_value("Delivery Note", n, "custom_monthly_implementation_summary")
			for n in ("_T-DN-ITEM", "_T-DN-ROW", "_T-DN-NONE")}
		self.assertEqual(got, {"_T-DN-ITEM": "_T-MIS-A", "_T-DN-ROW": "_T-MIS-B", "_T-DN-NONE": None})

	def test_patch_without_the_old_table_fills_from_lines(self):
		from phamos.patches.v1_0.set_delivery_note_monthly_implementation_summary import execute

		frappe.get_doc({"doctype": "Monthly Implementation Summary", "name": "_T-MIS-A"}).db_insert()
		for name in ("_T-DN-ITEM", "_T-DN-SET"):
			frappe.get_doc({"doctype": "Delivery Note", "name": name}).db_insert()
		frappe.db.set_value("Delivery Note", "_T-DN-SET", "custom_monthly_implementation_summary", "_T-MIS-X")
		for dn in ("_T-DN-ITEM", "_T-DN-SET"):
			frappe.get_doc({
				"doctype": "Delivery Note Item", "name": f"{dn}-1", "parent": dn,
				"parenttype": "Delivery Note", "parentfield": "items",
				"custom_against_monthly_implementation_summary": "_T-MIS-A",
			}).db_insert()

		with patch("frappe.db.table_exists", return_value=False):
			execute()

		got = {n: frappe.db.get_value("Delivery Note", n, "custom_monthly_implementation_summary")
			for n in ("_T-DN-ITEM", "_T-DN-SET")}
		self.assertEqual(got, {"_T-DN-ITEM": "_T-MIS-A", "_T-DN-SET": "_T-MIS-X"})

	def test_mis_fields_sit_in_implementation_specific_sections(self):
		dn = [(f.fieldname, f.label) for f in frappe.get_meta("Delivery Note").fields[:3]]
		self.assertEqual(dn, [
			("custom_phamos", "Implementation Specific"),
			("custom_implementation", "Implementation"),
			("custom_monthly_implementation_summary", "Monthly Implementation Summary"),
		])
		item = [f.fieldname for f in frappe.get_meta("Delivery Note Item").fields[:4]]
		self.assertEqual(item, [
			"custom_implementation_specific",
			"custom_against_monthly_implementation_summary",
			"custom_ref_doc",
			"custom_implementation_specific_end",
		])


class TestMisOneWayLinks(FrappeTestCase):
	"""#1987: Delivery Notes and Sales Invoices point at their MIS; the MIS keeps no link to them, so a
	submitted MIS doesn't block cancelling them."""

	def tearDown(self):
		frappe.db.rollback()
		_drop_legacy_tables()

	def _mis(self, name="_T-MIS-1", docstatus=1, billable_hours=20, creation=None):
		mis = frappe.get_doc({
			"doctype": "Monthly Implementation Summary", "name": name, "docstatus": docstatus,
			"billable_hours": billable_hours, "status": "Open" if docstatus == 1 else "Draft",
		})
		if creation:
			mis.creation = creation
		mis.db_insert()
		return mis

	def _dn(self, name, mis, hours, status="To Bill", docstatus=1, own_lines=True, uom="Hour"):
		frappe.get_doc({
			"doctype": "Delivery Note", "name": name, "docstatus": docstatus, "status": status,
			"project": PROJECT, "grand_total": hours * 100, "custom_monthly_implementation_summary": mis,
		}).db_insert()
		frappe.get_doc({
			"doctype": "Delivery Note Item", "name": f"{name}-1", "parent": name, "parenttype": "Delivery Note",
			"parentfield": "items", "idx": 1, "qty": hours, "uom": uom, "stock_uom": uom,
			"against_sales_order": "_T-SO-1",
			"custom_against_monthly_implementation_summary": mis if own_lines else None,
		}).db_insert()

	def test_mis_has_no_link_to_delivery_notes_or_sales_invoices(self):
		import json
		import os

		from frappe.modules import scrub

		def fields(doctype):
			"""From the app's JSON (the site may not be migrated yet). The ERPNext child table
			`delivery_note_item` is skipped: _mirror_dn_items_into_mis fills none of its links."""
			path = frappe.get_app_path("phamos", "phamos", "doctype", scrub(doctype), f"{scrub(doctype)}.json")
			if not os.path.exists(path):
				return []
			with open(path) as f:
				return json.load(f)["fields"]

		found = []
		for df in fields("Monthly Implementation Summary"):
			child = [] if df["fieldtype"] not in ("Table", "Table MultiSelect") else fields(df["options"])
			for f in [df, *child]:
				if f["fieldtype"] in ("Link", "Dynamic Link") and f.get("options") in ("Delivery Note", "Sales Invoice"):
					found.append((df["fieldname"], f["fieldname"]))
		self.assertEqual(found, [])

	def test_cancelling_a_dn_of_a_submitted_mis_is_not_blocked(self):
		from frappe.model.delete_doc import get_linked_docs

		from phamos.phamos.doctype.monthly_implementation_summary.monthly_implementation_summary import (
			clear_timesheet_stamps_on_delivery_note_cancel,
		)

		mis = self._mis()
		self._dn("_T-DN-1", mis.name, 2)
		frappe.get_doc({
			"doctype": "Timesheet", "name": "_T-MIS-TS-1", "docstatus": 1, "custom_delivery_note": "_T-DN-1",
		}).db_insert()
		frappe.get_doc({
			"doctype": "Timesheets", "name": "_T-MIS-TSROW-1", "parent": mis.name, "docstatus": 1,
			"parenttype": "Monthly Implementation Summary", "parentfield": "timesheets_table",
			"timesheet": "_T-MIS-TS-1", "delivery_note": "_T-DN-1",
		}).db_insert()
		dn = frappe.get_doc("Delivery Note", "_T-DN-1")

		clear_timesheet_stamps_on_delivery_note_cancel(dn)

		self.assertEqual(get_linked_docs(dn, "Cancel"), [])
		self.assertIsNone(frappe.db.get_value("Timesheet", "_T-MIS-TS-1", "custom_delivery_note"))
		self.assertIsNone(frappe.db.get_value("Timesheets", "_T-MIS-TSROW-1", "delivery_note"))

	def test_overview_and_delivered_hours_come_from_the_dns_pointing_at_the_mis(self):
		from phamos.phamos.doctype.monthly_implementation_summary.monthly_implementation_summary import (
			get_deliveries_overview,
		)

		mis = self._mis()
		self._mis("_T-MIS-OTHER")
		self._dn("_T-DN-BILL", mis.name, 12)
		self._dn("_T-DN-DONE", mis.name, 8, status="Completed")
		self._dn("_T-DN-CANC", mis.name, 5, status="Cancelled", docstatus=2)
		self._dn("_T-DN-DRAFT", mis.name, 3, status="Draft", docstatus=0)
		self._dn("_T-DN-OLD", mis.name, 4, status="Completed", own_lines=False)  # header link only
		self._dn("_T-DN-OTHER", "_T-MIS-OTHER", 7)
		frappe.get_doc({
			"doctype": "Sales Invoice", "name": "_T-SI-1", "docstatus": 1, "status": "Paid",
		}).db_insert()
		frappe.get_doc({
			"doctype": "Sales Invoice Item", "name": "_T-SII-1", "parent": "_T-SI-1", "parenttype": "Sales Invoice",
			"parentfield": "items", "delivery_note": "_T-DN-DONE",
		}).db_insert()

		with patch(f"{MOD}._get_hour_uom", return_value="Hour"):
			data = get_deliveries_overview(mis.name)
			mis.reload()
			mis._recalculate_delivered_hours()

		rows = {r["delivery_note"]: r for r in data["rows"]}
		self.assertEqual(set(rows), {"_T-DN-BILL", "_T-DN-DONE", "_T-DN-CANC", "_T-DN-DRAFT", "_T-DN-OLD"})
		self.assertEqual({n: r["hours"] for n, r in rows.items()},
			{"_T-DN-BILL": 12, "_T-DN-DONE": 8, "_T-DN-CANC": 5, "_T-DN-DRAFT": 3, "_T-DN-OLD": 4})
		self.assertEqual(rows["_T-DN-DONE"]["sales_invoices"],
			[{"sales_invoice": "_T-SI-1", "status": "Paid", "docstatus": 1}])
		self.assertEqual(rows["_T-DN-BILL"]["sales_order"], "_T-SO-1")
		self.assertEqual(data["delivered_hours"], 24)  # not the cancelled one, not the draft
		self.assertEqual(data["not_invoiced_hours"], 12)
		self.assertEqual(mis.delivered_hours, 24)

	def test_sales_invoice_created_from_the_mis_points_at_it(self):
		from phamos.phamos.doctype.monthly_implementation_summary.monthly_implementation_summary import (
			create_sales_invoice_from_mis,
		)

		mis = self._mis()
		self._dn("_T-DN-1", mis.name, 2)
		si = frappe.new_doc("Sales Invoice")
		si.append("items", {"delivery_note": "_T-DN-1"})
		with (
			patch("erpnext.stock.doctype.delivery_note.delivery_note.make_sales_invoice", return_value=si),
			patch.object(type(si), "insert"),
			patch(f"{MOD}._find_existing_sales_invoice_for_delivery_note", return_value=None),
		):
			create_sales_invoice_from_mis(mis.name, "_T-DN-1")
		self.assertEqual(si.custom_monthly_implementation_summary, mis.name)

	def test_patch_fills_sales_invoices_from_the_old_rows(self):
		_legacy_table("MIS Sales Invoice", "sales_invoice")
		from phamos.patches.v1_0.mis_links_from_documents import _fill

		self._mis("_T-MIS-A", creation="2026-09-01 00:00:00")
		self._mis("_T-MIS-B", creation="2026-10-01 00:00:00")
		self._mis("_T-MIS-C", docstatus=2, creation="2026-08-01 00:00:00")
		for name in ("_T-SI-BOTH", "_T-SI-SET", "_T-SI-CANC", "_T-SI-NONE"):
			frappe.get_doc({"doctype": "Sales Invoice", "name": name}).db_insert()
		frappe.db.set_value("Sales Invoice", "_T-SI-SET", "custom_monthly_implementation_summary", "_T-MIS-X")
		for i, (parent, si) in enumerate([
			("_T-MIS-B", "_T-SI-BOTH"), ("_T-MIS-A", "_T-SI-BOTH"), ("_T-MIS-A", "_T-SI-SET"),
			("_T-MIS-C", "_T-SI-CANC"), ("_T-MIS-A", "_T-SI-GONE"),
		]):
			frappe.db.sql("insert into `tabMIS Sales Invoice` (name, parent, idx, sales_invoice) values (%s, %s, %s, %s)",
				(f"_T-MSI-{i}", parent, i, si))

		_fill("Sales Invoice", "MIS Sales Invoice", "sales_invoice")

		got = {n: frappe.db.get_value("Sales Invoice", n, "custom_monthly_implementation_summary")
			for n in ("_T-SI-BOTH", "_T-SI-SET", "_T-SI-CANC", "_T-SI-NONE")}
		self.assertEqual(got, {"_T-SI-BOTH": "_T-MIS-A", "_T-SI-SET": "_T-MIS-X", "_T-SI-CANC": None, "_T-SI-NONE": None})
