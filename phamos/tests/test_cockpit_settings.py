# Copyright (c) 2026, phamos.eu and contributors
# For license information, please see license.txt

"""Cockpit Settings (phamos/phamos#1932): the per-cockpit settings moved out of phamos Settings,
and the window colour and edge glow of each cockpit (#1933)."""

import json
from unittest.mock import patch

import frappe
from frappe.tests.utils import FrappeTestCase

from phamos.cockpits.settings import COCKPITS, GLOW_EDGES, NEUTRAL_THEME_COLOR, cockpit_window
from phamos.patches.v1_0 import move_cockpit_settings as move
from phamos.patches.v1_0 import set_cockpit_window_defaults as window_defaults
from phamos.www.spa_boot import theme_color

OLD, NEW = move.OLD, move.NEW
TABLE = move.TABLE_DOCTYPE


def _rows(doctype):
	return frappe.db.sql(
		"select field, value from `tabSingles` where doctype = %s and field in %s",
		(doctype, move.FIELDS),
	)


def _table_rows():
	rows = frappe.get_all(
		TABLE,
		filters={"parentfield": move.TABLE_FIELD, "parenttype": ("in", (OLD, NEW))},
		fields=["*"],
	)
	return [{**row, "doctype": TABLE} for row in rows]


def _value(field):
	frappe.db.value_cache.pop(NEW, None)
	return frappe.db.get_single_value(NEW, field)


def _store_old(field, value):
	frappe.db.sql(
		"insert into `tabSingles` (doctype, field, value) values (%s, %s, %s)", (OLD, field, value)
	)


def _sick_row(parent, leave_type, idx=1):
	frappe.get_doc(
		{
			"doctype": TABLE,
			"parent": parent,
			"parenttype": parent,
			"parentfield": move.TABLE_FIELD,
			"leave_type": leave_type,
			"idx": idx,
		}
	).db_insert()


class TestMoveCockpitSettings(FrappeTestCase):
	"""Runs the patch on the real site's rows: they are snapshot here and put back in tearDown."""

	def setUp(self):
		self._singles = {doctype: _rows(doctype) for doctype in (OLD, NEW)}
		self._table = _table_rows()
		self._clear()

	def tearDown(self):
		frappe.db.rollback()
		self._clear()
		for doctype, rows in self._singles.items():
			for field, value in rows:
				frappe.db.sql(
					"insert into `tabSingles` (doctype, field, value) values (%s, %s, %s)", (doctype, field, value)
				)
		for row in self._table:
			frappe.get_doc(row).db_insert()
		frappe.db.commit()  # nosemgrep: the snapshot must survive whatever the patch committed
		frappe.db.value_cache.pop(NEW, None)

	def _clear(self):
		frappe.db.delete("Singles", {"doctype": ("in", (OLD, NEW)), "field": ("in", move.FIELDS)})
		frappe.db.delete(TABLE, {"parentfield": move.TABLE_FIELD, "parenttype": ("in", (OLD, NEW))})

	def _run(self):
		# reload_doc syncs the DocType and may commit; the DocType is already synced by migrate
		with patch.object(frappe, "reload_doc"):
			move.execute()

	def test_moves_every_value_and_the_sick_leave_rows(self):
		stored = {"human_resources_privacy_reveal_seconds": "33", "personal_ideas_show_author": "0"}
		for field in move.FIELDS:
			_store_old(field, stored.get(field, f"old {field}"))
		_sick_row(OLD, "_Test Sick A", 1)
		_sick_row(OLD, "_Test Sick B", 2)

		self._run()

		self.assertEqual(_value("sales_department"), "old sales_department")
		self.assertEqual(_value("software_development_timesheet_project"), "old software_development_timesheet_project")
		self.assertEqual(_value("human_resources_privacy_reveal_seconds"), 33)
		self.assertEqual(_value("personal_ideas_show_author"), 0)
		self.assertEqual(_rows(OLD), ())
		from phamos.phamos.hr import sick_leave

		self.assertEqual(sick_leave.get_sick_leave_types(), ["_Test Sick A", "_Test Sick B"])
		self.assertFalse(frappe.db.exists(TABLE, {"parenttype": OLD, "parentfield": move.TABLE_FIELD}))

	def test_keeps_a_value_already_set_on_cockpit_settings(self):
		_store_old("sales_department", "old")
		frappe.db.set_single_value(NEW, "sales_department", "new")
		_sick_row(OLD, "_Test Sick Old")
		_sick_row(NEW, "_Test Sick New")

		self._run()

		self.assertEqual(_value("sales_department"), "new")
		self.assertEqual(
			frappe.get_all(TABLE, filters={"parentfield": move.TABLE_FIELD, "parenttype": ("in", (OLD, NEW))}, pluck="leave_type"),
			["_Test Sick New"],
		)

	def test_stores_the_default_where_nothing_was_ever_stored(self):
		# a Check with no row reads 0, so the "show author" default (1) has to be written
		self._run()
		self.assertEqual(_value("personal_ideas_show_author"), 1)
		self.assertEqual(_value("human_resources_privacy_reveal_seconds"), 120)
		self.assertFalse(_value("sales_department"))  # an empty Link reads ""

	def test_second_run_changes_nothing(self):
		_store_old("accounting_department", "old")
		self._run()
		frappe.db.set_single_value(NEW, "accounting_department", "changed later")
		before = sorted(_rows(NEW))
		self._run()
		self.assertEqual(sorted(_rows(NEW)), before)


