# Copyright (c) 2026, phamos.eu and Contributors
# See license.txt

"""Plan changes with both sides' consent and the baseline of a planning session (#1971)."""

import json
from unittest.mock import patch
from urllib.parse import quote

import frappe
from frappe.tests.utils import FrappeTestCase

from phamos.phamos.doctype.implementation_baseline.implementation_baseline import (
	create_baseline,
	get_baseline_variance,
)
from phamos.phamos.doctype.implementation_change.implementation_change import (
	AWAITING,
	agree_change,
	confirm_change,
	dispute_change,
	reject_change,
	withdraw_change,
)
from phamos.phamos.doctype.implementation_change.implementation_change import (
	propose_change as _propose_change,
)
from phamos.phamos.doctype.implementation_feature.test_implementation_feature import make_feature
from phamos.phamos.doctype.stakeholder_meeting.test_stakeholder_meeting import (
	make_chapter,
	make_implementation,
	set_progress,
)

CUSTOMER_USER = "ic-change-customer@example.com"
PM_USER = "ic-change-pm@example.com"
OUTSIDER_USER = "ic-change-outsider@example.com"


def _website_user(email):
	if not frappe.db.exists("User", email):
		frappe.get_doc(
			{"doctype": "User", "email": email, "first_name": "IC", "user_type": "Website User", "send_welcome_email": 0}
		).insert(ignore_permissions=True)
	contact = frappe.db.get_value("Contact", {"user": email})
	if not contact:
		contact = (
			frappe.get_doc({"doctype": "Contact", "first_name": email.split("@")[0], "user": email})
			.insert(ignore_permissions=True)
			.name
		)
	return contact


def propose_change(*args, **kwargs):
	"""The cockpit's propose_change with the reason it needs (#2219); the reason's own test calls
	it without."""
	kwargs.setdefault("reason", "Test")
	return _propose_change(*args, **kwargs)


def changes_of(implementation, **filters):
	return frappe.get_all(
		"Implementation Change",
		filters={"implementation": implementation, **filters},
		fields=["name", "status", "change_type", "old_values", "proposed_values", "target_name"],
		order_by="creation asc",
	)


