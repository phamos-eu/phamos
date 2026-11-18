"""Department events (#1949, before on Company #1814): the Event Schedule syncs its rows to Mailcow
like Team's; the cockpit's saves send in the background; the old Company rows move to the General
Management Department.
bench --site <site> run-tests --module phamos.tests.test_department_event_schedule
"""

from unittest.mock import patch

import frappe
from frappe.tests.utils import FrappeTestCase

from phamos.events import team_daily_schedule
from phamos.patches.v1_0 import move_company_events_to_department as move_patch
from phamos.setup.event_schedule import ensure_event_schedule_fields
from phamos.tests.marketing_fixtures import ensure_company

MAILBOX = "department-events@example.com"


def ensure_email_account():
	"""A bare row is enough: the sync only reads email_id, and a real insert would try to log in."""
	if not frappe.db.exists("Email Account", MAILBOX):
		account = frappe.new_doc("Email Account")
		account.update({"name": MAILBOX, "email_account_name": MAILBOX, "email_id": MAILBOX})
		account.db_insert()
	team_daily_schedule._email_for_account.cache_clear()
	return MAILBOX


def ensure_department(company):
	name = frappe.db.get_value("Department", {"department_name": "_Test Events", "company": company})
	if name:
		return name
	return frappe.get_doc({"doctype": "Department", "department_name": "_Test Events", "company": company}).insert().name


class EventScheduleCase(FrappeTestCase):
	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		frappe.set_user("Administrator")
		cls.company = ensure_company()
		ensure_event_schedule_fields()
		cls.department = ensure_department(cls.company)

	def setUp(self):
		frappe.db.savepoint("department_event_schedule")
		self.put = patch.object(team_daily_schedule, "_put_ics_upsert", return_value=(True, None)).start()
		self.delete = patch.object(team_daily_schedule, "_delete_uid_for_mailbox", return_value=(True, None)).start()

	def tearDown(self):
		patch.stopall()
		frappe.db.rollback(save_point="department_event_schedule")

	def event(self, **values):
		return {
			"subject": "All-hands",
			"start": "2026-12-01 10:00:00",
			"end": "2026-12-01 11:00:00",
			"required_attendees": "a@example.com; b@example.com",
			"email_account": ensure_email_account(),
			**values,
		}

	def save_department_with_event(self, background=False):
		department = frappe.get_doc("Department", self.department)
		department.append("event_schedule", self.event())
		if background:
			department.flags[team_daily_schedule.BACKGROUND_FLAG] = True
		department.save()
		return department, department.event_schedule[-1]

	def save_again(self, change=None):
		"""Save the Department the way the form does: a fresh copy, dates as text."""
		department = frappe.get_doc("Department", self.department)
		for row in department.event_schedule:
			row.start, row.end = str(row.start), str(row.end)
			row.update(change or {})
		self.put.reset_mock()
		department.save()
		return department


class TestDepartmentEventSchedule(EventScheduleCase):
	def test_the_table_sits_in_the_implementation_specific_section_at_the_top(self):
		meta = frappe.get_meta("Department")
		self.assertEqual(meta.get_field("event_schedule").options, "Team Daily Schedule")
		fieldnames = [field.fieldname for field in meta.fields]
		self.assertEqual(
			fieldnames[:3],
			["custom_implementation_specific", "event_schedule", "custom_implementation_specific_end"],
		)

	def test_company_has_no_events_tab_any_more(self):
		self.assertFalse(frappe.get_meta("Company").has_field("event_schedule"))

	def test_saving_an_event_sends_the_invite_and_removing_it_cancels(self):
		department, row = self.save_department_with_event()

		uid = team_daily_schedule._row_uid(row.name)
		self.put.assert_called_once()
		self.assertEqual(self.put.call_args.args[0], uid)
		self.assertEqual(self.put.call_args.kwargs["mailbox_email"], MAILBOX)
		synced = frappe.db.get_value("Team Daily Schedule", row.name, ["mailcow_synced", "required_attendees", "description"], as_dict=True)
		self.assertEqual(synced.mailcow_synced, 1)
		self.assertEqual(synced.required_attendees, "a@example.com, b@example.com")
		# The invite links back to the Department, not to Company.
		self.assertIn("/app/department/", synced.description)

		department.reload()
		department.event_schedule = [r for r in department.event_schedule if r.name != row.name]
		department.save()
		self.delete.assert_called_once_with(uid, MAILBOX)

	def test_saving_again_does_not_resend_an_unchanged_event(self):
		self.save_department_with_event()
		self.save_again()
		self.put.assert_not_called()

	def test_a_changed_event_is_sent_again_with_a_higher_sequence(self):
		_, row = self.save_department_with_event()
		self.save_again({"subject": "All-hands, new room"})
		self.put.assert_called_once()
		self.assertEqual(frappe.db.get_value("Team Daily Schedule", row.name, "mailcow_seq"), 2)

	def test_an_event_whose_send_failed_is_tried_again(self):
		self.put.return_value = (False, "Mailcow PUT failed (503)")
		_, row = self.save_department_with_event()
		self.assertEqual(frappe.db.get_value("Team Daily Schedule", row.name, "mailcow_synced"), 0)
		self.put.return_value = (True, None)
		self.save_again()
		self.put.assert_called_once()
		self.assertEqual(frappe.db.get_value("Team Daily Schedule", row.name, "mailcow_synced"), 1)

	def test_a_server_side_save_keeps_attendee_answers(self):
		"""A save with nothing changed must not re-send: that would reset every attendee to
		NEEDS-ACTION, so accepted invites showed as open again."""
		self.save_department_with_event()
		self.put.reset_mock()
		frappe.get_doc("Department", self.department).save()
		self.put.assert_not_called()


