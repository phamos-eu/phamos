# Copyright (c) 2026, phamos.eu and contributors
# For license information, please see license.txt

"""Implementation Change (#1971): no change to an agreed plan value without the other side's consent.

Two ways in:
- A proposal (`propose_change`) by a phamos user or a customer stakeholder. The other side agrees
  or rejects. Once both agreed, it is applied: right away, or when the planning session it is
  linked to is submitted.
- A direct Desk edit by a PM (`record_direct_edits`, from on_update). The edit is saved as before
  and recorded as "Applied – awaiting customer"; the customer confirms or disputes it. A dispute
  undoes nothing; it goes on the next session's agenda.

Direct edits are recorded once the implementation has a baseline, i.e. after the first planning
session. Before that the plan is still being drafted together.

Chapters keep their own lock: their agreed content changes only through a Stakeholder Meeting,
which records what changed as Applied (`record_meeting_chapter_changes`).

Releases (#1986) are triaged the same way: a new target date ("Dates", `target_date`), a new
order of their features ("Rank", `ranking`: the feature names in the new order) or a feature
moved to another release ("Rank", `feature` + `to_release`). Their direct edits are recorded too.
"""

import json

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import getdate, now_datetime, today

from phamos.phamos.doctype.implementation_release.implementation_release import ranking_of

AWAITING = "Applied – awaiting customer"

# Agreed plan values per target doctype: field → change type. Status and current level of a
# feature are daily work, not agreed values. Fields the site does not have yet (the capacity
# share of #1986) are skipped.
AGREED_FIELDS = {
	"Implementation Feature": {
		"planned_start": "Dates",
		"target_date": "Dates",
		"priority": "Priority",
		"target_level": "Target level",
		"definition_of_done": "Definition of done",
	},
	"Implementation": {
		"max_parallel_chapters": "WIP limit",
		"max_parallel_features": "WIP limit",
		"team_capacity_share": "Capacity share",
	},
	"Implementation Release": {
		"target_date": "Dates",
	},
	"Implementation Chapter": {
		"chapter_title": "Scope change",
		"full_chapter_description": "Scope change",
		"planned_start": "Dates",
		"target_date": "Dates",
		"target_level": "Target level",
	},
}
# What a proposal for a new feature (Scope add without a target) may set.
NEW_FEATURE_FIELDS = (
	"title",
	"description",
	"module",
	"priority",
	"estimated_hours",
	"planned_start",
	"target_date",
	"target_level",
	"definition_of_done",
)


class ImplementationChange(Document):
	def validate(self):
		if self.target_doctype not in AGREED_FIELDS:
			frappe.throw(_("Changes can be recorded for features, releases, chapters and implementations only."))
		before = self.get_doc_before_save()
		if before and before.status in ("Applied", "Rejected") and self.has_value_changed("proposed_values"):
			frappe.throw(_("An applied or rejected change cannot be edited. Propose a new change instead."))
		if self.status in ("Proposed", "Agreed") and self.stakeholder_meeting:
			check_planning_meeting(self.stakeholder_meeting, self.implementation)

	@property
	def values(self):
		return json.loads(self.proposed_values or "{}")

	def apply(self):
		"""Write the agreed values to the target and mark the change Applied."""
		if self.change_type == "Scope add" and not self.target_name:
			feature = frappe.get_doc(
				{"doctype": "Implementation Feature", "implementation": self.implementation, "status": "Agreed", **self.values}
			)
			feature.flags.from_implementation_change = True
			feature.insert(ignore_permissions=True)
			self.target_name = feature.name
		elif self.target_doctype == "Implementation Release" and self.change_type == "Rank":
			from phamos.phamos.doctype.implementation_release.implementation_release import apply_ranking

			self.old_values = frappe.as_json(apply_ranking(self.target_name, self.values))
		else:
			target = frappe.get_doc(self.target_doctype, self.target_name)
			# the values as they are now, which may differ from those at the time of the proposal
			self.old_values = frappe.as_json({field: target.get(field) for field in self.values})
			target.update(self.values)
			if self.change_type == "Definition of done" and self.target_doctype == "Implementation Feature":
				_set_dod_agreement(target, self.agreed_by_customer)
			target.flags.from_implementation_change = True
			target.save(ignore_permissions=True)
		self.status = "Applied"
		self.applied_on = now_datetime()
		self.save(ignore_permissions=True)


