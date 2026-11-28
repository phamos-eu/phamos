# Copyright (c) 2026, phamos.eu and Contributors
# See license.txt

"""Critical path and slack of chapters (#2033): plain rows in, no database needed."""

from unittest import TestCase

from phamos.phamos.doctype.implementation_chapter.critical_path import critical_path, dependency_conflict


def chapter(name, start, target, *depends_on):
	return {"name": name, "planned_start": start, "target_date": target, "depends_on": list(depends_on)}


class TestCriticalPath(TestCase):
	def test_a_chain_is_critical_and_a_side_chapter_has_room(self):
		result = critical_path(
			[
				chapter("A", "2026-01-01", "2026-01-10"),
				chapter("B", "2026-01-11", "2026-01-20", "A"),
				chapter("C", "2026-01-21", "2026-01-31", "B"),
				chapter("Side", "2026-01-01", "2026-01-05"),
			]
		)["items"]
		for name in ("A", "B", "C"):
			self.assertEqual((result[name]["critical"], result[name]["slack_days"]), (True, 0), name)
		self.assertEqual((result["Side"]["critical"], result["Side"]["slack_days"]), (False, 26))

	def test_a_gap_before_the_successor_is_slack(self):
		result = critical_path(
			[chapter("A", "2026-01-01", "2026-01-10"), chapter("B", "2026-01-14", "2026-01-20", "A")]
		)["items"]
		self.assertEqual(result["A"]["slack_days"], 3)
		self.assertFalse(result["A"]["critical"])
		self.assertTrue(result["B"]["critical"])

	def test_a_deadline_before_the_plan_gives_negative_slack(self):
		result = critical_path(
			[chapter("A", "2026-01-01", "2026-01-10"), chapter("B", "2026-01-11", "2026-01-31", "A")],
			deadline="2026-01-28",
		)["items"]
		self.assertEqual(result["B"]["slack_days"], -3)
		self.assertEqual(result["A"]["slack_days"], -3)
		self.assertTrue(result["A"]["critical"])

	def test_missing_dates_give_none_and_do_not_break_the_rest(self):
		result = critical_path(
			[
				chapter("Undated", "2026-01-01", None),
				chapter("After", "2026-01-11", "2026-01-20", "Undated"),
				chapter("Other", "2026-01-01", "2026-01-15"),
			]
		)["items"]
		self.assertEqual((result["Undated"]["critical"], result["Undated"]["slack_days"]), (None, None))
		self.assertEqual(result["After"]["slack_days"], 0)
		self.assertEqual(result["Other"]["slack_days"], 5)

	def test_a_loop_is_flagged_without_an_error(self):
		result = critical_path(
			[
				chapter("G", "2026-01-01", "2026-01-10", "H"),
				chapter("H", "2026-01-11", "2026-01-20", "G"),
				chapter("I", "2026-01-21", "2026-01-31", "G"),
			]
		)["items"]
		for name in ("G", "H"):
			self.assertTrue(result[name]["cycle"], name)
			self.assertIsNone(result[name]["slack_days"], name)
		self.assertFalse(result["I"]["cycle"])
		self.assertEqual(result["I"]["slack_days"], 0)

	def test_an_overlapping_dependency_is_a_conflict(self):
		result = critical_path(
			[chapter("J", "2026-01-01", "2026-01-15"), chapter("K", "2026-01-10", "2026-01-20", "J")]
		)
		self.assertEqual(result["dependencies"], [{"from": "J", "to": "K", "conflict": True}])
		self.assertEqual(result["items"]["J"]["slack_days"], -6)
		# ending the day before the successor starts is fine; ending on its first day overlaps
		self.assertFalse(dependency_conflict({"target_date": "2026-01-09"}, {"planned_start": "2026-01-10"}))
		self.assertTrue(dependency_conflict({"target_date": "2026-01-10"}, {"planned_start": "2026-01-10"}))
		self.assertFalse(dependency_conflict({"target_date": None}, {"planned_start": "2026-01-10"}))

	def test_dependencies_outside_the_given_chapters_are_ignored(self):
		result = critical_path([chapter("A", "2026-01-01", "2026-01-10", "Draft chapter")])
		self.assertEqual(result["dependencies"], [])
		self.assertTrue(result["items"]["A"]["critical"])
		self.assertEqual(critical_path([]), {"items": {}, "dependencies": []})

	def test_a_chapter_waiting_for_itself_is_a_loop_and_duplicates_count_once(self):
		result = critical_path(
			[chapter("Self", "2026-01-01", "2026-01-10", "Self"), chapter("B", "2026-01-11", "2026-01-20", "A", "A"), chapter("A", "2026-01-01", "2026-01-10")]
		)
		self.assertTrue(result["items"]["Self"]["cycle"])
		self.assertIsNone(result["items"]["Self"]["slack_days"])
		self.assertEqual(result["dependencies"], [{"from": "A", "to": "B", "conflict": False}])
