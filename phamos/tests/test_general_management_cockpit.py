# Copyright (c) 2026, phamos.eu and contributors
# For license information, please see license.txt

"""The General Management Cockpit (#1946): wired like the department cockpits, but only the role
`phamos General Management` (and System Manager) gets in, and that role alone is enough."""

import frappe
from frappe.desk.search import search_widget
from frappe.tests.utils import FrappeTestCase
from frappe.utils import add_days, today

from phamos.api import general_management_spa as gm
from phamos.api import software_development_spa
from phamos.api.issue_chat import COCKPIT_PATHS, PERSONAL_COCKPIT_PATH, record_cockpit_path
from phamos.cockpits.settings import COCKPITS, COCKPIT_SETTINGS
from phamos.setup import contracts as contracts_setup
from phamos.setup import general_management as setup
from phamos.www import general_management_spa as page

ROUTE = "/general-management-cockpit"
MANAGER = "gm-cockpit-manager@example.com"
PROJECTS_USER = "gm-cockpit-projects-user@example.com"


def _whitelisted(module):
	return {name: fn for name, fn in vars(module).items() if callable(fn) and fn in frappe.whitelisted}


def _make_user(email, roles):
	"""A System User with exactly `roles` (plus the automatic ones)."""
	if frappe.db.exists("User", email):
		user = frappe.get_doc("User", email)
		user.remove_roles(*[r.role for r in user.roles])
	else:
		user = frappe.get_doc(
			{
				"doctype": "User",
				"email": email,
				"first_name": email.split("@")[0],
				"user_type": "System User",
				"send_welcome_email": 0,
			}
		).insert(ignore_permissions=True)
	user.add_roles(*roles)
	return email


def _custom_perm(doctype):
	return frappe.db.get_value(
		"Custom DocPerm",
		{"parent": doctype, "role": setup.GENERAL_MANAGEMENT_ROLE, "permlevel": 0, "if_owner": 0},
		["name", "modified", *setup.GRANTED, *setup.WITHHELD],
		as_dict=True,
	)


class TestGeneralManagementWiring(FrappeTestCase):
	def test_config_fields_exist_in_cockpit_settings(self):
		meta = frappe.get_meta(COCKPIT_SETTINGS)
		for field in (gm.CONFIG.department_field, gm.CONFIG.project_field, "general_management_color"):
			self.assertTrue(meta.has_field(field), field)

	def test_settings_keys_match_frontend_config(self):
		# general_management_frontend/src/config.js reads these keys from get_general_management_settings.
		self.assertEqual(gm.CONFIG.project_name_key, "general_management_timesheet_project_name")

	def test_exposes_the_same_endpoints_as_software_development(self):
		# The shared spa_shared views call these by name, so a missing one breaks a screen.
		# Software Development is the template (#1462); Human Resources has HR-only extras.
		expected = {
			name.replace("get_software_development_settings", gm.CONFIG.settings_method_name)
			for name in _whitelisted(software_development_spa)
		}
		# Plus what only this cockpit has: the company Tasks view (#1948), appointments (#1949)
		# and contracts (#2148).
		own = {
			"get_company_tasks",
			"get_company_task",
			"get_company_appointments",
			"get_appointment_options",
			"save_appointment",
			"delete_appointment",
			"get_contracts",
			"get_contract_options",
		}
		self.assertEqual(set(_whitelisted(gm)), expected | own)

	def test_every_endpoint_checks_the_role(self):
		ungated = [
			name
			for name, fn in _whitelisted(gm).items()
			if not getattr(fn, "requires_general_management", False)
		]
		self.assertEqual(ungated, [])

	def test_window_colour_and_raven_links(self):
		self.assertEqual(COCKPITS[ROUTE], ("general_management", "#a16207"))
		self.assertIn(("general_management_department", ROUTE), COCKPIT_PATHS)


