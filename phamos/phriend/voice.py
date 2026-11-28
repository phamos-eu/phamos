# Copyright (c) 2026, phamos.eu and contributors
# For license information, please see license.txt

"""One voice (#2011): Phriend opens at most a few bubbles a day by itself, per user (Phriend
Settings → Bubbles per day, default 1). The count is kept per user as a user default, so it holds
across tabs, Desk, the cockpits and devices.

"A day" is the user's own calendar day, which only the browser knows: it sends its local date
("2026-11-21") and the count starts again when that changes.
"""

import re

import frappe
from frappe import _
from frappe.utils import cint, cstr

DAY_DEFAULT = "phriend_voice_day"  # "2026-11-21:1"
_DAY = re.compile(r"^\d{4}-\d{2}-\d{2}$")


def limit(settings):
	return max(0, cint(settings.get("bubbles_per_day")))


def _read():
	value = cstr(frappe.defaults.get_user_default(DAY_DEFAULT))
	day, _sep, count = value.partition(":")
	return (day, cint(count)) if _DAY.match(day) else ("", 0)


def state(settings):
	"""{"day": "2026-11-21" | "", "used": n, "limit": n} for the boot."""
	day, used = _read()
	return {"day": day, "used": used, "limit": limit(settings)}


def claim(settings, day):
	"""Use one of today's bubbles. day: the browser's local date. Returns the state with
	"granted": 1 when a bubble may open now, 0 when today's are used up."""
	day = cstr(day).strip()
	if not _DAY.match(day):
		frappe.throw(_("A day looks like 2026-11-21."))
	# one claim per user at a time, committed before the next may read: two tabs asking at the
	# same moment can't both get the last bubble (AI review of !1276)
	key = f"phriend_voice_claim:{frappe.local.site}:{frappe.session.user}"
	with frappe.cache.lock(key, timeout=10, blocking_timeout=5):
		stored_day, used = _read()
		if stored_day != day:
			used = 0
		granted = used < limit(settings)
		if granted:
			used += 1
			frappe.defaults.set_user_default(DAY_DEFAULT, f"{day}:{used}")
			if not frappe.flags.in_test:  # tests roll back to a savepoint
				frappe.db.commit()
	return {"day": day, "used": used, "limit": limit(settings), "granted": 1 if granted else 0}
