# Copyright (c) 2026, phamos.eu and contributors
# For license information, please see license.txt

"""Team Assignment: who is in which team, and when (#1974).

The assignments are the source of truth for team membership. The Team's `team_lead`,
`co_team_lead` and `team_members` are a read-only view of the assignments open today: they are
rewritten after every change of an assignment and by a daily job (an assignment that starts or
ends at midnight changes nothing by itself). Existing readers of the Team keep working.

One team at a time: an employee's assignments must not overlap, whatever the team.
"""

from datetime import date

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import add_days, getdate, today

from phamos.phamos.team_capacity_utils import get_employee_weekly_hours

LEAD = "Lead"
CO_LEAD = "Co-Lead"
MEMBER = "Member"
# Far future stand-in for an open end, so open and closed periods compare alike.
OPEN_END = date(9999, 12, 31)


class TeamAssignment(Document):
	def validate(self):
		self.validate_dates()
		self.validate_one_team_at_a_time()
		self.validate_one_lead_per_role()

	def on_update(self):
		if self.flags.skip_team_sync:
			return
		sync_team(self.team, from_assignment=True)
		previous = self.get_doc_before_save()
		if previous and previous.team != self.team:
			# may have been that team's last assignment: sync it anyway, so the person leaves it
			sync_team(previous.team, from_assignment=True)

	def on_trash(self):
		if self.flags.skip_team_sync:
			return
		# Runs before the row is deleted: leave it out of the sync explicitly.
		sync_team(self.team, exclude=self.name, from_assignment=True)

	def validate_dates(self):
		if self.until_date and getdate(self.until_date) < getdate(self.from_date):
			frappe.throw(_("The end date of a team assignment cannot be before its start date."))

	def _overlapping(self, filters):
		"""Other assignments matching `filters` whose period overlaps this one."""
		start = getdate(self.from_date)
		end = getdate(self.until_date) if self.until_date else OPEN_END
		rows = frappe.get_all(
			"Team Assignment",
			filters={"name": ["!=", self.name or ""], **filters},
			fields=["name", "team", "role", "from_date", "until_date"],
		)
		return [
			row for row in rows if getdate(row.from_date) <= end and start <= (getdate(row.until_date) if row.until_date else OPEN_END)
		]

	def validate_one_team_at_a_time(self):
		clash = self._overlapping({"employee": self.employee})
		if clash:
			row = clash[0]
			frappe.throw(
				_("{0} is already assigned to team {1} in this period ({2}). One team at a time: end that assignment first.").format(
					self.employee_name or self.employee, row.team, row.name
				)
			)

	def validate_one_lead_per_role(self):
		if self.role not in (LEAD, CO_LEAD):
			return
		clash = self._overlapping({"team": self.team, "role": self.role})
		if clash:
			frappe.throw(
				_("Team {0} already has a {1} in this period ({2}).").format(self.team, _(self.role), clash[0].name)
			)


def open_assignments(team, on_date=None, exclude=None):
	"""Assignments of `team` open on `on_date` (default today), oldest first."""
	on_date = getdate(on_date or today())
	filters = {"team": team, "from_date": ["<=", on_date]}
	if exclude:
		filters["name"] = ["!=", exclude]
	return frappe.get_all(
		"Team Assignment",
		filters=filters,
		or_filters=[["until_date", "is", "not set"], ["until_date", ">=", on_date]],
		fields=["name", "employee", "role", "designation", "from_date"],
		order_by="from_date asc, creation asc",
	)


def members_of(team, on_date):
	"""Employees in `team` on `on_date` (any role), in the order they joined."""
	return list(dict.fromkeys(row.employee for row in open_assignments(team, on_date)))


def members_between(team, from_date, until_date):
	"""{employee: [(start, end), ...]} of everyone in `team` at some point in [from_date, until_date],
	each period cut to that range. For statistics of past periods (#1975)."""
	from_date, until_date = getdate(from_date), getdate(until_date)
	rows = frappe.get_all(
		"Team Assignment",
		filters={"team": team, "from_date": ["<=", until_date]},
		or_filters=[["until_date", "is", "not set"], ["until_date", ">=", from_date]],
		fields=["employee", "from_date", "until_date"],
		order_by="from_date asc",
	)
	periods = {}
	for row in rows:
		start = max(getdate(row.from_date), from_date)
		end = min(getdate(row.until_date) if row.until_date else OPEN_END, until_date)
		periods.setdefault(row.employee, []).append((start, end))
	return periods