def check_planning_meeting(meeting, implementation):
	"""An open change may wait only for a Planning meeting of its implementation that is not yet
	submitted: only the submit of such a meeting applies it (apply_agreed_changes_of_meeting)."""
	from phamos.setup.implementation_cockpit import PLANNING_MEETING_TYPE

	values = frappe.db.get_value(
		"Stakeholder Meeting", meeting, ["implementation", "docstatus", "meeting_type"], as_dict=True
	)
	if not values or values.implementation != implementation:
		frappe.throw(_("The meeting belongs to another implementation."))
	if values.docstatus != 0 or values.meeting_type != PLANNING_MEETING_TYPE:
		frappe.throw(_("Choose a Planning meeting that is not yet submitted."))


def _set_dod_agreement(feature, contact):
	feature.dod_agreed_on = today()
	feature.dod_agreed_by = contact


# Sides -----------------------------------------------------------------------------------------


def _customer_contact(implementation, user=None):
	"""The Contact through which `user` is a Customer stakeholder of the implementation, or None.

	Every customer stakeholder may act for the customer side until the Implementation Hero
	flag exists (#1684); then this narrows to heroes.
	"""
	from phamos.api.implementation_cockpit import _customer_implementations, is_internal_user

	user = user or frappe.session.user
	if is_internal_user(user) or implementation not in _customer_implementations(user):
		return None
	contacts = frappe.get_all("Contact", filters={"user": user}, pluck="name")
	email = frappe.db.get_value("User", user, "email")
	rows = frappe.get_all(
		"Implementation Stakeholder",
		filters={"parent": implementation, "parenttype": "Implementation", "stakeholder_organisation": "Customer"},
		fields=["contact", "email"],
	)
	for row in rows:
		if row.contact and row.contact in contacts:
			return row.contact
	for row in rows:
		if email and row.email == email and row.contact:
			return row.contact
	return contacts[0] if contacts else None


def _side(implementation):
	"""'phamos' for internal users who may change the implementation, 'customer' for a customer
	stakeholder; anyone else may not take part."""
	from phamos.api.implementation_cockpit import is_internal_user

	if is_internal_user():
		if frappe.has_permission("Implementation", "write", doc=implementation):
			return "phamos"
	elif _customer_contact(implementation):
		return "customer"
	frappe.throw(_("You cannot take part in plan changes of this implementation."), frappe.PermissionError)


# Direct edits ----------------------------------------------------------------------------------


def has_baseline(implementation):
	return bool(
		implementation
		and frappe.db.exists("Implementation Baseline", {"implementation": implementation, "is_current": 1})
	)