class TestBackgroundSync(EventScheduleCase):
	"""With the background flag (the cockpit's saves, decision 10 in #1949), Mailcow is called by a
	job after the commit, not in the request."""

	def setUp(self):
		super().setUp()
		self.enqueue = patch.object(frappe, "enqueue").start()

	JOB = "phamos.events.team_daily_schedule.run_sync_plan_in_background"

	def sync_jobs(self):
		# Other jobs of a Department save (e.g. the web profile mirror) are not ours.
		return [call for call in self.enqueue.call_args_list if call.args[:1] == (self.JOB,)]

	def run_job(self):
		jobs = self.sync_jobs()
		self.assertEqual(len(jobs), 1)
		kwargs = jobs[0].kwargs
		self.assertTrue(kwargs["enqueue_after_commit"])
		self.enqueue.reset_mock()
		with patch.object(frappe, "publish_realtime") as publish, patch.object(frappe.db, "commit"):
			team_daily_schedule.run_sync_plan_in_background(kwargs["doctype"], kwargs["name"], kwargs["plan"], kwargs["user"])
		events = [call.args[0] for call in publish.call_args_list]
		self.assertEqual(events.count(team_daily_schedule.SYNC_DONE_EVENT), 1)

	def test_the_request_only_plans_and_marks_the_row_pending(self):
		_, row = self.save_department_with_event(background=True)
		self.put.assert_not_called()
		status = frappe.db.get_value("Team Daily Schedule", row.name, ["mailcow_synced", "mailcow_last_error"], as_dict=True)
		self.assertEqual((status.mailcow_synced, status.mailcow_last_error or ""), (0, ""))

		self.run_job()
		self.put.assert_called_once()
		self.assertEqual(frappe.db.get_value("Team Daily Schedule", row.name, "mailcow_synced"), 1)

	def test_a_removed_row_is_cancelled_by_the_job(self):
		_, row = self.save_department_with_event(background=True)
		self.run_job()
		uid = team_daily_schedule._row_uid(row.name)

		department = frappe.get_doc("Department", self.department)
		department.event_schedule = [r for r in department.event_schedule if r.name != row.name]
		department.flags[team_daily_schedule.BACKGROUND_FLAG] = True
		department.save()
		self.delete.assert_not_called()
		self.run_job()
		self.delete.assert_called_once_with(uid, MAILBOX)

	def test_a_failed_send_shows_the_error(self):
		self.put.return_value = (False, "Mailcow PUT failed (503)")
		_, row = self.save_department_with_event(background=True)
		self.run_job()
		self.assertIn("503", frappe.db.get_value("Team Daily Schedule", row.name, "mailcow_last_error"))

	def test_a_crash_outside_a_step_marks_the_rows_instead_of_leaving_them_pending(self):
		_, row = self.save_department_with_event(background=True)
		kwargs = self.sync_jobs()[0].kwargs
		with patch.object(team_daily_schedule, "_run_sync_plan", side_effect=RuntimeError("boom")), \
			patch.object(frappe, "publish_realtime") as publish, patch.object(frappe.db, "commit"), \
			patch.object(frappe, "log_error"):
			team_daily_schedule.run_sync_plan_in_background(kwargs["doctype"], kwargs["name"], kwargs["plan"], kwargs["user"])
		self.assertIn("boom", frappe.db.get_value("Team Daily Schedule", row.name, "mailcow_last_error"))
		self.assertIn(team_daily_schedule.SYNC_DONE_EVENT, [c.args[0] for c in publish.call_args_list])

	def test_an_unchanged_save_enqueues_nothing(self):
		self.save_department_with_event(background=True)
		self.run_job()
		department = frappe.get_doc("Department", self.department)
		department.flags[team_daily_schedule.BACKGROUND_FLAG] = True
		department.save()
		self.assertEqual(self.sync_jobs(), [])


