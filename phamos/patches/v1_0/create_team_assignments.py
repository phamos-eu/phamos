"""Team Assignments for the current members of every Team (#1974).

One open assignment per member row, lead and co-lead of each Team that has no assignment yet, from
the Team's creation date or the person's date of joining if later (see
`team_assignment.assignments_from_teams`). A person in several teams keeps one; the others are
listed in the migrate output for HR to check. Afterwards each Team's member table is rewritten from
its assignments.
"""

import frappe

from phamos.phamos.doctype.team_assignment.team_assignment import assignments_from_teams, has_assignments, sync_team


def execute():
	teams = [team for team in frappe.get_all("Team", order_by="name asc", pluck="name") if not has_assignments(team)]
	if not teams:
		return
	result = assignments_from_teams(teams)
	for team in teams:
		sync_team(team)
	if result["ended"] or result["skipped"]:
		print("Team Assignment: some people were in several teams. Please check:")
		for name in result["ended"]:
			row = frappe.db.get_value("Team Assignment", name, ["employee", "team", "until_date"], as_dict=True)
			print(f"  {row.employee} in {row.team}: ended {row.until_date} ({name})")
		for entry in result["skipped"]:
			print(f"  {entry}: no assignment created")