class TestGeneralManagementAccess(FrappeTestCase):
	def setUp(self):
		frappe.set_user("Administrator")
		setup.after_migrate()
		# A department no other cockpit uses, so Raven links can only point here.
		taken = {
			frappe.db.get_single_value(COCKPIT_SETTINGS, f"{prefix}_department")
			for prefix, _color in COCKPITS.values()
			# cockpits without a department of their own
			if prefix not in ("general_management", "personal", "team", "implementation")
		}
		departments = [
			name
			for name in frappe.get_all("Department", filters={"is_group": 0}, pluck="name")
			if name not in taken
		]
		if not departments:
			self.skipTest("needs a Department no other cockpit uses")
		self.department = departments[0]
		frappe.db.set_single_value(COCKPIT_SETTINGS, gm.CONFIG.department_field, self.department)
		# A timesheet project of the site's own department would not match the test department.
		frappe.db.set_single_value(COCKPIT_SETTINGS, gm.CONFIG.project_field, None)

	def tearDown(self):
		frappe.set_user("Administrator")
		frappe.db.rollback()

	def test_reading_issues_and_tasks_is_not_enough(self):
		frappe.set_user(_make_user(PROJECTS_USER, ["Projects User"]))
		self.assertTrue(frappe.has_permission("Task", "read"))

		self.assertFalse(gm.check_app_permission())
		with self.assertRaises(frappe.PermissionError):
			gm.get_general_management_settings()
		with self.assertRaises(frappe.PermissionError):
			gm.get_tasks()
		with self.assertRaises(frappe.PermissionError):
			page.get_context(frappe._dict())

	def test_raven_links_open_here_only_for_the_role(self):
		frappe.set_user("Administrator")
		task = frappe.get_doc(
			{"doctype": "Task", "subject": "Company target", "department": self.department}
		).insert()

		frappe.set_user(_make_user(MANAGER, [setup.GENERAL_MANAGEMENT_ROLE]))
		self.assertEqual(record_cockpit_path("Task", task.name), ROUTE)

		frappe.set_user(_make_user(PROJECTS_USER, ["Projects User"]))
		self.assertEqual(record_cockpit_path("Task", task.name), PERSONAL_COCKPIT_PATH)

	def test_guest_is_refused(self):
		frappe.set_user("Guest")
		self.assertFalse(gm.check_app_permission())

	def test_the_role_alone_is_enough(self):
		frappe.set_user(_make_user(MANAGER, [setup.GENERAL_MANAGEMENT_ROLE]))
		self.assertTrue(gm.check_app_permission())

		settings = gm.get_general_management_settings()
		self.assertEqual(settings["general_management_department"], self.department)

		task = gm.create_task(
			"Company target",
			priority="Medium",
			exp_start_date=today(),
			exp_end_date=add_days(today(), 30),
			expected_time=4,
			custom_task_owner=MANAGER,
		)
		self.assertEqual(task["department"], self.department)
		self.assertIn(task["name"], [t["name"] for t in gm.get_tasks()])

	def test_checklist_reference_search_runs_as_the_dialog_calls_it(self):
		# The "Linked record" field searches through frappe's search_widget, which passes the
		# arguments by position; frappe's sanitiser has to see the real function to find
		# `searchfield` among them (#1956).
		frappe.set_user("Administrator")
		task = frappe.get_doc(
			{"doctype": "Task", "subject": "_Test searchable company target", "department": self.department}
		).insert()

		frappe.set_user(_make_user(MANAGER, [setup.GENERAL_MANAGEMENT_ROLE]))
		rows = search_widget(
			"Task",
			"searchable company",
			query="phamos.api.general_management_spa.checklist_reference_query",
			page_length=20,
		)
		self.assertIn(task.name, {row[0] for row in rows})

	def test_checklist_reference_search_needs_the_role(self):
		frappe.set_user(_make_user(PROJECTS_USER, ["Projects User"]))
		with self.assertRaises(frappe.PermissionError):
			gm.checklist_reference_query("Task", "target", "name", 0, 20, {})