class TestMoveCompanyEvents(EventScheduleCase):
	"""The patch moves the Company rows of #1814 to the General Management Department."""

	def company_row(self, subject):
		from urllib.parse import quote

		row = frappe.new_doc("Team Daily Schedule")
		# Built in a request on another host than migrate's get_url() (e.g. a custom domain).
		description = f"Agenda\n\n{team_daily_schedule.AUTO_GENERATED_MARKER}\nhttps://erp.example.com/app/company/{quote(self.company)}"
		row.update({**self.event(subject=subject), "description": description, "parent": self.company, "parenttype": "Company",
			"parentfield": "event_schedule", "idx": 1, "mailcow_uid": f"uid-{subject}", "mailcow_seq": 3, "mailcow_synced": 1})
		row.db_insert()
		return row.name

	def test_rows_move_with_their_invite_and_the_company_fields_go(self):
		frappe.db.set_single_value("Cockpit Settings", "general_management_department", self.department)
		name = self.company_row("Old company event")

		move_patch.execute()

		moved = frappe.db.get_value("Team Daily Schedule", name, ["parenttype", "parent", "mailcow_uid", "mailcow_seq", "mailcow_synced"], as_dict=True)
		self.assertEqual((moved.parenttype, moved.parent), ("Department", self.department))
		self.assertEqual((moved.mailcow_uid, moved.mailcow_seq, moved.mailcow_synced), ("uid-Old company event", 3, 1))
		self.assertFalse(frappe.db.exists("Custom Field", "Company-event_schedule"))
		description = frappe.db.get_value("Team Daily Schedule", name, "description")
		self.assertIn("https://erp.example.com/app/department/", description)
		self.assertNotIn("/app/company/", description)
		self.put.assert_not_called()
		self.delete.assert_not_called()

	def test_without_a_general_management_department_nothing_moves(self):
		frappe.db.set_single_value("Cockpit Settings", "general_management_department", None)
		name = self.company_row("Stays")
		with patch.object(frappe, "log_error") as log:
			move_patch.execute()
		log.assert_called_once()
		self.assertEqual(frappe.db.get_value("Team Daily Schedule", name, "parenttype"), "Company")

	def test_setting_the_department_later_moves_them(self):
		"""Production: the department setting is new in this release, so it is empty at migrate time."""
		frappe.db.set_single_value("Cockpit Settings", "general_management_department", None)
		name = self.company_row("Waits for the department")
		with patch.object(frappe, "log_error"):
			move_patch.execute()

		settings = frappe.get_doc("Cockpit Settings")
		settings.general_management_department = self.department
		settings.save()
		self.assertEqual(
			frappe.db.get_value("Team Daily Schedule", name, ["parenttype", "parent"]), ("Department", self.department)
		)
		self.put.assert_not_called()


class TestReadableSyncError(FrappeTestCase):
	"""The cockpit shows one line of mailcow_last_error; it must be the line that names the problem."""

	def test_a_long_traceback_keeps_its_exception_line(self):
		from phamos.api.general_management_spa import _sync_error_line

		frames = "".join(
			f'  File "env/lib/python3.11/site-packages/requests/adapters.py", line {n}, in send\n    resp = conn.urlopen()\n'
			for n in range(40)
		)
		traceback = f"Traceback (most recent call last):\n{frames}requests.exceptions.SSLError: certificate verify failed\n"
		stored = team_daily_schedule._truncate_error(traceback)
		self.assertLessEqual(len(stored), 1400)
		self.assertEqual(_sync_error_line(stored), "requests.exceptions.SSLError: certificate verify failed")

	def test_a_server_error_shows_its_status_not_the_end_of_its_html(self):
		from phamos.api.general_management_spa import _sync_error_line

		message = "Mailcow PUT failed (503): <html>\n<body>Service Unavailable</body>\n</html>"
		self.assertEqual(_sync_error_line(message), "Mailcow PUT failed (503): <html>")

	def test_an_unreachable_server_is_a_message_not_a_crash(self):
		import requests

		with (
			patch.object(team_daily_schedule, "dav_password", return_value="secret"),
			patch.object(team_daily_schedule.requests, "put", side_effect=requests.ConnectionError("Name or service not known")),
		):
			ok, error = team_daily_schedule._put_ics_upsert("uid-1", "BEGIN:VCALENDAR", MAILBOX)
		self.assertFalse(ok)
		self.assertIn("server not reachable: ConnectionError: Name or service not known", error)

	def test_a_refused_login_names_the_mailbox_and_where_to_fix_it(self):
		from types import SimpleNamespace

		page = "<html>\n<head><title>401 Authorization Required</title></head>\n<body>nginx</body>\n</html>"
		with (
			patch.object(team_daily_schedule, "dav_password", return_value="secret"),
			patch.object(team_daily_schedule.requests, "put", return_value=SimpleNamespace(status_code=401, text=page)),
		):
			ok, error = team_daily_schedule._put_ics_upsert("uid-1", "BEGIN:VCALENDAR", MAILBOX)
		self.assertFalse(ok)
		self.assertTrue(error.startswith(f"Mailcow refused the login of {MAILBOX} (401)."))
		self.assertNotIn("<", error)

	def test_other_server_errors_keep_their_text_without_html(self):
		from types import SimpleNamespace

		response = SimpleNamespace(status_code=503, text="<html><body><h1>Service Unavailable</h1></body></html>")
		self.assertEqual(
			team_daily_schedule._http_error_message("PUT", MAILBOX, response), "Mailcow PUT failed (503): Service Unavailable"
		)
