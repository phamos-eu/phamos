# Copyright (c) 2026, phamos.eu and Contributors
# See license.txt

"""Plan changes with both sides' consent and the baseline of a planning session (#1971)."""

import json

import frappe
from frappe.tests.utils import FrappeTestCase

from phamos.phamos.doctype.implementation_baseline.implementation_baseline import (
	create_baseline,
	get_baseline_variance,
)
from phamos.phamos.doctype.implementation_change.implementation_change import (
	AWAITING,
	_insert_change,
	agree_change,
	confirm_change,
	dispute_change,
	propose_change,
	reject_change,
)
from phamos.phamos.doctype.implementation_feature.test_implementation_feature import make_feature
from phamos.phamos.doctype.stakeholder_meeting.test_stakeholder_meeting import (
	make_chapter,
	make_implementation,
	set_progress,
)

CUSTOMER_USER = "ic-change-customer@example.com"
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
		# chapters are not proposed through propose_change; the Desk form inserts the change
		name = _insert_change(
			self.implementation.name,
			"Implementation Chapter",
			chapter.name,
			"Dates",
			{"planned_start": "2026-01-01", "target_date": "2026-06-30"},
			{"planned_start": "2026-02-01", "target_date": "2026-09-30"},
			status="Proposed",
			agreed_by_phamos="Administrator",
		).name

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
		reject_change(name)
		frappe.set_user(OUTSIDER_USER)
		# an existing (rejected) change and a missing one give the same answer
		self.assertRaises(frappe.PermissionError, agree_change, name)
		self.assertRaises(frappe.PermissionError, agree_change, "CHG-99999")