class TestGeneralManagementRole(FrappeTestCase):
	def tearDown(self):
		frappe.db.rollback()

	def test_role_gets_rights_without_delete(self):
		setup.after_migrate()
		self.assertTrue(frappe.db.exists("Role", setup.GENERAL_MANAGEMENT_ROLE))
		for doctype in setup.DOCTYPES:
			perm = _custom_perm(doctype)
			self.assertIsNotNone(perm, doctype)
			for ptype in setup.GRANTED:
				self.assertEqual(perm[ptype], 1, f"{doctype} {ptype}")
			self.assertEqual(perm["delete"], 0, doctype)

	def test_running_twice_changes_nothing(self):
		setup.after_migrate()
		before = {doctype: _custom_perm(doctype) for doctype in setup.DOCTYPES}
		setup.after_migrate()
		self.assertEqual({doctype: _custom_perm(doctype) for doctype in setup.DOCTYPES}, before)


class TestCompanyTasks(FrappeTestCase):
	"""'All departments' on the Tasks Gantt (#1948): top-level Tasks of each cockpit department."""

	def setUp(self):
		frappe.set_user("Administrator")
		setup.after_migrate()
		departments = frappe.get_all("Department", filters={"is_group": 0}, pluck="name", limit=3)
		if len(departments) < 3:
			self.skipTest("needs three Departments")
		self.own, self.sales, self.elsewhere = departments
		# Only General Management and Sales have a department here; the rest is rolled back.
		for prefix, _color in COCKPITS.values():
			field = f"{prefix}_department"
			if frappe.get_meta(COCKPIT_SETTINGS).has_field(field):
				frappe.db.set_single_value(COCKPIT_SETTINGS, field, None)
		frappe.db.set_single_value(COCKPIT_SETTINGS, "general_management_department", self.own)
		frappe.db.set_single_value(COCKPIT_SETTINGS, "sales_department", self.sales)

		self.own_task = self._task("GM target", self.own)
		self.sales_task = self._task("Sales target", self.sales, is_group=1)
		self.sales_subtask = self._task("Sales subtask", self.sales, parent_task=self.sales_task)
		self.sales_cancelled = self._task("Sales cancelled", self.sales, status="Cancelled")
		self.other_task = self._task("No cockpit", self.elsewhere)

	def tearDown(self):
		frappe.set_user("Administrator")
		frappe.db.rollback()

	def _task(self, subject, department, **fields):
		return (
			frappe.get_doc(
				{
					"doctype": "Task",
					"subject": f"_Test company {subject}",
					"department": department,
					"exp_start_date": today(),
					"exp_end_date": add_days(today(), 10),
					**fields,
				}
			)
			.insert()
			.name
		)

	def _names(self, group):
		return {task["name"] for task in group["tasks"]}

	def test_one_group_per_cockpit_department_own_first(self):
		groups = gm.get_company_tasks()
		self.assertEqual([g["department"] for g in groups], [self.own, self.sales])
		own, sales = groups
		self.assertTrue(own["own"])
		self.assertFalse(sales["own"])
		self.assertEqual((own["label"], own["route"]), ("General Management", ROUTE))
		self.assertEqual((sales["label"], sales["route"]), ("Sales", "/sales-cockpit"))
		self.assertRegex(sales["color"], r"^#[0-9a-f]{6}$")

	def test_only_top_level_tasks_and_completed_on_request(self):
		own, sales = gm.get_company_tasks()
		self.assertIn(self.own_task, self._names(own))
		self.assertIn(self.sales_task, self._names(sales))
		self.assertNotIn(self.sales_subtask, self._names(sales))
		self.assertNotIn(self.sales_cancelled, self._names(sales))

		_own, sales = gm.get_company_tasks(include_completed=1)
		self.assertIn(self.sales_cancelled, self._names(sales))

	def test_departments_without_a_cockpit_stay_out(self):
		names = set().union(*(self._names(g) for g in gm.get_company_tasks(include_completed=1)))
		self.assertNotIn(self.other_task, names)

	def test_read_only_detail_of_another_department(self):
		detail = gm.get_company_task(self.sales_task)
		self.assertEqual(detail["subject"], "_Test company Sales target")
		self.assertEqual(detail["cockpit"]["label"], "Sales")
		self.assertFalse(detail["cockpit"]["own"])
		with self.assertRaises(frappe.PermissionError):
			gm.get_company_task(self.other_task)

	def test_dependencies_in_the_task_panel(self):
		# #2000: the side panel lists, adds and removes predecessors.
		first = self._task("GM first", self.own)
		gm.add_task_dependency(self.own_task, first)

		deps = gm.get_task(self.own_task)["dependencies"]
		self.assertEqual([d["name"] for d in deps], [first])
		self.assertEqual(deps[0]["subject"], "_Test company GM first")
		self.assertTrue(deps[0]["readable"])

		detail = gm.remove_task_dependency(self.own_task, first)
		self.assertEqual(detail["dependencies"], [])
		self.assertEqual(frappe.get_doc("Task", self.own_task).depends_on, [])
		# Removing it again changes nothing.
		self.assertEqual(gm.remove_task_dependency(self.own_task, first)["dependencies"], [])

	def test_dependency_search_stays_in_the_cockpit(self):
		first = self._task("GM first", self.own)
		found = [t["name"] for t in gm.search_dependency_candidates(self.own_task, "_Test company")]
		self.assertIn(first, found)
		self.assertNotIn(self.own_task, found)
		self.assertNotIn(self.sales_task, found)

		gm.add_task_dependency(self.own_task, first)
		found = [t["name"] for t in gm.search_dependency_candidates(self.own_task, "_Test company")]
		self.assertNotIn(first, found)

	def test_needs_the_role(self):
		frappe.set_user(_make_user(PROJECTS_USER, ["Projects User"]))
		with self.assertRaises(frappe.PermissionError):
			gm.get_company_tasks()
		with self.assertRaises(frappe.PermissionError):
			gm.get_company_task(self.sales_task)


