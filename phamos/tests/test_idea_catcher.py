# Copyright (c) 2026, phamos.eu and contributors
# For license information, please see license.txt

"""Idea Catcher (#2200): catch, search, suggest and link ideas from the phone page."""

from unittest.mock import patch

import frappe
from frappe.tests.utils import FrappeTestCase

from phamos.api import idea_catcher as catcher
from phamos.api import personal_ideas as ideas
from phamos.tests.test_personal_ideas import OTHER, USER, _ensure_user

SETTINGS = "Cockpit Settings"


class TestIdeaCatcher(FrappeTestCase):
	def setUp(self):
		frappe.set_user("Administrator")
		_ensure_user(USER)
		_ensure_user(OTHER, ("Employee", "System Manager"))
		frappe.set_user(USER)

	def tearDown(self):
		frappe.set_user("Administrator")
		frappe.db.rollback()

	def _mine(self, title, content="<p>x</p>"):
		return ideas.create_idea(title=title, content=content)["name"]

	# catch (#2201)

	def test_save_makes_a_seed_with_title_from_first_words(self):
		idea = catcher.save_idea("Bikes for every employee in the summer months and beyond\nsecond line")
		doc = frappe.get_doc("Idea", idea["name"])
		self.assertEqual(doc.user, USER)
		self.assertEqual(doc.stage, "Seed")
		self.assertEqual(doc.title, "Bikes for every employee in the summer months …")
		self.assertIn("<p>second line</p>", doc.content)

	def test_save_refuses_empty_text(self):
		with self.assertRaises(frappe.ValidationError):
			catcher.save_idea("   ")

	def test_same_client_id_makes_one_idea(self):
		first = catcher.save_idea("Offline idea", client_id="abc-1")
		again = catcher.save_idea("Offline idea", client_id="abc-1")
		self.assertEqual(first["name"], again["name"])
		self.assertTrue(again["duplicate"])
		self.assertEqual(frappe.db.count("Idea", {"user": USER, "title": "Offline idea"}), 1)

	def test_website_user_cannot_catch(self):
		with patch.object(catcher, "is_colleague", return_value=False):
			with self.assertRaises(frappe.PermissionError):
				catcher.save_idea("Not for portal users")

	# link (#2203)

	def test_search_shows_only_my_open_ideas(self):
		mine = self._mine("Garden roof")
		frappe.set_user(OTHER)
		theirs = self._mine("Garden party")
		frappe.set_user(USER)
		names = [row.name for row in catcher.search_my_ideas("Garden")]
		self.assertIn(mine, names)
		self.assertNotIn(theirs, names)
		self.assertNotIn(mine, [row.name for row in catcher.search_my_ideas("Garden", exclude=mine)])

	def test_grew_out_of_sets_spawned_from(self):
		target = self._mine("Parent idea")
		new = catcher.save_idea("Child thought")["name"]
		catcher.link_idea(new, target, "spawned")
		self.assertEqual(frappe.db.get_value("Idea", new, "spawned_from"), target)

	def test_add_to_appends_text_and_deletes_the_caught_idea(self):
		target = self._mine("Parent idea", "<p>old text</p>")
		new = catcher.save_idea("One more thought")["name"]
		result = catcher.link_idea(new, target, "append")
		self.assertIsNone(result["name"])
		self.assertFalse(frappe.db.exists("Idea", new))
		content = frappe.db.get_value("Idea", target, "content")
		self.assertTrue(content.startswith("<p>old text</p>"))
		self.assertIn("<p>One more thought</p>", content)

	def test_cannot_link_to_someone_elses_idea(self):
		frappe.set_user(OTHER)
		theirs = self._mine("Not yours")
		frappe.set_user(USER)
		new = catcher.save_idea("Mine")["name"]
		for mode in ("spawned", "append"):
			with self.assertRaises(frappe.PermissionError):
				catcher.link_idea(new, theirs, mode)

	# nearby ideas (#2206)

	def test_suggestions_are_off_by_default(self):
		new = catcher.save_idea("Anything")["name"]
		with patch.object(catcher.llm, "embed") as embed:
			self.assertEqual(catcher.suggest_ideas(new)["enabled"], False)
			embed.assert_not_called()

	def test_suggestions_rank_my_ideas_by_meaning(self):
		close = self._mine("Bike leasing")
		far = self._mine("Christmas party")
		frappe.set_user(OTHER)
		self._mine("Bike leasing too")  # never compared: not mine
		frappe.set_user(USER)
		new = catcher.save_idea("Company bikes")["name"]
		vectors = {"Company bikes": [1, 0], "Bike leasing": [0.95, 0.31], "Christmas party": [0, 1]}

		def fake_embed(texts):
			return [vectors[text.split("\n")[0]] for text in texts]

		with (
			patch.object(catcher, "ai_suggestions_enabled", return_value=True),
			patch.object(catcher.llm, "get_mistral_settings", return_value={"api_key": "x"}),
			patch.object(catcher.llm, "embed", side_effect=fake_embed) as embed,
		):
			result = catcher.suggest_ideas(new)
		self.assertTrue(result["enabled"])
		self.assertEqual([row["name"] for row in result["ideas"]], [close])
		self.assertEqual(result["ideas"][0]["band"], "very close")
		sent = [text.split("\n")[0] for text in embed.call_args[0][0]]
		self.assertNotIn("Bike leasing too", sent)
		self.assertNotIn(far, [row["name"] for row in result["ideas"]])

	# guards from the review

	def test_grew_out_of_refuses_a_loop(self):
		first = catcher.save_idea("First")["name"]
		second = catcher.save_idea("Second")["name"]
		catcher.link_idea(second, first, "spawned")
		with self.assertRaises(frappe.ValidationError):
			catcher.link_idea(first, second, "spawned")

	def test_add_to_keeps_ideas_with_their_own_history(self):
		target = self._mine("Target")
		worked_on = self._mine("Worked on")
		frappe.get_doc(
			{"doctype": "Idea Writing Session", "idea": worked_on, "user": USER, "started_on": frappe.utils.now_datetime()}
		).insert(ignore_permissions=True)
		with self.assertRaises(frappe.ValidationError):
			catcher.link_idea(worked_on, target, "append")
		self.assertTrue(frappe.db.exists("Idea", worked_on))

	def test_add_to_moves_children_to_the_target(self):
		target = self._mine("Target")
		caught = catcher.save_idea("Caught")["name"]
		child = self._mine("Child")
		catcher.link_idea(child, caught, "spawned")
		catcher.link_idea(caught, target, "append")
		self.assertEqual(frappe.db.get_value("Idea", child, "spawned_from"), target)

	def test_embeddings_go_in_batches(self):
		for i in range(20):
			self._mine(f"Idea {i}")
		new = catcher.save_idea("Something new")["name"]
		calls = []

		def fake_embed(texts):
			calls.append(len(texts))
			return [[1, 0] for _ in texts]

		with (
			patch.object(catcher, "ai_suggestions_enabled", return_value=True),
			patch.object(catcher.llm, "get_mistral_settings", return_value={"api_key": "x"}),
			patch.object(catcher.llm, "embed", side_effect=fake_embed),
		):
			catcher.suggest_ideas(new)
		self.assertTrue(all(size <= catcher.EMBED_BATCH for size in calls))
		self.assertEqual(sum(calls), 21)

	def test_add_to_refuses_a_target_that_grew_out_of_it(self):
		caught = catcher.save_idea("Caught")["name"]
		child = catcher.save_idea("Child")["name"]
		grandchild = catcher.save_idea("Grandchild")["name"]
		catcher.link_idea(child, caught, "spawned")
		catcher.link_idea(grandchild, child, "spawned")
		for target in (child, grandchild):
			with self.assertRaises(frappe.ValidationError):
				catcher.link_idea(caught, target, "append")
		self.assertEqual(frappe.db.get_value("Idea", child, "spawned_from"), caught)
		self.assertEqual(frappe.db.get_value("Idea", grandchild, "spawned_from"), child)

	# undo after "Add to it" (#2209)

	def test_undo_puts_both_ideas_back(self):
		target = self._mine("Target", "<p>old text</p>")
		caught = catcher.save_idea("One more thought")["name"]
		child = self._mine("Child")
		catcher.link_idea(child, caught, "spawned")
		result = catcher.link_idea(caught, target, "append")
		restored = catcher.undo_append(result["undo"])
		self.assertEqual(restored["name"], caught)
		self.assertEqual(frappe.db.get_value("Idea", caught, "title"), "One more thought")
		self.assertEqual(frappe.db.get_value("Idea", caught, "user"), USER)
		self.assertEqual(frappe.db.get_value("Idea", target, "content"), "<p>old text</p>")
		self.assertEqual(frappe.db.get_value("Idea", child, "spawned_from"), caught)
		with self.assertRaises(frappe.ValidationError):  # only once
			catcher.undo_append(result["undo"])

	def test_undo_refuses_when_the_target_changed(self):
		target = self._mine("Target", "<p>old text</p>")
		caught = catcher.save_idea("Thought")["name"]
		result = catcher.link_idea(caught, target, "append")
		ideas.update_idea(target, content="<p>edited elsewhere</p>")
		with self.assertRaises(frappe.ValidationError):
			catcher.undo_append(result["undo"])
		self.assertFalse(frappe.db.exists("Idea", caught))

	def test_undo_token_is_per_user(self):
		target = self._mine("Target")
		caught = catcher.save_idea("Thought")["name"]
		result = catcher.link_idea(caught, target, "append")
		frappe.set_user(OTHER)
		with self.assertRaises(frappe.ValidationError):
			catcher.undo_append(result["undo"])
