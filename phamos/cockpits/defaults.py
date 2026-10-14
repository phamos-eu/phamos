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

# Eisenhower matrix (#1555): a dated ToDo is urgent when it is due within this many working
# days from today (overdue included). Each quadrant shows at most MATRIX_LIMIT ToDos.
URGENT_WORKING_DAYS = 2
MATRIX_LIMIT = 15

# Focus mode (#1556). A session holds 1..FOCUS_MAX_TODOS ToDos; its length is a preset, any
# value up to FOCUS_MAX_MINUTES, or 0 for a stopwatch (ended after STOPWATCH_MAX_MINUTES).
# A timed session expires FOCUS_GRACE_MINUTES after its planned end. Leaving is free during the
# first FOCUS_FREE_EXIT_SECONDS; afterwards the button waits BREAK_OUT_BASE_SECONDS, doubling
# with every break-out that day, at most BREAK_OUT_MAX_SECONDS. Friction, never a lock.
FOCUS_MAX_TODOS = 5
FOCUS_PRESETS = (25, 50)
FOCUS_MAX_MINUTES = 180
STOPWATCH_MAX_MINUTES = 240
FOCUS_GRACE_MINUTES = 15
FOCUS_FREE_EXIT_SECONDS = 60
BREAK_OUT_BASE_SECONDS = 10
BREAK_OUT_MAX_SECONDS = 160