class TestCompanyAppointments(FrappeTestCase):
	"""Company appointments (#1949): the General Management Department's Event Schedule rows,
	planned from the cockpit. The Mailcow calls are patched, as in test_company_event_schedule."""

	MAILBOX = "gm-appointments@example.com"

	def setUp(self):
		from unittest.mock import patch

		from phamos.events import team_daily_schedule
		from phamos.setup.event_schedule import ensure_event_schedule_fields
		from phamos.tests.marketing_fixtures import ensure_company

		frappe.set_user("Administrator")
		setup.after_migrate()
		ensure_event_schedule_fields()
		self.company = ensure_company()
		self.department = self._department(self.company)
		frappe.db.set_single_value(COCKPIT_SETTINGS, gm.CONFIG.department_field, self.department)
		self._mailbox()
		team_daily_schedule._email_for_account.cache_clear()
		self.put = patch.object(team_daily_schedule, "_put_ics_upsert", return_value=(True, None)).start()
		self.delete = patch.object(team_daily_schedule, "_delete_uid_for_mailbox", return_value=(True, None)).start()
		# The cockpit sends in the background (decision 10): capture the job, run it with run_jobs().
		self.enqueue = patch.object(frappe, "enqueue").start()

	def run_jobs(self):
		from unittest.mock import patch

		from phamos.events import team_daily_schedule

		job = "phamos.events.team_daily_schedule.run_sync_plan_in_background"
		for call in self.enqueue.call_args_list:
			if call.args[:1] != (job,):
				continue  # other jobs of a Department save, e.g. the web profile mirror
			kwargs = call.kwargs
			with patch.object(frappe, "publish_realtime"), patch.object(frappe.db, "commit"):
				team_daily_schedule.run_sync_plan_in_background(kwargs["doctype"], kwargs["name"], kwargs["plan"], kwargs["user"])
		self.enqueue.reset_mock()

	def tearDown(self):
		from unittest.mock import patch

		patch.stopall()
		frappe.set_user("Administrator")
		frappe.db.rollback()

	def _department(self, company):
		existing = frappe.get_all("Department", filters={"company": company, "is_group": 0}, pluck="name", limit=1)
		if existing:
			return existing[0]
		return frappe.get_doc(
			{"doctype": "Department", "department_name": "_Test GM Appointments", "company": company}
		).insert().name

	def _mailbox(self):
		"""A bare Email Account (a real insert would log in) with a Mailcow DAV password."""
		if not frappe.db.exists("Email Account", self.MAILBOX):
			account = frappe.new_doc("Email Account")
			account.update({"name": self.MAILBOX, "email_account_name": self.MAILBOX, "email_id": self.MAILBOX})
			account.db_insert()
		if not frappe.db.exists("Mailcow DAV Password", {"user": self.MAILBOX}):
			frappe.get_doc({"doctype": "Mailcow DAV Password", "user": self.MAILBOX, "dav_password": "x"}).insert()

	def _appointment(self, **values):
		return {
			"subject": "All-hands",
			"location": "Office",
			"start": "2026-12-01 10:00:00",
			"end": "2026-12-01 11:00:00",
			"email_account": self.MAILBOX,
			"required_attendees": ["a@example.com", "b@example.com"],
			"optional_attendees": ["c@example.com"],
			**values,
		}

	def _department_fields(self):
		doc = frappe.get_doc("Department", self.department).as_dict()
		# lft / rgt / old_parent are the tree's own bookkeeping, which every Department save updates.
		ignored = ("event_schedule", "modified", "modified_by", "lft", "rgt", "old_parent")
		return {k: v for k, v in doc.items() if k not in ignored}

	def test_the_role_alone_plans_an_appointment(self):
		before = self._department_fields()
		frappe.set_user(_make_user(MANAGER, [setup.GENERAL_MANAGEMENT_ROLE]))
		self.assertFalse(frappe.has_permission("Department", "write"))

		saved = gm.save_appointment(self._appointment())
		self.assertEqual(saved["required_attendees"], ["a@example.com", "b@example.com"])
		self.assertEqual(saved["optional_attendees"], ["c@example.com"])
		# Returned right away: the invite goes out after the commit.
		self.assertFalse(saved["synced"])
		self.put.assert_not_called()
		sync_jobs = [c for c in self.enqueue.call_args_list if c.args[:1] == ("phamos.events.team_daily_schedule.run_sync_plan_in_background",)]
		self.assertEqual(len(sync_jobs), 1)
		self.assertTrue(sync_jobs[0].kwargs["enqueue_after_commit"])
		self.run_jobs()
		self.put.assert_called_once()

		listed = gm.get_company_appointments()
		self.assertEqual(listed["department"], self.department)
		self.assertIn(saved["name"], [a["name"] for a in listed["appointments"]])
		# Stored on the Department, so the invite's source link points there (not to Company).
		self.assertEqual(frappe.db.get_value("Team Daily Schedule", saved["name"], "parenttype"), "Department")
		self.assertIn("/app/department/", frappe.db.get_value("Team Daily Schedule", saved["name"], "description"))

		frappe.set_user("Administrator")
		self.assertEqual(self._department_fields(), before)

	def test_update_and_delete(self):
		saved = gm.save_appointment(self._appointment())
		self.run_jobs()
		updated = gm.save_appointment(self._appointment(name=saved["name"], subject="All-hands, moved"))
		self.assertEqual(updated["name"], saved["name"])
		self.assertEqual(updated["subject"], "All-hands, moved")

		self.run_jobs()
		gm.delete_appointment(saved["name"])
		self.delete.assert_not_called()
		self.run_jobs()
		self.delete.assert_called()
		self.assertNotIn(saved["name"], [a["name"] for a in gm.get_company_appointments()["appointments"]])

	def test_an_appointment_cannot_change_while_its_invite_is_being_sent(self):
		"""A second save would start a second job with the same version, which can mark the first
		one failed after its wait (review of !1231)."""
		saved = gm.save_appointment(self._appointment())
		self.assertTrue(saved["sending"])
		with self.assertRaises(frappe.ValidationError):
			gm.save_appointment(self._appointment(name=saved["name"], subject="Changed meanwhile"))
		with self.assertRaises(frappe.ValidationError):
			gm.delete_appointment(saved["name"])

		self.run_jobs()
		listed = {a["name"]: a for a in gm.get_company_appointments()["appointments"]}
		self.assertFalse(listed[saved["name"]]["sending"])
		gm.save_appointment(self._appointment(name=saved["name"], subject="Changed afterwards"))

	def test_a_row_left_pending_by_a_dead_job_can_change_again(self):
		from phamos.events import team_daily_schedule

		saved = gm.save_appointment(self._appointment())
		long_ago = frappe.utils.add_to_date(
			frappe.utils.now_datetime(), seconds=-team_daily_schedule.MAX_ROW_SEND_SECONDS - 1
		)
		frappe.db.set_value("Team Daily Schedule", saved["name"], "mailcow_last_sync_at", long_ago)
		gm.save_appointment(self._appointment(name=saved["name"], subject="Job died, try again"))

	def test_a_cancelled_incomplete_row_is_not_being_sent(self):
		"""After an incomplete row's cancel it is unsynced, error-free and freshly stamped, like a pending one."""
		from phamos.events import team_daily_schedule

		row = frappe._dict(mailcow_synced=0, mailcow_last_error="", mailcow_last_sync_at=frappe.utils.now_datetime())
		self.assertFalse(team_daily_schedule.row_is_being_sent(row))
		row.update(subject="All-hands", start="2026-12-01 10:00:00", end="2026-12-01 11:00:00")
		self.assertTrue(team_daily_schedule.row_is_being_sent(row))

	def test_refuses_rows_outside_the_company_and_bad_input(self):
		with self.assertRaises(frappe.ValidationError):
			gm.save_appointment(self._appointment(name="not-a-row"))
		with self.assertRaises(frappe.ValidationError):
			gm.delete_appointment("not-a-row")
		with self.assertRaises(frappe.ValidationError):
			gm.save_appointment(self._appointment(email_account="no-dav@example.com"))
		with self.assertRaises(frappe.ValidationError):
			gm.save_appointment(self._appointment(end="2026-12-01 09:00:00"))
		with self.assertRaises(frappe.ValidationError):
			gm.save_appointment(self._appointment(required_attendees=["not an email"]))
		# AI review of !1203: lists only, a repeat needs its frequency, until not before start
		with self.assertRaises(frappe.ValidationError):
			gm.save_appointment(self._appointment(required_attendees="a@example.com"))
		with self.assertRaises(frappe.ValidationError):
			gm.save_appointment(self._appointment(repeat_this_event=1, repeat_on=""))
		with self.assertRaises(frappe.ValidationError):
			gm.save_appointment(self._appointment(repeat_this_event=1, repeat_on="Weekly", repeat_till="2026-11-01"))

	def test_a_weekly_start_on_an_unticked_weekday_stays(self):
		"""The chosen start is the first appointment, also when its weekday isn't ticked; the repeat
		continues on the ticked days after it (Wolfram, 2026-11-19). 2026-12-01 is a Tuesday."""
		saved = gm.save_appointment(
			self._appointment(repeat_this_event=1, repeat_on="Weekly", monday=1, thursday=1, repeat_till="2026-12-01")
		)
		self.assertEqual(str(saved["start"]), "2026-12-01 10:00:00")
		self.assertEqual(str(saved["end"]), "2026-12-01 11:00:00")
		self.assertEqual((saved["monday"], saved["tuesday"], saved["thursday"]), (1, 0, 1))

	def test_needs_the_role(self):
		frappe.set_user(_make_user(PROJECTS_USER, ["Projects User"]))
		for call in (
			gm.get_company_appointments,
			gm.get_appointment_options,
			lambda: gm.save_appointment(self._appointment()),
		):
			with self.assertRaises(frappe.PermissionError):
				call()

	def test_options_group_people_by_department(self):
		employee = frappe.get_doc(
			{
				"doctype": "Employee",
				"first_name": "_Test",
				"last_name": "Appointments",
				"gender": frappe.db.get_value("Gender", {}, "name"),
				"date_of_birth": "1990-01-01",
				"date_of_joining": "2020-01-01",
				"company": self.company,
				"department": self.department,
				"company_email": "test-appointments@example.com",
				"status": "Active",
			}
		).insert()
		options = gm.get_appointment_options()
		self.assertIn(self.MAILBOX, [m.name for m in options["mailboxes"]])
		group = next(g for g in options["departments"] if g["department"] == self.department)
		self.assertIn(
			{"email": "test-appointments@example.com", "name": employee.employee_name, "image": None},
			group["people"],
		)