class TestCockpitSettingsValidation(FrappeTestCase):
	def test_privacy_seconds_below_ten_are_refused(self):
		settings = frappe.get_single(NEW)
		settings.human_resources_privacy_reveal_seconds = 5
		self.assertRaises(frappe.ValidationError, settings.validate)
		settings.human_resources_privacy_reveal_seconds = 10
		settings.validate()

	def test_phamos_settings_no_longer_has_the_cockpit_fields(self):
		meta = frappe.get_meta(OLD)
		for field in (*move.FIELDS, move.TABLE_FIELD):
			self.assertFalse(meta.has_field(field), field)
			self.assertTrue(frappe.get_meta(NEW).has_field(field), field)


	def test_each_tab_starts_with_an_open_cockpit_button(self):
		# the routes behind the buttons live in cockpit_settings.js (COCKPIT_ROUTES)
		fields = frappe.get_meta(NEW).fields
		tabs = [i for i, field in enumerate(fields) if field.fieldtype == "Tab Break"]
		self.assertEqual(len(tabs), 6)
		with open(frappe.get_app_path("phamos", "cockpits", "doctype", "cockpit_settings", "cockpit_settings.js")) as js:
			script = js.read()
		for i in tabs:
			button = fields[i + 1]
			self.assertEqual((button.fieldtype, button.label), ("Button", "Open Cockpit"), fields[i].fieldname)
			self.assertIn(f"{button.fieldname}:", script)


WINDOW_FIELDS = tuple(
	f"{prefix}_{part}"
	for prefix, _ in COCKPITS.values()
	for part in ("color", "glow", "glow_breathing", *(f"glow_{edge}" for edge in GLOW_EDGES))
)
OFF = {"color": None, "glow": "Off", "edges": [], "breathing": False}