def has_assignments(team):
	return bool(frappe.db.exists("Team Assignment", {"team": team}))


def sync_team(team, on_date=None, exclude=None, from_assignment=False):
	"""Rewrite the Team's lead, co-lead and member table from its assignments open on `on_date`.

	Saves the Team only when something changed. A team without any assignment is left alone
	(created outside this flow, e.g. demo data before the patch), unless the call comes from a
	change of one of its assignments (`from_assignment`): then it may just have lost its last one.
	"""
	if not team or not frappe.db.exists("Team", team):
		return
	if not from_assignment and not has_assignments(team):
		return
	on_date = getdate(on_date or today())
	rows = open_assignments(team, on_date, exclude=exclude)

	lead = next((row.employee for row in rows if row.role == LEAD), None)
	co_lead = next((row.employee for row in rows if row.role == CO_LEAD), None)
	# Everyone open today is a row, the lead and co-lead too: they count in the team's capacity.
	members = []
	for row in rows:
		if row.employee in (m["employee"] for m in members):
			continue
		members.append(
			{
				"employee": row.employee,
				"designation": row.designation,
				"weekly_capacity": get_employee_weekly_hours(row.employee, on_date),
			}
		)

	doc = frappe.get_doc("Team", team)
	current = [
		{"employee": m.employee, "designation": m.designation, "weekly_capacity": m.weekly_capacity or 0}
		for m in doc.team_members
	]
	# weekly_capacity is an Int field
	wanted = [{**m, "weekly_capacity": int(round(m["weekly_capacity"] or 0))} for m in members]
	if doc.team_lead == lead and doc.co_team_lead == co_lead and current == wanted:
		return

	doc.team_lead = lead
	doc.co_team_lead = co_lead
	doc.set("team_members", wanted)
	doc.flags.from_team_assignment = True
	doc.save(ignore_permissions=True)


def sync_all_teams():
	"""Daily job: assignments that started or ended overnight reach the Team."""
	for team in frappe.get_all("Team", pluck="name"):
		try:
			sync_team(team)
		except Exception:
			frappe.log_error(title=f"Team Assignment sync failed for {team}")


def assignments_from_team(team):
	"""Open assignments for the current lead, co-lead and members of a Team that has none yet.

	Used by the patch and the demo data. Start date: when the person was added to the member table
	(the row's creation), or their date of joining if later; lead and co-lead without a row: the
	Team's creation, or their date of joining if later. A person in a row and a lead field gets the
	lead role. A person who already has an open assignment in another team (in several teams before
	#1974) gets this one ended yesterday, so one team at a time holds.

	Returns {"created": [names], "ended": [names ended because of another team]}.
	"""
	doc = frappe.get_doc("Team", team)
	people = {}
	for row in doc.team_members:
		if row.employee:
			people.setdefault(row.employee, {"role": MEMBER, "since": getdate(row.creation), "designation": row.designation})
	for employee, role in ((doc.co_team_lead, CO_LEAD), (doc.team_lead, LEAD)):
		if employee:
			person = people.setdefault(employee, {"role": role, "since": getdate(doc.creation), "designation": None})
			person["role"] = role

	yesterday = add_days(getdate(today()), -1)
	result = {"created": [], "ended": []}
	for employee, person in people.items():
		joined = frappe.db.get_value("Employee", employee, "date_of_joining")
		start = max(person["since"], getdate(joined)) if joined else person["since"]
		until = None
		if frappe.db.exists("Team Assignment", {"employee": employee}):
			until = yesterday
			start = min(start, yesterday)
		assignment = frappe.get_doc(
			{
				"doctype": "Team Assignment",
				"employee": employee,
				"team": team,
				"role": person["role"],
				"from_date": start,
				"until_date": until,
				"designation": person["designation"],
			}
		)
		assignment.flags.skip_team_sync = True
		try:
			assignment.insert(ignore_permissions=True)
		except frappe.ValidationError:
			# e.g. the other team's assignment starts before this one would end: skip, HR decides
			frappe.clear_last_message()
			result["ended"].append(f"{employee} in {team}: not created, overlaps another team")
			continue
		result["created"].append(assignment.name)
		if until:
			result["ended"].append(assignment.name)
	return result