class TestContracts(FrappeTestCase):
	"""Contracts list (#2148): standard Contract, typed by Contract Type, filtered in the cockpit."""

	CUSTOMER = "_Test GM Contracts Customer"

	@classmethod
	def setUpClass(cls):
		# FrappeTestCase rolls back once per class, so the contracts are made once, not per test.
		super().setUpClass()
		setup.after_migrate()
		contracts_setup.after_migrate()
		if not frappe.db.exists("Customer", cls.CUSTOMER):
			frappe.get_doc(
				{
					"doctype": "Customer",
					"customer_name": cls.CUSTOMER,
					"customer_type": "Company",
					"customer_group": frappe.db.get_value("Customer Group", {"is_group": 0}),
				}
			).insert(ignore_permissions=True)
		cls.manager = _make_user(MANAGER, [setup.GENERAL_MANAGEMENT_ROLE])
		cls.avv = cls._contract("AVV", end_date=add_days(today(), 20))
		cls.nda = cls._contract("NDA", end_date=add_days(today(), 200))

	def tearDown(self):
		frappe.set_user("Administrator")

	@classmethod
	def _contract(cls, contract_type, end_date):
		return frappe.get_doc(
			{
				"doctype": "Contract",
				"party_type": "Customer",
				"party_name": cls.CUSTOMER,
				"custom_contract_type": contract_type,
				"start_date": today(),
				"end_date": end_date,
				"contract_terms": "Test terms",
			}
		).insert(ignore_permissions=True).name

	def _names(self, **filters):
		return {row["name"] for row in gm.get_contracts(**filters)}

	def test_setup_adds_the_type_field_and_first_types(self):
		self.assertTrue(frappe.get_meta("Contract").has_field(contracts_setup.TYPE_FIELD))
		self.assertTrue(frappe.db.exists("Contract Type", "AVV"))
		self.assertTrue(frappe.db.exists("Contract Type", "NDA"))
		contracts_setup.after_migrate()
		self.assertEqual(frappe.db.count("Contract Type", {"name": "AVV"}), 1)

	def test_the_role_lists_and_filters_contracts(self):
		frappe.set_user(self.manager)
		self.assertIn("AVV", gm.get_contract_options()["types"])
		self.assertTrue({self.avv, self.nda} <= self._names(party=self.CUSTOMER))
		self.assertEqual(self._names(party=self.CUSTOMER, contract_type="AVV"), {self.avv})
		self.assertEqual(self._names(party=self.CUSTOMER, ending_within_days=30), {self.avv})
		self.assertEqual(self._names(party=self.CUSTOMER, status="Active"), set())
		# A typed % is a plain character, not a wildcard that matches every contract.
		self.assertEqual(self._names(party="%"), set())

	def test_needs_the_role(self):
		frappe.set_user(_make_user(PROJECTS_USER, ["Projects User"]))
		with self.assertRaises(frappe.PermissionError):
			gm.get_contracts()

	def test_refuses_bad_filters(self):
		frappe.set_user(self.manager)
		with self.assertRaises(frappe.ValidationError):
			gm.get_contracts(status="Signed")
		with self.assertRaises(frappe.ValidationError):
			gm.get_contracts(ending_within_days=-1)
		for bad in ("abc", "1.5", "99999", "1e9"):
			with self.subTest(bad=bad), self.assertRaises(frappe.ValidationError):
				gm.get_contracts(ending_within_days=bad)