class TestCockpitWindow(FrappeTestCase):
	"""Window colour and edge glow per cockpit (phamos/phamos#1933). Snapshot as above."""

	def setUp(self):
		self._rows = frappe.db.sql(
			"select field, value from `tabSingles` where doctype = %s and field in %s", (NEW, WINDOW_FIELDS)
		)

	def tearDown(self):
		frappe.db.rollback()
		frappe.db.delete("Singles", {"doctype": NEW, "field": ("in", WINDOW_FIELDS)})
		for field, value in self._rows:
			frappe.db.sql("insert into `tabSingles` (doctype, field, value) values (%s, %s, %s)", (NEW, field, value))
		frappe.db.commit()  # nosemgrep: the snapshot must survive whatever the patch committed
		frappe.db.value_cache.pop(NEW, None)

	def _set(self, prefix, color, glow, edges=("bottom", "right"), breathing=1):
		values = {f"{prefix}_color": color, f"{prefix}_glow": glow, f"{prefix}_glow_breathing": breathing}
		values.update({f"{prefix}_glow_{edge}": int(edge in edges) for edge in GLOW_EDGES})
		frappe.db.set_single_value(NEW, values)

	def test_each_cockpit_reads_its_own_colour_glow_and_edges(self):
		self._set("sales", "#C2410C", "On focus")
		self._set("personal", "#0e7490", "Always", edges=("top", "left", "bottom", "right"), breathing=0)
		self.assertEqual(
			cockpit_window("/sales-cockpit"),
			{"color": "#c2410c", "glow": "On focus", "edges": ["bottom", "right"], "breathing": True},
		)
		personal = cockpit_window("/personal-cockpit")
		self.assertEqual(personal["edges"], ["top", "left", "bottom", "right"])
		self.assertFalse(personal["breathing"])

	def test_no_colour_means_neutral_and_no_glow(self):
		for color in ("", None, "red", "#c24", "#c2410c; background: x"):
			self._set("sales", color, "Always")
			self.assertEqual(cockpit_window("/sales-cockpit"), OFF, color)
		self.assertEqual(cockpit_window("/lead-scan"), OFF)

	def test_unknown_glow_or_no_edge_is_off(self):
		self._set("sales", "#c2410c", "Sometimes")
		self.assertEqual(cockpit_window("/sales-cockpit"), {**OFF, "color": "#c2410c"})
		self._set("sales", "#c2410c", "Always", edges=())
		self.assertEqual(cockpit_window("/sales-cockpit"), {**OFF, "color": "#c2410c"})
		self._set("sales", "#c2410c", "Off", edges=("right",))
		self.assertEqual(cockpit_window("/sales-cockpit")["edges"], [])

	def test_boot_and_page_carry_the_colour(self):
		from phamos.www import sales_spa

		self._set("sales", "#c2410c", "Always")
		boot = sales_spa.get_boot()
		self.assertEqual(
			boot.cockpit_window, {"color": "#c2410c", "glow": "Always", "edges": ["bottom", "right"], "breathing": True}
		)
		self.assertEqual(theme_color(boot), "#c2410c")

		self._set("sales", "", "Always")
		self.assertEqual(theme_color(sales_spa.get_boot()), NEUTRAL_THEME_COLOR)

	def test_patch_sets_the_logo_colours_and_keeps_choices(self):
		frappe.db.delete("Singles", {"doctype": NEW, "field": ("in", WINDOW_FIELDS)})
		frappe.db.set_single_value(NEW, {"sales_color": "#123456", "sales_glow_top": 1})
		with patch.object(frappe, "reload_doc"):
			window_defaults.execute()
		self.assertEqual(cockpit_window("/sales-cockpit"), {**OFF, "color": "#123456"})
		self.assertEqual(cockpit_window("/personal-cockpit")["color"], "#0e7490")
		frappe.db.set_single_value(NEW, {"sales_glow": "Always", "human_resources_glow": "Always"})
		self.assertEqual(cockpit_window("/sales-cockpit")["edges"], ["top", "bottom", "right"])  # top kept
		self.assertEqual(cockpit_window("/human-resources-cockpit")["edges"], ["bottom", "right"])
		self.assertTrue(cockpit_window("/human-resources-cockpit")["breathing"])  # default on

	def test_defaults_match_the_app_icons_and_manifests(self):
		meta = frappe.get_meta(NEW)
		for route, (prefix, color) in COCKPITS.items():
			self.assertEqual(meta.get_field(f"{prefix}_color").default, color, prefix)
			self.assertEqual(meta.get_field(f"{prefix}_glow").default, "Off", prefix)
			for edge in GLOW_EDGES:
				self.assertEqual(meta.get_field(f"{prefix}_glow_{edge}").default, str(int(edge in ("bottom", "right"))))
			self.assertEqual(meta.get_field(f"{prefix}_glow_breathing").default, "1", prefix)
			slug = prefix.replace("_", "-")
			path = frappe.get_app_path("phamos", "public", "manifest", f"{slug}.webmanifest")
			with open(path) as manifest:
				data = json.load(manifest)
			self.assertEqual(data["theme_color"], color, slug)
			self.assertEqual(data["start_url"], route, slug)
