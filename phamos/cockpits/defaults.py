# Copyright (c) 2026, phamos.eu and contributors
# For license information, please see license.txt

"""Constants of the Personal Cockpit's ToDo rules (#1553).

Site-wide defaults live here until a Cockpit Settings page exists (#1376).
"""

MODULE = "Cockpits"

# A ToDo is "stale" (asks for a decision) when it is open and overdue by more than
# STALE_DAYS, or its due date was moved later STALE_RESCHEDULES times or more.
STALE_DAYS = 14
STALE_RESCHEDULES = 3

# Created and closed within this many minutes: a quick win, not counted toward targets.
MICRO_MINUTES = 15

DASHBOARD_PERIODS = (7, 30, 90)
OLDEST_LIMIT = 5

# Age buckets for open ToDos, in days since creation (upper bound inclusive, None = open end).
AGE_BUCKETS = (
	("0–7 days", 0, 7),
	("8–14 days", 8, 14),
	("15–30 days", 15, 30),
	("31–90 days", 31, 90),
	("90+ days", 91, None),
)

DROP_REASONS = ("Not needed any more", "Done elsewhere", "Out of date", "Other")