class TestImplementationChange(FrappeTestCase):
	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		cls.contact = _website_user(CUSTOMER_USER)
		_website_user(OUTSIDER_USER)

	def setUp(self):
		frappe.set_user("Administrator")
		# reload: inserting an implementation updates it again in hooks
		self.implementation = frappe.get_doc("Implementation", make_implementation().name)
		self.implementation.show_on_customer_portal = 1
		self.implementation.append(
			"stakeholders", {"contact": self.contact, "full_name": "IC Customer", "stakeholder_organisation": "Customer"}
		)
		self.implementation.save()
		self.feature = make_feature(
			self.implementation.name, planned_start="2026-12-01", target_date="2026-12-20", status="Agreed"
		)

	def tearDown(self):
		frappe.set_user("Administrator")

	def as_customer(self):
		frappe.set_user(CUSTOMER_USER)

	# direct edits

	def test_direct_edits_are_recorded_only_after_the_baseline(self):
		self.feature.target_date = "2026-12-24"
		self.feature.save()
		self.assertEqual(changes_of(self.implementation.name), [])

		create_baseline(self.implementation.name)
		self.feature.reload()
		self.feature.target_date = "2027-01-10"
		self.feature.priority = "High"
		self.feature.current_level = 2  # daily work, not recorded
		self.feature.save()
		changes = {row.change_type: row for row in changes_of(self.implementation.name)}
		self.assertEqual(set(changes), {"Dates", "Priority"})
		dates = changes["Dates"]
		self.assertEqual(dates.status, AWAITING)
		self.assertEqual(json.loads(dates.old_values), {"target_date": "2026-12-24"})
		self.assertEqual(json.loads(dates.proposed_values), {"target_date": "2027-01-10"})

	def test_wip_limit_drop_and_new_feature_after_the_baseline(self):
		create_baseline(self.implementation.name)
		implementation = frappe.get_doc("Implementation", self.implementation.name)
		implementation.max_parallel_features = 3
		implementation.save()
		self.feature.reload()
		self.feature.status = "Dropped"
		self.feature.save()
		make_feature(self.implementation.name, title="Added later")
		self.assertEqual(
			[row.change_type for row in changes_of(self.implementation.name)], ["WIP limit", "Scope drop", "Scope add"]
		)

	def test_customer_confirms_or_disputes_a_direct_edit(self):
		create_baseline(self.implementation.name)
		self.feature.reload()
		self.feature.target_date = "2027-01-10"
		self.feature.save()
		self.feature.reload()
		self.feature.priority = "High"
		self.feature.save()
		dates, priority = (row.name for row in changes_of(self.implementation.name))

		self.as_customer()
		self.assertEqual(confirm_change(dates), "Applied")
		self.assertRaises(frappe.ValidationError, dispute_change, priority, "")
		self.assertEqual(dispute_change(priority, "We need it in December"), "Disputed")
		# a dispute undoes nothing
		self.assertEqual(frappe.db.get_value("Implementation Feature", self.feature.name, "priority"), "High")
		self.assertEqual(frappe.db.get_value("Implementation Change", dates, "agreed_by_customer"), self.contact)

		# phamos records a confirmation given in a call by naming the customer's contact
		frappe.set_user("Administrator")
		self.assertRaises(frappe.ValidationError, confirm_change, priority)
		self.assertEqual(confirm_change(priority, contact=self.contact), "Applied")

	def test_outsiders_cannot_take_part(self):
		frappe.set_user(OUTSIDER_USER)
		self.assertRaises(
			frappe.PermissionError,
			propose_change,
			self.implementation.name,
			"Implementation Feature",
			"Priority",
			{"priority": "High"},
			target_name=self.feature.name,
		)

	# proposals

	def test_proposal_applies_only_after_both_sides_agree(self):
		name = propose_change(
			self.implementation.name, "Implementation Feature", "Dates", {"target_date": "2027-02-01"}, self.feature.name
		)
		self.assertEqual(frappe.db.get_value("Implementation Change", name, "status"), "Proposed")
		self.assertEqual(str(frappe.db.get_value("Implementation Feature", self.feature.name, "target_date")), "2026-12-20")
		# the proposing side cannot agree a second time
		self.assertRaises(frappe.ValidationError, agree_change, name)

		self.as_customer()
		self.assertEqual(agree_change(name), "Applied")
		self.assertEqual(str(frappe.db.get_value("Implementation Feature", self.feature.name, "target_date")), "2027-02-01")
		change = frappe.get_doc("Implementation Change", name)
		self.assertEqual((change.agreed_by_phamos, change.agreed_by_customer), ("Administrator", self.contact))

	def test_reject_and_wrong_fields(self):
		self.as_customer()
		name = propose_change(
			self.implementation.name, "Implementation Feature", "Priority", {"priority": "High"}, self.feature.name
		)
		frappe.set_user("Administrator")
		self.assertEqual(reject_change(name, "Not now"), "Rejected")
		self.assertRaises(frappe.ValidationError, agree_change, name)
		self.assertEqual(frappe.db.get_value("Implementation Feature", self.feature.name, "priority"), "Medium")
		# a type may only set its own fields
		self.assertRaises(
			frappe.ValidationError,
			propose_change,
			self.implementation.name,
			"Implementation Feature",
			"Priority",
			{"target_date": "2027-01-01"},
			self.feature.name,
		)
		# features of another implementation
		other = make_feature(make_implementation().name, title="Elsewhere")
		self.assertRaises(
			frappe.ValidationError,
			propose_change,
			self.implementation.name,
			"Implementation Feature",
			"Priority",
			{"priority": "High"},
			other.name,
		)

	def test_agreed_definition_of_done_sets_the_feature_fields(self):
		name = propose_change(
			self.implementation.name,
			"Implementation Feature",
			"Definition of done",
			{"definition_of_done": "Batches printed on the pick list"},
			self.feature.name,
		)
		self.as_customer()
		agree_change(name)
		feature = frappe.get_doc("Implementation Feature", self.feature.name)
		self.assertEqual(feature.definition_of_done, "Batches printed on the pick list")
		self.assertEqual(feature.dod_agreed_by, self.contact)
		self.assertTrue(feature.dod_agreed_on)

	def test_new_feature_proposed_by_the_customer(self):
		self.as_customer()
		name = propose_change(
			self.implementation.name, "Implementation Feature", "Scope add", {"title": "Label printer", "priority": "High"}
		)
		frappe.set_user("Administrator")
		agree_change(name)
		feature = frappe.db.get_value("Implementation Change", name, "target_name")
		self.assertEqual(frappe.db.get_value("Implementation Feature", feature, "title"), "Label printer")

	# planning session and baseline

	def test_planning_meeting_applies_agreed_changes_and_sets_a_baseline(self):
		from phamos.setup.implementation_cockpit import after_migrate

		after_migrate()  # the Planning meeting type
		chapter = make_chapter(self.implementation.name, title="Warehouse")
		first = create_baseline(self.implementation.name)
		meeting = frappe.get_doc(
			{
				"doctype": "Stakeholder Meeting",
				"implementation": self.implementation.name,
				"meeting_type": "Planning",
				"meeting_date": "2026-12-01",
				"chair": "Administrator",
			}
		).insert()
		self.as_customer()
		name = propose_change(
			self.implementation.name,
			"Implementation Feature",
			"Dates",
			{"target_date": "2027-03-01"},
			self.feature.name,
			stakeholder_meeting=meeting.name,
		)
		frappe.set_user("Administrator")
		self.assertEqual(agree_change(name), "Agreed")  # waits for the session

		meeting.reload()
		set_progress(meeting)
		for row in meeting.chapter_reviews:
			row.scope_change = 1
			row.proposed_chapter_title = "Warehouse and shipping"
			row.proposed_full_chapter_description = "Wider"
			row.proposed_planned_start = "2026-01-01"
			row.proposed_target_date = "2026-08-31"
		meeting.submit()

		self.assertEqual(frappe.db.get_value("Implementation Change", name, "status"), "Applied")
		self.assertEqual(str(frappe.db.get_value("Implementation Feature", self.feature.name, "target_date")), "2027-03-01")
		chapter_changes = changes_of(self.implementation.name, target_name=chapter.name)
		self.assertEqual({row.change_type for row in chapter_changes}, {"Scope change", "Dates"})
		self.assertTrue(all(row.status == "Applied" for row in chapter_changes))

		current = frappe.get_all(
			"Implementation Baseline", filters={"implementation": self.implementation.name, "is_current": 1}, pluck="name"
		)
		self.assertEqual(len(current), 1)
		self.assertNotEqual(current[0], first.name)
		self.assertEqual(frappe.db.get_value("Implementation Baseline", current[0], "stakeholder_meeting"), meeting.name)

	def test_variance_against_the_baseline(self):
		chapter = make_chapter(self.implementation.name, title="Warehouse")
		create_baseline(self.implementation.name)
		self.assertIsNone(get_baseline_variance(make_implementation().name))

		frappe.db.set_value("Implementation Feature", self.feature.name, "target_date", "2026-12-30")
		frappe.db.set_value("Implementation Chapter", chapter.name, "target_date", "2026-06-20")
		added = make_feature(self.implementation.name, title="Added later")
		dropped = make_feature(self.implementation.name, title="Will drop")
		create_baseline(self.implementation.name)
		frappe.db.set_value("Implementation Feature", dropped.name, "status", "Dropped")
		frappe.db.set_value("Implementation Feature", self.feature.name, "target_date", "2027-01-09")
		new = make_feature(self.implementation.name, title="Brand new")

		variance = get_baseline_variance(self.implementation.name)
		feature = next(row for row in variance["features"] if row["name"] == self.feature.name)
		self.assertEqual(feature["target_shift_days"], 10)
		self.assertEqual(variance["chapters"][0]["target_shift_days"], 0)
		self.assertEqual([row["name"] for row in variance["scope"]["added"]], [new.name])
		self.assertEqual([row["name"] for row in variance["scope"]["dropped"]], [dropped.name])
		self.assertNotIn(added.name, [row["name"] for row in variance["scope"]["added"]])

	def planning_meeting(self, meeting_type="Planning"):
		from phamos.setup.implementation_cockpit import after_migrate

		after_migrate()
		if not frappe.db.exists("Meeting Type", meeting_type):
			frappe.get_doc({"doctype": "Meeting Type", "meeting_type_name": meeting_type}).insert()
		return frappe.get_doc(
			{
				"doctype": "Stakeholder Meeting",
				"implementation": self.implementation.name,
				"meeting_type": meeting_type,
				"meeting_date": "2026-12-01",
				"chair": "Administrator",
			}
		).insert()

	def test_only_an_open_planning_meeting_can_carry_a_change(self):
		review = self.planning_meeting("_Test Review")
		self.assertRaises(
			frappe.ValidationError,
			propose_change,
			self.implementation.name,
			"Implementation Feature",
			"Priority",
			{"priority": "High"},
			self.feature.name,
			stakeholder_meeting=review.name,
		)

	def test_a_change_the_target_refuses_does_not_block_the_meeting(self):
		meeting = self.planning_meeting()
		name = propose_change(
			self.implementation.name,
			"Implementation Feature",
			"Dates",
			{"target_date": "2026-12-15"},
			self.feature.name,
			stakeholder_meeting=meeting.name,
		)
		self.as_customer()
		agree_change(name)
		frappe.set_user("Administrator")
		# the feature moved on since: the agreed date is now before its start and is refused at apply time
		frappe.db.set_value("Implementation Feature", self.feature.name, "planned_start", "2026-12-20")
		meeting.reload()
		set_progress(meeting)
		frappe.message_log = []
		meeting.submit()
		self.assertEqual(frappe.db.get_value("Implementation Change", name, "status"), "Agreed")
		self.assertTrue(any(name in str(message) for message in frappe.message_log))
		self.assertTrue(frappe.db.exists("Implementation Baseline", {"stakeholder_meeting": meeting.name}))

	def test_phamos_records_the_customers_agreement(self):
		name = propose_change(
			self.implementation.name, "Implementation Feature", "Priority", {"priority": "High"}, self.feature.name
		)
		self.assertRaises(frappe.ValidationError, agree_change, name, contact="Not a stakeholder")
		self.assertEqual(agree_change(name, contact=self.contact), "Applied")
		self.assertEqual(frappe.db.get_value("Implementation Change", name, "agreed_by_customer"), self.contact)

	def test_agreed_chapter_dates_apply_without_a_meeting(self):
		# #2050: a planned chapter's agreed content is locked against direct edits, but not
		# against a change both sides agreed to outside a Planning meeting
		chapter = make_chapter(self.implementation.name, title="Warehouse")
		self.assertEqual(chapter.status, "Planned")
		name = propose_change(
			self.implementation.name,
			"Implementation Chapter",
			"Dates",
			{"planned_start": "2026-02-01", "target_date": "2026-09-30"},
			chapter.name,
		)

		self.as_customer()
		self.assertEqual(agree_change(name), "Applied")
		frappe.set_user("Administrator")
		chapter.reload()
		self.assertEqual((str(chapter.planned_start), str(chapter.target_date)), ("2026-02-01", "2026-09-30"))

		# a direct edit of the dates stays locked
		chapter.target_date = "2026-12-31"
		with self.assertRaisesRegex(frappe.ValidationError, "can no longer be edited directly"):
			chapter.save()

	def test_outsiders_learn_nothing_about_a_change(self):
		name = propose_change(
			self.implementation.name, "Implementation Feature", "Priority", {"priority": "High"}, self.feature.name
		)
		reject_change(name, "Not needed")
		frappe.set_user(OUTSIDER_USER)
		# an existing (rejected) change and a missing one give the same answer
		self.assertRaises(frappe.PermissionError, agree_change, name)
		self.assertRaises(frappe.PermissionError, agree_change, "CHG-99999")

	# chapter proposals and decisions in the cockpit (#2219)

	def propose_chapter(self, chapter, values, change_type="Dates", **kwargs):
		return propose_change(
			self.implementation.name, "Implementation Chapter", change_type, values, chapter, **kwargs
		)

	def test_a_customer_proposes_a_chapters_dates_and_target_level(self):
		chapter = make_chapter(self.implementation.name, title="Warehouse")
		self.as_customer()
		dates = self.propose_chapter(chapter.name, {"target_date": "2026-07-31"}, reason="Stocktaking in June")
		level = self.propose_chapter(chapter.name, {"target_level": 4}, "Target level")
		frappe.set_user("Administrator")
		self.assertEqual(agree_change(dates), "Applied")
		self.assertEqual(agree_change(level), "Applied")
		chapter.reload()
		self.assertEqual((str(chapter.target_date), chapter.target_level), ("2026-07-31", 4))
		change = frappe.get_doc("Implementation Change", dates)
		self.assertEqual((change.reason, json.loads(change.old_values)), ("Stocktaking in June", {"target_date": "2026-06-30"}))

	def test_what_cannot_be_proposed_for_a_chapter(self):
		planned = make_chapter(self.implementation.name, title="Warehouse")
		draft = make_chapter(self.implementation.name, title="Idea", plan=False)
		cancelled = make_chapter(self.implementation.name, title="Gone")
		frappe.db.set_value("Implementation Chapter", cancelled.name, "status", "Cancelled")
		refused = {
			"Draft chapter isn't agreed": (draft.name, "Dates", {"target_date": "2026-07-31"}),
			"not planned any more": (cancelled.name, "Dates", {"target_date": "2026-07-31"}),
			"title and description change in a Stakeholder Meeting": (
				planned.name,
				"Scope change",
				{"chapter_title": "Bigger"},
			),
			"may set only": (planned.name, "Dates", {"target_level": 5}),
			"Target Date must be after Planned Start": (planned.name, "Dates", {"target_date": "2025-12-01"}),
		}
		for message, (chapter, change_type, values) in refused.items():
			with self.subTest(message), self.assertRaisesRegex(frappe.ValidationError, message):
				self.propose_chapter(chapter, values, change_type)
		self.assertEqual(changes_of(self.implementation.name), [])

	def test_one_open_proposal_per_record_and_type_and_the_proposer_withdraws(self):
		chapter = make_chapter(self.implementation.name, title="Warehouse")
		first = self.propose_chapter(chapter.name, {"target_date": "2026-07-31"})
		self.as_customer()
		with self.assertRaisesRegex(frappe.ValidationError, "A proposal for this is open"):
			self.propose_chapter(chapter.name, {"target_date": "2026-08-31"})
		# another type of change for the same chapter is a separate decision
		self.propose_chapter(chapter.name, {"target_level": 4}, "Target level")
		# only the side that proposed takes it back
		self.assertRaises(frappe.ValidationError, withdraw_change, first)
		frappe.set_user("Administrator")
		self.assertEqual(withdraw_change(first, "Wrong month"), "Withdrawn")
		self.assertEqual(frappe.db.get_value("Implementation Change", first, "decision_reason"), "Wrong month")
		self.assertRaises(frappe.ValidationError, withdraw_change, first)
		# withdrawn, it no longer blocks a new one
		self.as_customer()
		self.assertTrue(self.propose_chapter(chapter.name, {"target_date": "2026-08-31"}))

	def test_a_change_made_outside_the_cockpit_is_checked_the_same(self):
		def insert(**values):
			return frappe.get_doc(
				{
					"doctype": "Implementation Change",
					"implementation": self.implementation.name,
					"target_doctype": "Implementation Feature",
					"target_name": self.feature.name,
					"change_type": "Dates",
					"status": "Proposed",
					**values,
				}
			).insert()

		# as the Desk form saves it: no values
		with self.assertRaisesRegex(frappe.ValidationError, "proposed in the Implementation Cockpit"):
			insert()
		with self.assertRaisesRegex(frappe.ValidationError, "may set only"):
			insert(proposed_values=json.dumps({"priority": "High"}))
		other = make_feature(make_implementation().name, title="Elsewhere")
		with self.assertRaisesRegex(frappe.ValidationError, "another implementation"):
			insert(target_name=other.name, proposed_values=json.dumps({"target_date": "2027-01-31"}))
		with self.assertRaisesRegex(frappe.ValidationError, "not valid|before|after"):
			insert(proposed_values=json.dumps({"target_date": "2026-11-01"}))
		self.assertTrue(insert(proposed_values=json.dumps({"target_date": "2027-01-31"})).name)

	def test_proposing_rejecting_and_disputing_need_a_reason(self):
		self.assertRaisesRegex(
			frappe.ValidationError,
			"Give a short reason",
			_propose_change,
			self.implementation.name,
			"Implementation Feature",
			"Priority",
			{"priority": "High"},
			self.feature.name,
			reason="  ",
		)
		name = propose_change(
			self.implementation.name,
			"Implementation Feature",
			"Priority",
			{"priority": "High"},
			self.feature.name,
			reason="Go-live first",
		)
		self.as_customer()
		self.assertRaisesRegex(frappe.ValidationError, "Give a short reason", reject_change, name)
		self.assertEqual(reject_change(name, "Not before January"), "Rejected")
		change = frappe.get_doc("Implementation Change", name)
		# the decision's reason is kept apart from the proposer's
		self.assertEqual((change.reason, change.decision_reason), ("Go-live first", "Not before January"))

	def add_internal_pm(self, user=PM_USER):
		if not frappe.db.exists("User", user):
			frappe.get_doc(
				{"doctype": "User", "email": user, "first_name": "IC PM", "send_welcome_email": 0}
			).insert(ignore_permissions=True)
		contact = frappe.db.get_value("Contact", {"user": user}) or (
			frappe.get_doc({"doctype": "Contact", "first_name": "IC PM", "user": user}).insert(ignore_permissions=True).name
		)
		self.implementation.reload()
		self.implementation.append(
			"stakeholders",
			{
				"contact": contact,
				"full_name": "IC PM",
				"stakeholder_organisation": "Internal",
				"stakeholder_type": "Project Manager",
			},
		)
		self.implementation.save()

	@patch("phamos.phriend.events.send")
	def test_the_internal_pm_hears_of_the_customers_decisions(self, send):
		self.add_internal_pm()
		chapter = make_chapter(self.implementation.name, title="Warehouse")
		# a staff proposal reaches no staff
		staff = self.propose_chapter(chapter.name, {"target_date": "2026-07-31"})
		send.assert_not_called()

		self.as_customer()
		reject_change(staff, "Too late for us")
		customer = self.propose_chapter(chapter.name, {"target_date": "2026-07-15"})
		frappe.set_user("Administrator")
		self.assertEqual([c.args[:2] for c in send.call_args_list], [(PM_USER, "plan_change")] * 2)
		text, link = send.call_args_list[1].args[2:]
		self.assertIn("proposes a change to Warehouse", text)
		self.assertEqual(link, f"/implementation-cockpit/{quote(self.implementation.name)}/decisions")

		# without an internal PM the account manager hears of it
		send.reset_mock()
		self.implementation.reload()
		self.implementation.stakeholders = [r for r in self.implementation.stakeholders if r.stakeholder_organisation != "Internal"]
		self.implementation.account_manager = "Administrator"
		self.implementation.save()
		self.as_customer()
		withdraw_change(customer)
		self.propose_chapter(chapter.name, {"target_date": "2026-07-20"})
		self.assertEqual([c.args[0] for c in send.call_args_list], ["Administrator"])

