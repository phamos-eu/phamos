# Copyright (c) 2026, phamos.eu and contributors
# For license information, please see license.txt

"""Short-lived cache of a user's SOGo calendar slots (milestone 68, Phase 0).

The Personal Cockpit calendar reads SOGo through `pull_event_slots`, which costs a CalDAV
REPORT round trip. Week navigation hits the same ranges again and again, so the result is
kept for five minutes per mailbox and range. Every push or delete through the Event sync
drops the mailbox's entries, so a change made in ERPNext is visible on the next read.
"""

from __future__ import annotations

import frappe

PREFIX = "phamos_sogo_slots"
TTL_SECONDS = 300


def _key(email: str, start: str, end: str) -> str:
	return f"{PREFIX}:{email}:{start}:{end}"


def get_slots(email: str, start: str, end: str, timeout: int = 8, refresh: bool = False) -> list[dict]:
	"""Slots of `email`'s SOGo calendar between `start` and `end` (ISO strings).

	`pull_event_slots` reads the calendar of the session user, so `email` must be the session
	user's mailbox; it is only the cache key here. `refresh` skips the cached copy.
	"""
	key = _key(email, start, end)
	if not refresh:
		# expires=True: a miss must not be remembered in frappe.local.cache, or the value set
		# right after it would stay invisible for the rest of the request
		cached = frappe.cache.get_value(key, expires=True)
		if cached is not None:
			return cached
	from .sync_event import pull_event_slots

	slots = pull_event_slots(start, end, timeout=timeout)
	frappe.cache.set_value(key, slots, expires_in_sec=TTL_SECONDS)
	return slots


def invalidate(email: str | None) -> None:
	"""Forget every cached range of one mailbox."""
	if email:
		frappe.cache.delete_keys(f"{PREFIX}:{email}:")
