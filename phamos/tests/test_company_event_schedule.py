"""Company-wide events: the Events tab on Company syncs its rows to Mailcow like Team's.
bench --site <site> run-tests --module phamos.tests.test_company_event_schedule
"""

from unittest.mock import patch

import frappe
from frappe.tests.utils import FrappeTestCase

from phamos.events import team_daily_schedule
from phamos.setup.event_schedule import ensure_event_schedule_fields
from phamos.tests.marketing_fixtures import ensure_company

MAILBOX = "company-events@example.com"


def ensure_email_account():
	"""A bare row is enough: the sync only reads email_id, and a real insert would try to log in."""
	if not frappe.db.exists("Email Account", MAILBOX):
		account = frappe.new_doc("Email Account")
		account.update({"name": MAILBOX, "email_account_name": MAILBOX, "email_id": MAILBOX})
		account.db_insert()
	team_daily_schedule._email_for_account.cache_clear()
	return MAILBOX


class TestCompanyEventSchedule(FrappeTestCase):
	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		frappe.set_user("Administrator")
		cls.company = ensure_company()
		ensure_event_schedule_fields()

	def setUp(self):
		frappe.db.savepoint("company_event_schedule")
		self.put = patch.object(team_daily_schedule, "_put_ics_upsert", return_value=(True, None)).start()
		self.delete = patch.object(team_daily_schedule, "_delete_uid_for_mailbox", return_value=(True, None)).start()

	def tearDown(self):
		patch.stopall()
		frappe.db.rollback(save_point="company_event_schedule")

	def test_events_tab_sits_before_the_dashboard(self):
		meta = frappe.get_meta("Company")
		self.assertEqual(meta.get_field("event_schedule").options, "Team Daily Schedule")
		fieldnames = [field.fieldname for field in meta.fields]
		start = fieldnames.index("events_tab")
		self.assertEqual(fieldnames[start:start + 3], ["events_tab", "event_schedule", "dashboard_tab"])

	def save_company_with_event(self):
		company = frappe.get_doc("Company", self.company)
		company.append("event_schedule", {
			"subject": "All-hands",
			"start": "2026-12-01 10:00:00",
			"end": "2026-12-01 11:00:00",
			"required_attendees": "a@example.com; b@example.com",
			"email_account": ensure_email_account(),
		})
		company.save()
		return company, company.event_schedule[-1]

	def save_again(self, change=None):
		"""Save the Company the way the form does: a fresh copy, dates as text."""
		company = frappe.get_doc("Company", self.company)
		for row in company.event_schedule:
			row.start, row.end = str(row.start), str(row.end)
			row.update(change or {})
		self.put.reset_mock()
		company.save()
		return company

	def test_saving_a_company_event_sends_the_invite_and_removing_it_cancels(self):
		company, row = self.save_company_with_event()

		uid = team_daily_schedule._row_uid(row.name)
		self.put.assert_called_once()
		self.assertEqual(self.put.call_args.args[0], uid)
		self.assertEqual(self.put.call_args.kwargs["mailbox_email"], MAILBOX)
		synced = frappe.db.get_value("Team Daily Schedule", row.name, ["mailcow_synced", "required_attendees"], as_dict=True)
		self.assertEqual(synced.mailcow_synced, 1)
		self.assertEqual(synced.required_attendees, "a@example.com, b@example.com")

		company.reload()
		company.event_schedule = [r for r in company.event_schedule if r.name != row.name]
		company.save()
		self.delete.assert_called_once_with(uid, MAILBOX)

	def test_saving_the_company_again_does_not_resend_an_unchanged_event(self):
		self.save_company_with_event()
		self.save_again()
		self.put.assert_not_called()

	def test_a_changed_event_is_sent_again_with_a_higher_sequence(self):
		_, row = self.save_company_with_event()
		self.save_again({"subject": "All-hands, new room"})
		self.put.assert_called_once()
		self.assertEqual(frappe.db.get_value("Team Daily Schedule", row.name, "mailcow_seq"), 2)

	def test_an_event_whose_send_failed_is_tried_again(self):
		self.put.return_value = (False, "Mailcow PUT failed (503)")
		_, row = self.save_company_with_event()
		self.assertEqual(frappe.db.get_value("Team Daily Schedule", row.name, "mailcow_synced"), 0)
		self.put.return_value = (True, None)
		self.save_again()
		self.put.assert_called_once()
		self.assertEqual(frappe.db.get_value("Team Daily Schedule", row.name, "mailcow_synced"), 1)

	def test_a_server_side_save_keeps_attendee_answers(self):
		"""Like the daily update_all_teams_weekly_holidays on Team: get_doc + save, nothing changed.
		A re-send would reset every attendee to NEEDS-ACTION, so accepted invites showed as open again."""
		self.save_company_with_event()
		self.put.reset_mock()
		frappe.get_doc("Company", self.company).save()
		self.put.assert_not_called()
