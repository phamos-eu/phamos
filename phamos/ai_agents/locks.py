# Copyright (c) 2026, phamos.eu and contributors
# For license information, please see license.txt

"""Redis locks so one document never has two agent runs at the same time."""

import frappe

RUN_LOCK_TTL = 900


def _key(doctype, name):
	return frappe.cache.make_key(f"ai_agent_run_lock:{doctype}:{name}")


def acquire(doctype, name):
	"""Atomic set-if-absent; True only for the caller that wins."""
	return bool(frappe.cache.set(_key(doctype, name), b"1", nx=True, ex=RUN_LOCK_TTL))


def release(doctype, name):
	frappe.cache.delete(_key(doctype, name))