def record_direct_edits(doc, method=None):
	"""on_update of Implementation and Implementation Feature: record changed agreed values.

	One change per change type and save, with old and new values. Skipped while a change or a
	meeting writes the values, during migrations and imports, and before the first baseline.
	"""
	if doc.flags.from_implementation_change or frappe.flags.in_stakeholder_meeting_submit:
		return
	if frappe.flags.in_migrate or frappe.flags.in_install or frappe.flags.in_import or frappe.flags.in_patch:
		return
	implementation = doc.name if doc.doctype == "Implementation" else doc.get("implementation")
	if not has_baseline(implementation):
		return
	before = doc.get_doc_before_save()
	if not before:
		return
	meta = frappe.get_meta(doc.doctype)
	by_type = {}
	for field, change_type in AGREED_FIELDS[doc.doctype].items():
		if not meta.has_field(field):
			continue
		old, new = before.get(field), doc.get(field)
		# the form sends dates and numbers as text, the stored doc has typed values
		if str(old or "") == str(new or ""):
			continue
		old_values, new_values = by_type.setdefault(change_type, ({}, {}))
		old_values[field] = old
		new_values[field] = new
	if doc.doctype == "Implementation Feature" and before.status != doc.status and doc.status == "Dropped":
		by_type["Scope drop"] = ({"status": before.status}, {"status": "Dropped"})
	if doc.doctype == "Implementation Release":
		old_ranking = [row.feature for row in before.features]
		new_ranking = [row.feature for row in doc.features]
		# the same features in another order is a re-rank; features added or taken out change the
		# release's scope (a move between two releases gives one scope change on each)
		if sorted(old_ranking) != sorted(new_ranking):
			by_type["Scope change"] = ({"features": old_ranking}, {"features": new_ranking})
		elif old_ranking != new_ranking:
			by_type["Rank"] = ({"ranking": old_ranking}, {"ranking": new_ranking})
	for change_type, (old_values, new_values) in by_type.items():
		_insert_change(
			implementation,
			doc.doctype,
			doc.name,
			change_type,
			old_values,
			new_values,
			status=AWAITING,
			agreed_by_phamos=frappe.session.user,
			applied_on=now_datetime(),
		)


def record_feature_added(doc, method=None):
	"""after_insert of Implementation Feature: a feature added after the baseline is a scope change."""
	if doc.flags.from_implementation_change or not has_baseline(doc.implementation):
		return
	_insert_change(
		doc.implementation,
		doc.doctype,
		doc.name,
		"Scope add",
		{},
		{"title": doc.title},
		status=AWAITING,
		agreed_by_phamos=frappe.session.user,
		applied_on=now_datetime(),
	)


def record_meeting_chapter_changes(meeting):
	"""Chapter content a submitted Stakeholder Meeting changed, recorded as Applied with the meeting."""
	for row in meeting.chapter_reviews:
		snapshot_json = frappe.db.get_value(row.doctype, row.name, "submit_snapshot")
		if not snapshot_json:
			continue
		snapshot = json.loads(snapshot_json)
		before, after = snapshot.get("before") or {}, snapshot.get("after") or {}
		by_type = {}
		for field, change_type in AGREED_FIELDS["Implementation Chapter"].items():
			if field in after and str(before.get(field) or "") != str(after.get(field) or ""):
				old_values, new_values = by_type.setdefault(change_type, ({}, {}))
				old_values[field] = before.get(field)
				new_values[field] = after.get(field)
		for change_type, (old_values, new_values) in by_type.items():
			_insert_change(
				meeting.implementation,
				"Implementation Chapter",
				row.chapter,
				change_type,
				old_values,
				new_values,
				status="Applied",
				stakeholder_meeting=meeting.name,
				agreed_by_phamos=meeting.chair or frappe.session.user,
				applied_on=now_datetime(),
				reason=_("Agreed in Stakeholder Meeting {0}").format(meeting.name),
			)


def _insert_change(implementation, target_doctype, target_name, change_type, old_values, new_values, **values):
	return frappe.get_doc(
		{
			"doctype": "Implementation Change",
			"implementation": implementation,
			"target_doctype": target_doctype,
			"target_name": target_name,
			"change_type": change_type,
			"old_values": frappe.as_json(old_values),
			"proposed_values": frappe.as_json(new_values),
			"proposed_by": frappe.session.user,
			**values,
		}
	).insert(ignore_permissions=True)


