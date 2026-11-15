# Copyright (c) 2026, phamos.eu and contributors
# For license information, please see license.txt

"""Phriend's keyboard shortcut (#1900): a site-wide default in Phriend Settings, which each user
can change or switch off for themselves (stored as a user default, no field on User).

A shortcut is written like "Mod+P" or "Alt+Shift+P": modifiers, then one key. "Mod" is Cmd on a
Mac and Ctrl elsewhere (the browser side, phamos/public/js/phriend/shortcut.js, decides). The
same notation is read on both sides; normalize() keeps one spelling.
"""

import re

import frappe
from frappe import _

USER_DEFAULT = "phriend_shortcut"
OFF = "Off"
MODIFIERS = ("Mod", "Ctrl", "Alt", "Shift")  # in this order
_KEY = re.compile(r"^([A-Z0-9]|F([1-9]|1[0-2])|Space)$")


def normalize(text):
	"""One spelling for a shortcut ("cmd+shift+p" -> "Mod+Shift+P"); "" for none.

	Raises a ValidationError for anything that isn't modifiers plus one key, or that has no
	Mod, Ctrl or Alt: a plain or Shift+ letter would fire while typing.
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
	if not key or not _KEY.match(key) or not (mods & {"Mod", "Ctrl", "Alt"} or key.startswith("F")):
		frappe.throw(
			_("{0} is not a shortcut Phriend can use. Use Cmd/Ctrl or Alt with a letter, a digit or F1 to F12, e.g. Mod+P.").format(text),
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
