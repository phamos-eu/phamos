# Copyright (c) 2026, phamos.eu and contributors
# For license information, please see license.txt

"""Ideas in the Personal Cockpit (#1771), with users who are not Administrator."""

from datetime import timedelta
from unittest.mock import patch

import frappe
from frappe.tests.utils import FrappeTestCase
from frappe.utils import add_to_date, now_datetime

from phamos.api import personal_cockpit as pc
from phamos.api import personal_ideas as ideas
from phamos.cockpits import permissions

USER = "idea-a@example.com"
OTHER = "idea-b@example.com"


def _ensure_user(email, roles=("Employee",)):
	if not frappe.db.exists("User", email):
		frappe.get_doc(
			{"doctype": "User", "email": email, "first_name": email.split("@")[0], "send_welcome_email": 0}
		).insert(ignore_permissions=True)
	missing = set(roles) - set(frappe.get_roles(email))
	if missing:
		frappe.get_doc("User", email).add_roles(*missing)


def _versions(name):
	frappe.set_user("Administrator")
	rows = frappe.get_all(
		"Version", filters={"ref_doctype": "Idea", "docname": name}, fields=["data"], order_by="creation asc"
	)
	frappe.set_user(USER)
	return [frappe.parse_json(row.data) for row in rows]


class TestPersonalIdeas(FrappeTestCase):
	def setUp(self):
		frappe.set_user("Administrator")
		_ensure_user(USER)
		_ensure_user(OTHER, ("Employee", "System Manager"))
		self.now = now_datetime()
		clock = patch.object(ideas, "now_datetime", side_effect=lambda: self.now)
		clock.start()
		self.addCleanup(clock.stop)
		frappe.set_user(USER)

	def tearDown(self):
		frappe.set_user("Administrator")
		frappe.db.rollback()

	def _later(self, minutes):
		self.now = self.now + timedelta(minutes=minutes)

	# create and update

	def test_create_defaults_to_seed_and_untitled(self):
		idea = pc.create_idea()
		self.assertEqual(idea["stage"], "Seed")
		self.assertEqual(idea["title"], "Untitled idea")
		self.assertEqual(frappe.db.get_value("Idea", idea["name"], "user"), USER)

	def test_summary_is_a_plain_text_excerpt(self):
		idea = pc.create_idea("Long", content="<p>Hello <b>world</b></p><ul><li>one</li></ul>" + "<p>x</p>" * 150)
		self.assertTrue(idea["summary"].startswith("Hello world one"))
		self.assertNotIn("<", idea["summary"])
		self.assertLessEqual(len(idea["summary"]), 200)
		self.assertTrue(idea["summary"].endswith("…"))

	def test_update_with_stale_modified_is_refused(self):
		idea = pc.create_idea("First")
		stale = idea["modified"]
		self._later(1)
		saved = pc.update_idea(idea["name"], title="Second", modified=stale)
		self.assertEqual(saved["title"], "Second")
		with self.assertRaises(frappe.TimestampMismatchError):
			pc.update_idea(idea["name"], title="Third", modified=stale)
		self.assertEqual(pc.update_idea(idea["name"], title="Third", modified=saved["modified"])["title"], "Third")

	def test_update_rejects_empty_title_and_unknown_stage(self):
		idea = pc.create_idea("Keep")
		with self.assertRaises(frappe.ValidationError):
			pc.update_idea(idea["name"], title="  ")
		with self.assertRaises(frappe.ValidationError):
			pc.update_idea(idea["name"], stage="Tree")

	# stages and list

	def test_harvest_sets_and_clears_harvested_on(self):
		idea = pc.create_idea("Grow")
		self.assertTrue(pc.update_idea(idea["name"], stage="Harvest")["harvested_on"])
		self.assertIsNone(pc.update_idea(idea["name"], stage="Mature")["harvested_on"])

	def test_list_hides_closed_stages_unless_asked(self):
		open_idea = pc.create_idea("Open")
		harvested = pc.create_idea("Done")
		composted = pc.create_idea("Dropped")
		pc.update_idea(harvested["name"], stage="Harvest")
		pc.update_idea(composted["name"], stage="Compost")
		self.assertEqual([r["name"] for r in pc.get_ideas()], [open_idea["name"]])
		self.assertEqual(len(pc.get_ideas(include_closed=1)), 3)
		self.assertEqual([r["name"] for r in pc.get_ideas(stage="Compost")], [composted["name"]])

	# versioning

	def test_content_edits_within_the_window_write_no_version(self):
		idea = pc.create_idea("Quiet")
		before = len(_versions(idea["name"]))
		for word in ("one", "two", "three"):
			self._later(1)
			pc.update_idea(idea["name"], content=f"<p>{word}</p>")
		self.assertEqual(len(_versions(idea["name"])), before)

	def test_leaving_the_editor_writes_one_version_spanning_the_edit(self):
		idea = pc.create_idea("Span", content="<p>start</p>")
		before = len(_versions(idea["name"]))
		for word in ("middle", "end"):
			self._later(1)
			pc.update_idea(idea["name"], content=f"<p>{word}</p>")
		self.assertTrue(pc.snapshot_idea(idea["name"])["written"])
		versions = _versions(idea["name"])
		self.assertEqual(len(versions), before + 1)
		self.assertIn(["content", "<p>start</p>", "<p>end</p>"], versions[-1]["changed"])
		self.assertFalse(pc.snapshot_idea(idea["name"])["written"])

	def test_versions_hold_only_title_stage_and_content(self):
		idea = pc.create_idea("Clean", content="<p>first</p>")
		first = _versions(idea["name"])[0]
		self.assertEqual({row[0] for row in first["changed"]}, {"title", "stage", "content"})

	def test_a_second_snapshot_without_changes_writes_nothing(self):
		idea = pc.create_idea("Twice")
		self._later(1)
		pc.update_idea(idea["name"], content="<p>edit</p>")
		self.assertTrue(pc.snapshot_idea(idea["name"])["written"])
		self.assertFalse(pc.snapshot_idea(idea["name"])["written"])

	def test_title_and_stage_changes_write_a_version_at_once(self):
		idea = pc.create_idea("Old")
		before = len(_versions(idea["name"]))
		pc.update_idea(idea["name"], title="New")
		pc.update_idea(idea["name"], stage="Sprout")
		versions = _versions(idea["name"])
		self.assertEqual(len(versions), before + 2)
		self.assertIn(["stage", "Seed", "Sprout"], versions[-1]["changed"])

	def test_long_editing_writes_a_version_every_ten_minutes(self):
		idea = pc.create_idea("Long edit")
		before = len(_versions(idea["name"]))
		self._later(11)
		pc.update_idea(idea["name"], content="<p>after a while</p>")
		self.assertEqual(len(_versions(idea["name"])), before + 1)

	# side ideas and sessions

	def test_side_idea_spawns_a_child_and_updates_it(self):
		parent = pc.create_idea("Parent")
		child = pc.capture_side_idea(parent["name"], "Stray thought\nwith a second line")
		self.assertEqual(child["title"], "Stray thought")
		self.assertEqual(child["spawned_from"], parent["name"])
		again = pc.capture_side_idea(parent["name"], "Sharper thought", name=child["name"])
		self.assertEqual(again["name"], child["name"])
		self.assertEqual(again["title"], "Sharper thought")
		self.assertEqual([c["name"] for c in pc.get_idea(parent["name"])["children"]], [child["name"]])
		self.assertIsNone(pc.capture_side_idea(parent["name"], "   "))

	def test_complete_writing_session(self):
		idea = pc.create_idea("Write")
		started = add_to_date(self.now, minutes=-25)
		result = pc.complete_idea_writing_session(
			idea["name"], str(started), 420, 300, "similar", "Productive", content="<p>new text</p>"
		)
		self.assertEqual(result["session"]["duration_mins"], 25)
		self.assertEqual(result["idea"]["last_session_words"], 420)
		self.assertEqual(result["idea"]["content"], "<p>new text</p>")
		self.assertEqual(result["idea"]["last_session"]["words_written"], 420)
		self.assertEqual(pc.idea_word_goal(idea["name"], "more"), round(420 * 1.15))
		with self.assertRaises(frappe.ValidationError):
			pc.complete_idea_writing_session(idea["name"], str(started), 1, 1, "lots")
		with self.assertRaises(frappe.ValidationError):
			pc.complete_idea_writing_session(idea["name"], str(started), 1, 1, "more", "Ecstatic")

	def test_word_goal_starts_at_the_default_base(self):
		idea = pc.create_idea("Fresh")
		self.assertEqual(pc.idea_word_goal(idea["name"], "similar"), 300)
		self.assertEqual(pc.idea_word_goal(idea["name"], "less"), 255)

	# privacy

	def test_ideas_are_private_even_for_system_managers(self):
		idea = pc.create_idea("Secret", content="<p>mine</p>")
		pc.update_idea(idea["name"], title="Secret plan")
		pc.complete_idea_writing_session(idea["name"], str(add_to_date(self.now, minutes=-5)), 10, 300, "similar")
		child = pc.capture_side_idea(idea["name"], "Also mine")

		frappe.set_user(OTHER)
		self.assertEqual(frappe.get_list("Idea", pluck="name"), [])
		self.assertEqual(frappe.get_list("Idea Writing Session", pluck="name"), [])
		self.assertEqual(
			frappe.get_list("Version", filters={"ref_doctype": "Idea", "docname": idea["name"]}, pluck="name"), []
		)
		self.assertFalse(frappe.has_permission("Idea", "read", doc=idea["name"]))
		version = frappe.db.get_value("Version", {"ref_doctype": "Idea", "docname": idea["name"]})
		self.assertFalse(frappe.has_permission("Version", "read", doc=version))
		with self.assertRaises(frappe.PermissionError):
			pc.get_idea(idea["name"])
		with self.assertRaises(frappe.PermissionError):
			pc.capture_side_idea(idea["name"], "Not yours")
		with self.assertRaises(frappe.PermissionError):
			pc.create_idea("Sneaky", spawned_from=child["name"])
		self.assertEqual(permissions.idea_query("Administrator"), "")
		self.assertEqual(permissions.version_query("Administrator"), "")

	def test_other_versions_stay_visible_to_system_managers(self):
		frappe.set_user("Administrator")
		note = frappe.get_doc({"doctype": "ToDo", "description": "versioned"}).insert()
		note.description = "changed"
		note.save(ignore_version=False)
		frappe.set_user(OTHER)
		self.assertTrue(frappe.get_list("Version", filters={"ref_doctype": "ToDo", "docname": note.name}))