def apply_agreed_changes_of_meeting(meeting):
	"""Submit of a Planning meeting: apply every Agreed change linked to it, oldest first.

	A change its target no longer accepts (a date before the start, a dropped feature) must not
	block the meeting: it is rolled back on its own, stays Agreed, and the chair is told which one
	to propose again or link to the next session.
	"""
	failed = []
	for name in frappe.get_all(
		"Implementation Change",
		filters={"stakeholder_meeting": meeting.name, "status": "Agreed"},
		pluck="name",
		order_by="creation asc",
	):
		frappe.db.savepoint("implementation_change_apply")
		try:
			frappe.get_doc("Implementation Change", name).apply()
		except frappe.ValidationError as error:
			frappe.db.rollback(save_point="implementation_change_apply")
			failed.append(f"{name}: {frappe.utils.strip_html(str(error))}")
	if failed:
		frappe.msgprint(
			_("These agreed changes could not be applied and stay Agreed:")
			+ "<br>"
			+ "<br>".join(frappe.utils.escape_html(line) for line in failed),
			indicator="orange",
		)
	return failed


# API for the cockpit ---------------------------------------------------------------------------


@frappe.whitelist()
def propose_change(
	implementation,
	target_doctype,
	change_type,
	proposed_values,
	target_name=None,
	reason=None,
	stakeholder_meeting=None,
):
	"""Propose a change to agreed plan values. The proposer's side counts as agreed.

	Returns the name of the new Implementation Change.
	"""
	side = _side(implementation)
	values = frappe.parse_json(proposed_values) or {}
	if not isinstance(values, dict) or not values:
		frappe.throw(_("Name the values to change."))
	_validate_proposal(implementation, target_doctype, target_name, change_type, values)
	_check_values_on_a_copy(implementation, target_doctype, target_name, change_type, values)
	if stakeholder_meeting:
		check_planning_meeting(stakeholder_meeting, implementation)
	change = _insert_change(
		implementation,
		target_doctype,
		target_name,
		change_type,
		_current_values(target_doctype, target_name, change_type, values),
		values,
		status="Proposed",
		reason=reason,
		stakeholder_meeting=stakeholder_meeting,
		**_consent_of(side, implementation),
	)
	return change.name


def _current_values(target_doctype, target_name, change_type, values):
	"""What the proposal would replace, kept with it so both sides see old and new."""
	if not target_name:
		return {}
	if target_doctype == "Implementation Release" and change_type == "Rank":
		return {"ranking": ranking_of(target_name)}
	return frappe.db.get_value(target_doctype, target_name, list(values), as_dict=True) or {}


def _validate_release_ranking(implementation, release, values):
	"""A new order of the same features, or one feature moved to another active release."""
	current = ranking_of(release)
	# proposed_values comes from the client: check the shape before using it
	if set(values) == {"ranking"}:
		ranking = values["ranking"]
		if (
			not isinstance(ranking, list)
			or not all(isinstance(name, str) for name in ranking)
			or sorted(ranking) != sorted(current)
		):
			frappe.throw(_("A new ranking lists the same features as the release, in the new order."))
		return
	position = values.get("position")
	if (
		set(values) - {"feature", "to_release", "position"}
		or not isinstance(values.get("feature"), str)
		or not isinstance(values.get("to_release"), str)
		or not (position is None or (isinstance(position, int) and not isinstance(position, bool) and position > 0))
	):
		frappe.throw(_("Name the new ranking, or the feature and the release to move it to."))
	if values["feature"] not in current:
		frappe.throw(_("Feature {0} is not in this release.").format(values["feature"]))
	other = frappe.db.get_value(
		"Implementation Release", values["to_release"], ["implementation", "status"], as_dict=True
	)
	if (
		values["to_release"] == release
		or not other
		or other.implementation != implementation
		or other.status not in ("Planned", "In Progress")
	):
		frappe.throw(_("Move the feature to another planned release of this implementation."))


