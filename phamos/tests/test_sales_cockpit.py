# Copyright (c) 2026, phamos.eu and contributors
# For license information, please see license.txt

"""Unit tests for the Sales cockpit API.

Focused on the guards rather than the happy path: which calendars may be
queried and what they disclose, which events a demo is allowed to touch, and
the filter shapes the endpoints send to the database — the class of bug that
is invisible in a manual click-through.
"""

from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import frappe
from frappe.tests.utils import FrappeTestCase

from phamos.api.sales_demos import DEMO_STATUSES, _attendee_rows, _demo_event_names, _meeting_url
from phamos.api.sales_leads import (
	_allowed_availability_users,
	_availability_day,
	_split_gap,
	_thread_key,
)


class TestAvailabilityUserScope(FrappeTestCase):
	"""Whose calendar a caller may inspect."""

	def test_rejects_users_outside_the_sales_shortlist(self):
		"""Otherwise the caller picks whose calendar to read, which turns a
		scheduling helper into a way of probing any account on the site."""
		shortlist = [{"name": "rep@example.com"}]
		with (
			patch("phamos.api.sales_leads.role_shortlist_users", return_value=shortlist),
			patch("frappe.session", SimpleNamespace(user="me@example.com")),
		):
			self.assertEqual(
				_allowed_availability_users(["hr-manager@example.com"]), ["me@example.com"]
			)

	def test_keeps_users_inside_the_shortlist(self):
		shortlist = [{"name": "rep@example.com"}]
		with (
			patch("phamos.api.sales_leads.role_shortlist_users", return_value=shortlist),
			patch("frappe.session", SimpleNamespace(user="me@example.com")),
		):
			self.assertEqual(_allowed_availability_users(["rep@example.com"]), ["rep@example.com"])

	def test_falls_back_to_the_caller(self):
		with (
			patch("phamos.api.sales_leads.role_shortlist_users", return_value=[]),
			patch("frappe.session", SimpleNamespace(user="me@example.com")),
		):
			self.assertEqual(_allowed_availability_users(None), ["me@example.com"])


class TestAvailabilitySlots(FrappeTestCase):
	"""The gaps offered around what is already booked."""

	def test_slots_do_not_overlap_each_other(self):
		"""Overlapping suggestions would let a rep offer a customer two times
		that clash."""
		slots = _split_gap(
			frappe.utils.get_datetime("2026-09-17 08:00:00"),
			frappe.utils.get_datetime("2026-09-17 12:00:00"),
			60,
		)
		starts = [s["starts_on"] for s in slots]
		self.assertEqual(starts[0], "2026-09-17 08:00:00")
		for earlier, later in zip(slots, slots[1:]):
			self.assertLessEqual(earlier["ends_on"], later["starts_on"])

	def test_slots_start_on_the_half_hour(self):
		slots = _split_gap(
			frappe.utils.get_datetime("2026-09-17 08:07:00"),
			frappe.utils.get_datetime("2026-09-17 11:00:00"),
			60,
		)
		self.assertEqual(slots[0]["starts_on"], "2026-09-17 08:30:00")

	def test_gap_shorter_than_the_slot_offers_nothing(self):
		slots = _split_gap(
			frappe.utils.get_datetime("2026-09-17 08:00:00"),
			frappe.utils.get_datetime("2026-09-17 08:30:00"),
			60,
		)
		self.assertEqual(slots, [])

	def test_free_time_never_overlaps_a_booking(self):
		busy = [
			{
				"subject": "Booked",
				"starts_on": "2026-09-17 10:00:00",
				"ends_on": "2026-09-17 11:30:00",
			}
		]
		day = _availability_day(frappe.utils.getdate("2026-09-17"), busy, 60)
		self.assertEqual(len(day["busy"]), 1)
		for slot in day["free"]:
			self.assertFalse(
				slot["starts_on"] < "2026-09-17 11:30:00" and slot["ends_on"] > "2026-09-17 10:00:00",
				f"{slot} overlaps the booking",
			)

	def test_a_booking_on_another_day_is_ignored(self):
		busy = [
			{
				"subject": "Elsewhere",
				"starts_on": "2026-09-18 10:00:00",
				"ends_on": "2026-09-18 11:00:00",
			}
		]
		day = _availability_day(frappe.utils.getdate("2026-09-17"), busy, 60)
		self.assertEqual(day["busy"], [])


