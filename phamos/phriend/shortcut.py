# Copyright (c) 2026, phamos.eu and contributors
# For license information, please see license.txt

"""Phriend's keyboard shortcut (#1900): a site-wide default in Phriend Settings, which each user
can change or switch off for themselves (stored as a user default, no field on User).

A shortcut is written like "Mod+P" or "Mod+Shift+K": modifiers, then one key. "Mod" is Cmd on a
Mac and Ctrl elsewhere (the browser side, phamos/public/js/phriend/shortcut.js, decides). The
same notation is read on both sides; normalize() keeps one spelling.
"""

import json
import re

import frappe
from frappe import _
from frappe.utils import escape_html

USER_DEFAULT = "phriend_shortcut"
OFF = "Off"
MODIFIERS = ("Mod", "Ctrl", "Alt", "Shift")  # in this order
_KEY = re.compile(r"^([A-Z0-9]|F([1-9]|1[0-2])|Space)$")


def _refused():
	"""The keys a shortcut must not take over: one list for both sides (shortcut_rules.json)."""
	path = frappe.get_app_path("phamos", "public", "js", "phriend", "shortcut_rules.json")
	with open(path) as f:
		return json.load(f)["refused"]


def problem(mods, key):
	"""Why a shortcut can't be used, or None. Same rules as problem() in shortcut.js."""
	if not (mods & {"Mod", "Ctrl"}):
		return _("Use Cmd/Ctrl together with a letter, a digit or F1 to F12.")
	if "Alt" in mods:
		return _("Alt/Option is not possible: it types characters such as @ or € on many keyboards.")
	refused = _refused()["shift" if "Shift" in mods else "plain"]
	if key in refused:
		return _("This combination belongs to the browser or the system (copy, paste, undo, tabs…).")
	return None


def normalize(text):
	"""One spelling for a shortcut ("cmd+shift+k" -> "Mod+Shift+K"); "" for none.

	Raises a ValidationError for anything that isn't Cmd/Ctrl (+ Shift) plus one key, or that
	would take over typing or a browser/system function (see problem()).
	"""
	text = (text or "").strip()
	if not text:
		return ""
	parts = [p.strip() for p in text.replace(" ", "").split("+") if p.strip()]
	aliases = {"cmd": "Mod", "command": "Mod", "meta": "Mod", "mod": "Mod", "ctrl": "Ctrl",
		"control": "Ctrl", "alt": "Alt", "option": "Alt", "opt": "Alt", "shift": "Shift"}
	mods, key = set(), None
	for part in parts:
		alias = aliases.get(part.lower())
		if alias:
			mods.add(alias)
		elif key is None:
			key = part.upper() if len(part) == 1 else part[:1].upper() + part[1:].lower()
		else:
			key = "?"  # two keys
	reason = _("Use Cmd/Ctrl together with a letter, a digit or F1 to F12.")
	if key and _KEY.match(key):
		reason = problem(mods, key)
	if reason:
		frappe.throw(
			_("{0} can't be Phriend's shortcut. {1}").format(escape_html(text), reason),
			title=_("Keyboard shortcut"),
		)
	return "+".join([m for m in MODIFIERS if m in mods] + [key])


def site_shortcut():
	return frappe.get_cached_doc("Phriend Settings").shortcut or ""


def user_shortcut():
	"""The shortcut for the current user: their own choice, else the site's. "" when off."""
	own = frappe.defaults.get_user_default(USER_DEFAULT)
	if own == OFF:
		return ""
	return own or site_shortcut()