def _check_values_on_a_copy(implementation, target_doctype, target_name, change_type, values):
	"""Refuse values the target would refuse, to the proposer, before the other side sees them.

	The values go onto an unsaved copy of the target, which runs the field checks and the
	target's own validate (a date before the start, a negative limit, ...). Nothing is saved; the
	target's warnings are muted. A release ranking is checked by _validate_release_ranking.
	"""
	if target_doctype == "Implementation Release" and change_type == "Rank":
		return
	if target_name:
		doc = frappe.get_doc(target_doctype, target_name)
		doc.update(values)
	else:
		doc = frappe.get_doc(
			{"doctype": "Implementation Feature", "implementation": implementation, "status": "Agreed", **values}
		)
	doc.flags.from_implementation_change = True
	doc._action = "save"  # Frappe's link check reads it; set by save() otherwise
	muted = frappe.flags.mute_messages
	frappe.flags.mute_messages = True
	try:
		for field in values:
			df = doc.meta.get_field(field)
			if df and df.fieldtype == "Date" and values[field]:
				getdate(values[field])
			elif df and df.fieldtype in ("Int", "Float", "Percent") and values[field] not in (None, ""):
				if isinstance(values[field], bool) or not isinstance(values[field], (int, float, str)):
					raise ValueError(field)
				float(values[field])
		doc._validate_mandatory()
		doc._validate_selects()
		doc._validate_non_negative()
		doc._validate_length()
		doc._validate_links()
		doc.run_method("validate")
	except frappe.ValidationError:
		raise
	except Exception:
		frappe.throw(_("These values are not valid for {0}.").format(_(target_doctype)))
	finally:
		frappe.flags.mute_messages = muted


def _validate_proposal(implementation, target_doctype, target_name, change_type, values):
	if change_type == "Scope add" and target_doctype == "Implementation Feature" and not target_name:
		unknown = set(values) - set(NEW_FEATURE_FIELDS)
		if unknown or not values.get("title"):
			frappe.throw(
				_("A new feature needs a title and may set only: {0}").format(", ".join(NEW_FEATURE_FIELDS))
			)
		return
	if target_doctype not in ("Implementation Feature", "Implementation", "Implementation Release"):
		# chapters change through a Stakeholder Meeting only
		frappe.throw(_("Changes can be proposed for features, releases and the implementation."))
	if not target_name or not frappe.db.exists(target_doctype, target_name):
		frappe.throw(_("Choose the record to change."))
	owner = (
		target_name
		if target_doctype == "Implementation"
		else frappe.db.get_value(target_doctype, target_name, "implementation")
	)
	if owner != implementation:
		frappe.throw(_("The record belongs to another implementation."))
	if target_doctype == "Implementation Release":
		# a released or cancelled release is history: it is not re-planned, and stays out of the cut line
		if frappe.db.get_value("Implementation Release", target_name, "status") not in ("Planned", "In Progress"):
			frappe.throw(_("Only planned releases can be changed."))
		if change_type == "Rank":
			_validate_release_ranking(implementation, target_name, values)
			return
	if change_type == "Scope drop":
		if target_doctype != "Implementation Feature" or values != {"status": "Dropped"}:
			frappe.throw(_("Dropping a feature sets its status to Dropped and nothing else."))
		return
	meta = frappe.get_meta(target_doctype)
	allowed = {
		field
		for field, kind in AGREED_FIELDS[target_doctype].items()
		if kind == change_type and meta.has_field(field)
	}
	if not allowed or not set(values) <= allowed:
		frappe.throw(
			_("A change of type {0} may set only: {1}").format(_(change_type), ", ".join(sorted(allowed)) or "-")
		)


def _consent_of(side, implementation):
	if side == "phamos":
		return {"agreed_by_phamos": frappe.session.user}
	return {"agreed_by_customer": _customer_contact(implementation)}


def _get_change(name, statuses):
	"""The change and the caller's side. The side is checked before anything about the change is
	told: an outsider learns neither whether it exists nor its status."""
	implementation = frappe.db.get_value("Implementation Change", name, "implementation")
	if not implementation:
		frappe.throw(_("You cannot take part in plan changes of this implementation."), frappe.PermissionError)
	side = _side(implementation)
	change = frappe.get_doc("Implementation Change", name)
	if change.status not in statuses:
		frappe.throw(_("This change is {0} and cannot be changed that way.").format(_(change.status)))
	return change, side


