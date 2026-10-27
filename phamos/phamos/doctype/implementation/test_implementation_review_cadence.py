# Copyright (c) 2026, phamos.eu and Contributors
# See license.txt

"""Review Cadence on Implementation and how a submitted Stakeholder Meeting advances it (#1071)."""

from datetime import date

from frappe.tests.utils import FrappeTestCase
from frappe.utils import add_days, getdate, today

from phamos.phamos.doctype.implementation.implementation import compute_next_review_due
from phamos.phamos.doctype.stakeholder_meeting.test_stakeholder_meeting import (
	make_chapter,
	make_implementation,
	make_meeting,
	set_progress,
)


class TestComputeNextReviewDue(FrappeTestCase):
	def test_day_based_cadences(self):
		self.assertEqual(getdate(compute_next_review_due("2026-01-01", "Weekly")), date(2026, 1, 8))
		self.assertEqual(getdate(compute_next_review_due("2026-01-01", "Biweekly")), date(2026, 1, 15))

	def test_month_based_cadences_clamp_to_the_month_end(self):
		self.assertEqual(getdate(compute_next_review_due("2026-01-31", "Monthly")), date(2026, 2, 28))
		self.assertEqual(getdate(compute_next_review_due("2026-01-31", "Quarterly")), date(2026, 4, 30))

	def test_no_or_unknown_cadence_gives_no_date(self):
		self.assertIsNone(compute_next_review_due("2026-01-01", ""))
		self.assertIsNone(compute_next_review_due("2026-01-01", None))
		self.assertIsNone(compute_next_review_due("2026-01-01", "Yearly"))


class TestReviewCadenceOnImplementation(FrappeTestCase):
	def setUp(self):
		# Reloaded: the on_update hooks write to the record after insert.
		self.implementation = make_implementation()
		self.implementation.reload()

	def test_setting_a_cadence_fills_next_review_due(self):
		self.implementation.review_cadence = "Weekly"
		self.implementation.save()

		self.assertEqual(getdate(self.implementation.next_review_due), getdate(add_days(today(), 7)))

	def test_a_manually_set_next_review_due_is_kept(self):
		self.implementation.review_cadence = "Weekly"
		self.implementation.next_review_due = "2027-01-01"
		self.implementation.save()
		# Reloaded: on_update writes the time limit summary after every save.
		self.implementation.reload()

		self.implementation.review_cadence = "Monthly"
		self.implementation.save()

		self.assertEqual(getdate(self.implementation.next_review_due), date(2027, 1, 1))

	def test_submitted_meeting_advances_the_review_dates(self):
		self.implementation.review_cadence = "Monthly"
		self.implementation.save()
		make_chapter(self.implementation.name)

		meeting = make_meeting(self.implementation.name, meeting_date="2026-02-10")
		set_progress(meeting)
		meeting.submit()

		self.implementation.reload()
		self.assertEqual(self.implementation.last_stakeholder_meeting, meeting.name)
		self.assertEqual(getdate(self.implementation.last_reviewed_on), date(2026, 2, 10))
		self.assertEqual(getdate(self.implementation.next_review_due), date(2026, 3, 10))

	def test_meeting_without_cadence_leaves_next_review_due_empty(self):
		make_chapter(self.implementation.name)

		meeting = make_meeting(self.implementation.name)
		set_progress(meeting)
		meeting.submit()

		self.implementation.reload()
		self.assertEqual(self.implementation.last_stakeholder_meeting, meeting.name)
		self.assertFalse(self.implementation.next_review_due)
