"""Team Assignments for the current members of every Team (#1974).

One open assignment per member row, lead and co-lead of each Team that has no assignment yet. Start
date: when the person was added to the Team's member table, or their date of joining if later
(Wolfram, 2026-11-19). Teams are handled most recently changed first, so a person in several teams
keeps the assignment of that team open; their other assignments end yesterday and are listed below
for HR to correct. Afterwards each Team's member table is rewritten from its assignments.
"""

import frappe

from phamos.phamos.doctype.team_assignment.team_assignment import assignments_from_team, has_assignments, sync_team


def execute():
	ended = []
	for team in frappe.get_all("Team", order_by="modified desc", pluck="name"):
		if has_assignments(team):
			continue
		result = assignments_from_team(team)
		ended.extend(result["ended"])
		sync_team(team)
	if ended:
		print("Team Assignment: people were in several teams. Ended yesterday, please check:")
		for entry in ended:
			print(f"  {entry}")