class TestDemoEventOwnership(FrappeTestCase):
	"""Which calendar entries a demo is allowed to rewrite or delete."""

	def test_only_events_stamped_with_this_demo_are_returned(self):
		"""`proposed_slots[].event` is read-only in the form but not on the
		API, so a crafted child row could otherwise name someone else's event
		and have it rewritten or deleted."""
		doc = SimpleNamespace(
			name="DEMO-0001",
			event=None,
			get=lambda field: [SimpleNamespace(event="EV-mine"), SimpleNamespace(event="EV-victim")],
		)
		with patch("frappe.get_all", return_value=["EV-mine"]) as get_all:
			self.assertEqual(_demo_event_names(doc), {"EV-mine"})

			_, kwargs = get_all.call_args
			self.assertEqual(kwargs["filters"]["custom_demo"], "DEMO-0001")
			self.assertCountEqual(kwargs["filters"]["name"][1], ["EV-mine", "EV-victim"])

	def test_no_claimed_events_means_no_query(self):
		doc = SimpleNamespace(name="DEMO-0001", event=None, get=lambda field: [])
		with patch("frappe.get_all") as get_all:
			self.assertEqual(_demo_event_names(doc), set())
			get_all.assert_not_called()


class TestMeetingUrl(FrappeTestCase):
	"""`location` holds either an address or a video link."""

	def test_recognises_a_meeting_link(self):
		self.assertEqual(_meeting_url("https://meet.jit.si/abc"), "https://meet.jit.si/abc")

	def test_a_street_address_is_not_a_link(self):
		self.assertEqual(_meeting_url("Musterstr. 1, 10115 Berlin"), "")

	def test_a_non_http_scheme_is_not_a_link(self):
		self.assertEqual(_meeting_url("javascript:alert(1)"), "")

	def test_empty_location(self):
		self.assertEqual(_meeting_url(None), "")


class TestAttendeeRows(FrappeTestCase):
	"""Normalising invitees onto the demo."""

	def test_duplicates_collapse(self):
		rows = _attendee_rows(
			[
				{"email": "a@example.com", "full_name": "A"},
				{"email": "A@EXAMPLE.COM", "full_name": "A again"},
			]
		)
		self.assertEqual(len(rows), 1)

	def test_a_user_defaults_to_internal(self):
		with (
			patch("phamos.api.sales_demos._user_label", return_value="Our Person"),
			patch("frappe.db.exists", return_value=True),
		):
			rows = _attendee_rows([{"email": "us@phamos.eu", "user": "us@phamos.eu"}])
		self.assertEqual(rows[0]["audience"], "Internal")
		self.assertEqual(rows[0]["full_name"], "Our Person")

	def test_a_plain_address_defaults_to_external(self):
		rows = _attendee_rows([{"email": "them@example.com", "full_name": "Them"}])
		self.assertEqual(rows[0]["audience"], "External")

	def test_attendance_starts_unrecorded(self):
		rows = _attendee_rows([{"email": "them@example.com"}])
		self.assertIsNone(rows[0]["attended"])

	def test_rows_without_anything_identifying_are_dropped(self):
		self.assertEqual(_attendee_rows([{"participation": "Required"}]), [])


class TestThreadKey(FrappeTestCase):
	"""Grouping a conversation in the feed."""

	def test_stacked_reply_prefixes_collapse(self):
		self.assertEqual(_thread_key("AW: Re: Fwd: Angebot"), _thread_key("Angebot"))

	def test_unrelated_subjects_stay_apart(self):
		self.assertNotEqual(_thread_key("Angebot"), _thread_key("Rechnung"))


class TestDemoStatuses(FrappeTestCase):
	def test_statuses_match_the_doctype(self):
		"""The cockpit's pills and `update_demo`'s guard both read from this
		tuple, so it has to stay in step with the Select field."""
		meta = frappe.get_meta("Demo")
		options = [o for o in (meta.get_field("status").options or "").split("\n") if o]
		self.assertEqual(list(DEMO_STATUSES), options)