@frappe.whitelist()
def agree_change(name, contact=None):
	"""The other side agrees. With both sides agreed the change is applied, unless it waits for
	its planning session. Returns the new status.

	A phamos user may record the customer's agreement given elsewhere (a call, a meeting) by
	naming the customer's Contact, as for confirm_change.
	"""
	change, side = _get_change(name, ("Proposed",))
	if side == "phamos" and contact:
		if change.agreed_by_customer:
			frappe.throw(_("The customer has agreed already."))
		change.agreed_by_customer = _customer_side_contact(change, contact)
		change.agreed_by_phamos = change.agreed_by_phamos or frappe.session.user
	else:
		if (side == "phamos" and change.agreed_by_phamos) or (side == "customer" and change.agreed_by_customer):
			frappe.throw(_("Your side has agreed already. The other side decides now."))
		change.update(_consent_of(side, change.implementation))
	change.status = "Agreed"
	change.decided_on = now_datetime()
	change.save(ignore_permissions=True)
	if not change.stakeholder_meeting:
		change.apply()
	return change.status


@frappe.whitelist()
def reject_change(name, reason=None):
	"""Either side rejects a proposal; the proposer withdraws it this way too."""
	change = _get_change(name, ("Proposed", "Agreed"))[0]
	change.status = "Rejected"
	change.decided_on = now_datetime()
	if reason:
		change.reason = "\n".join(filter(None, [change.reason, reason]))
	change.save(ignore_permissions=True)
	return change.status


@frappe.whitelist()
def confirm_change(name, contact=None):
	"""The customer confirms a direct edit (or a disputed one after talking it through).

	A phamos user may record a confirmation the customer gave elsewhere (a call, a meeting) by
	naming the customer's Contact.
	"""
	change = _get_change(name, (AWAITING, "Disputed"))[0]
	contact = _customer_side_contact(change, contact)
	change.agreed_by_customer = contact
	change.status = "Applied"
	change.decided_on = now_datetime()
	change.save(ignore_permissions=True)
	if change.change_type == "Definition of done" and change.target_doctype == "Implementation Feature":
		feature = frappe.get_doc("Implementation Feature", change.target_name)
		# only when the text is still the one confirmed
		if (feature.definition_of_done or "") == (change.values.get("definition_of_done") or ""):
			_set_dod_agreement(feature, contact)
			feature.flags.from_implementation_change = True
			feature.save(ignore_permissions=True)
	return change.status


@frappe.whitelist()
def dispute_change(name, reason, contact=None):
	"""The customer disputes a direct edit. Nothing is undone; it goes on the next session's agenda."""
	if not (reason or "").strip():
		frappe.throw(_("Say why you dispute the change."))
	change = _get_change(name, (AWAITING,))[0]
	_customer_side_contact(change, contact)
	change.agreed_by_customer = None
	change.dispute_reason = reason
	change.status = "Disputed"
	change.decided_on = now_datetime()
	change.save(ignore_permissions=True)
	return change.status


def _customer_side_contact(change, contact=None):
	"""The customer Contact deciding: the session user's own, or the one a phamos user names."""
	side = _side(change.implementation)
	if side == "customer":
		return _customer_contact(change.implementation)
	if not contact:
		frappe.throw(_("Name the customer contact who decided."))
	customer_contacts = frappe.get_all(
		"Implementation Stakeholder",
		filters={
			"parent": change.implementation,
			"parenttype": "Implementation",
			"stakeholder_organisation": "Customer",
		},
		pluck="contact",
	)
	if contact not in customer_contacts:
		frappe.throw(_("{0} is not a customer stakeholder of this implementation.").format(contact))
	return contact
