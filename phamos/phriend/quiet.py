# Copyright (c) 2026, phamos.eu and contributors
# For license information, please see license.txt

"""Leave me in peace (#2010): each user can tell Phriend to be quiet for a while, and mute its
red warnings for up to 90 minutes. Stored per user as user defaults (no field on User), so it
holds on Desk, in every cockpit and on other devices.

Times are epoch milliseconds (UTC), as the browser counts them: "for today" ends at the user's
local midnight, which only the browser knows. "forever" means until the user calls Phriend back.
"""

import time

import frappe
from frappe import _
from frappe.utils import cint, cstr

QUIET_DEFAULT = "phriend_quiet_until"
MUTE_DEFAULT = "phriend_warnings_muted_until"
FOREVER = "forever"
MAX_QUIET_MS = 25 * 60 * 60 * 1000  # "for today" from just after midnight, with a margin for clocks
MUTE_MINUTES = (30, 60, 90)  # warnings can be muted for 90 minutes at most (PM, 2026-11-21)


def now_ms():
	return int(time.time() * 1000)


def _read(key, now):
	"""A stored time still in the future, FOREVER, or None (none stored, expired or broken)."""
	value = cstr(frappe.defaults.get_user_default(key))
	if value == FOREVER:
		return FOREVER
	until = cint(value)
	return until if until > now else None


def state(now=None):
	"""{"quiet_until": ms | "forever" | None, "warnings_muted_until": ms | None, "server_now": ms}
	for the boot. server_now lets the browser compare these times on the server's clock, so a
	browser clock that is off doesn't shorten or lengthen them (AI review of !1273)."""
	now = now or now_ms()
	mute = _read(MUTE_DEFAULT, now)
	return {
		"quiet_until": _read(QUIET_DEFAULT, now),
		"warnings_muted_until": mute if mute != FOREVER else None,
		"server_now": now,
	}


def set_quiet(until=None, minutes=None, now=None):
	"""minutes: quiet for that long, counted on the server's clock ("for 1 hour"); or until:
	"forever", a time in ms within the next 25 hours ("for today", the browser's midnight), or
	empty to call Phriend back."""
	now = now or now_ms()
	if cint(minutes):
		until = now + cint(minutes) * 60 * 1000
	value = cstr(until).strip()
	if not value:
		frappe.defaults.clear_user_default(QUIET_DEFAULT)
	elif value == FOREVER:
		frappe.defaults.set_user_default(QUIET_DEFAULT, FOREVER)
	else:
		ms = cint(value)
		if ms <= now:
			frappe.throw(_("That time has already passed. Is your computer's clock right?"))
		if ms > now + MAX_QUIET_MS:
			frappe.throw(_("Phriend can be quiet for today at most, or until you call it back."))
		frappe.defaults.set_user_default(QUIET_DEFAULT, str(ms))
	return state(now)


def set_warning_mute(minutes, now=None):
	"""minutes: 30, 60 or 90; 0 to hear warnings again."""
	now = now or now_ms()
	minutes = cint(minutes)
	if not minutes:
		frappe.defaults.clear_user_default(MUTE_DEFAULT)
	elif minutes in MUTE_MINUTES:
		frappe.defaults.set_user_default(MUTE_DEFAULT, str(now + minutes * 60 * 1000))
	else:
		frappe.throw(_("Warnings can be muted for 30, 60 or 90 minutes."))
	return state(now)
