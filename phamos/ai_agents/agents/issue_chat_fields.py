# Copyright (c) 2026, phamos.eu and contributors
# For license information, please see license.txt

"""Issue Assistant chat: which Issue fields a colleague may have it change, and how values are checked (#2239,
decisions 3 and 4 of #2230).

- Any field the asking person may write: Frappe's meta and permission levels decide; no read-only, hidden,
  table or layout fields.
- Values are checked by type: a Link must exist, a Select value must be an option, dates must parse, a Check
  is 0 or 1, numbers must be numbers.
- Closing (status Closed or Resolved) is never done at once: the assistant asks back and closes on a yes.
- Customer, contact, Implementation, project and the person to assign still need the colleague to name the
  value (the customer's own text must not choose them), but a close spelling counts when exactly one record
  is close; several close records become a suggestion instead of a guess.
"""

import difflib
import re

import frappe
from frappe import _
from frappe.model import no_value_fields, table_fields
from frappe.utils import cint, cstr, flt, get_datetime, getdate

CLOSING = ("Closed", "Resolved")
CONFIRM_MINUTES = 30
CLOSE_MATCH = 0.85
CLEAR_LEAD = 0.05
MAX_SUGGESTIONS = 3
TEXT_TYPES = ("Data", "Small Text", "Text", "Long Text", "Text Editor", "Markdown Editor", "HTML Editor")
# fields that decide whose Issue it is → the doctype of the value and its title field
NAMED_FIELDS = {"customer": ("Customer", "customer_name"), "contact": ("Contact", "full_name"),
	"custom_implementation": ("Implementation", None), "project": ("Project", "project_name")}
# a confirmation is the whole message, one of these (AI review on !1407: "das ist falsch" must not close)
YES_PHRASES = {"yes", "y", "ja", "j", "jep", "yep", "ok", "okay", "sure", "klar", "gerne", "ja bitte", "yes please",
	"mach das", "mach", "do it", "go ahead", "close it", "schließen", "schliessen", "ja schließen", "ja, schließen"}
# kept by the system or deciding who sees the Issue: never set from the chat (AI review on !1407)
SYSTEM_FIELDS = {"company", "email_account", "service_level_agreement", "first_responded_on", "response_by",
	"resolution_by", "agreement_status", "sla_resolution_by", "sla_resolution_date", "via_customer_portal", "lead",
	"opening_date", "opening_time", "resolution_date", "resolution_time", "user_resolution_time",
	"avg_response_time", "on_hold_since", "total_hold_time"}
# whose Issue it is in the portal: the colleague must write the address itself
NAMED_TEXT_FIELDS = ("raised_by",)
SHORT_NAME = 4  # names up to this length only count when written exactly ("Tim" ≠ "time")


# --- which fields ---------------------------------------------------------------------------------


def writable_fields(issue, user):
	"""{fieldname: df} of the Issue fields `user` may write."""
	if not frappe.has_permission("Issue", "write", doc=issue, user=user):
		return {}
	meta = frappe.get_meta("Issue")
	levels = set(meta.get_permlevel_access("write", user=user)) | {0}
	return {
		df.fieldname: df for df in meta.fields
		if df.fieldtype not in no_value_fields and df.fieldtype not in table_fields and df.fieldtype != "Dynamic Link"
		and not df.read_only and not df.hidden and not df.read_only_depends_on and (df.permlevel or 0) in levels
		and df.fieldname not in SYSTEM_FIELDS and df.fieldname not in ("naming_series", "amended_from")
	}


def describe(issue, fields):
	"""The fields for the model's prompt: label, type, choices and the current value."""
	out = {}
	for name, df in fields.items():
		entry = {"label": df.label, "type": df.fieldtype, "current": issue.get(name)}
		if df.fieldtype == "Select":
			entry["options"] = [o for o in cstr(df.options).split("\n") if o][:30]
		elif df.fieldtype in ("Link", "Dynamic Link"):
			entry["link_to"] = df.options
		out[name] = entry
	return out


# --- values ---------------------------------------------------------------------------------------


def check_value(df, value, user=None):
	"""(the value to save, None) or (None, the reason it can't be saved)."""
	text = cstr(value).strip()
	if text in ("", "null", "None") and not df.reqd:
		return None, None
	try:
		if df.fieldtype == "Link":
			name = frappe.db.get_value(df.options, text, "name")
			if not name or (user and not frappe.has_permission(df.options, "read", doc=name, user=user)):
				# not readable is answered like not found, so the chat reveals nothing (AI review on !1407)
				return None, _("{0} {1} does not exist").format(_(df.options), text)
			return name, None  # its exact spelling, not the model's casing
		if df.fieldtype == "Select":
			options = [o for o in cstr(df.options).split("\n") if o]
			if text not in options:
				return None, _("{0} must be one of: {1}").format(_(df.label), ", ".join(options[:10]))
			return text, None
		if df.fieldtype == "Date":
			return str(getdate(text)), None
		if df.fieldtype == "Datetime":
			return str(get_datetime(text)), None
		if df.fieldtype == "Time":
			from frappe.utils import get_time

			return str(get_time(text)), None
		if df.fieldtype == "Check":
			if text.lower() not in ("0", "1", "true", "false", "yes", "no"):
				return None, _("{0} must be yes or no").format(_(df.label))
			return 1 if text.lower() in ("1", "true", "yes") else 0, None
		if df.fieldtype == "Int":
			return cint(float(text)), None
		if df.fieldtype in ("Float", "Currency", "Percent", "Duration"):
			import math

			if not math.isfinite(float(text)):
				raise ValueError(text)
			return flt(text), None
		if df.fieldtype in TEXT_TYPES or df.fieldtype in ("Phone", "Data", "Rating", "Color"):
			return text[: (df.length or 140)] if df.fieldtype in ("Data", "Phone") else text, None
	except Exception:
		return None, _("{0} is not a valid {1}").format(text, _(df.fieldtype))
	return None, _("{0} can't be changed here").format(_(df.label))


# --- closing asks back ----------------------------------------------------------------------------


def says_yes(text):
	"""Only a clear yes on its own: the whole message is one of YES_PHRASES."""
	return " ".join(re.findall(r"[\wäöüß]+", cstr(text).lower())) in {
		" ".join(re.findall(r"[\wäöüß]+", p)) for p in YES_PHRASES}


def pending_close(issue_name, asker, channel=None):
	"""The status the assistant asked this person about closing to, within the last minutes and in the same chat
	or thread (an "ok" elsewhere is no answer to it, AI review on !1407)."""
	from frappe.utils import add_to_date, now_datetime

	from phamos.ai_agents.agents.issue_chat_answer import CHAT_TRIGGER

	run = frappe.get_all("AI Agent Run", filters={"trigger": CHAT_TRIGGER, "reference_doctype": "Issue",
		"reference_name": issue_name, "triggered_by": asker, "status": "Completed",
		"finished_at": (">=", add_to_date(now_datetime(), minutes=-CONFIRM_MINUTES))},
		fields=["analysis"], order_by="creation desc", limit=1)
	if not run:
		return None
	chat = (frappe.parse_json(run[0].analysis or "{}") or {}).get("chat") or {}
	pending = chat.get("pending_close")
	if not isinstance(pending, dict) or (channel and pending.get("channel") != channel):
		return None
	return pending.get("status")


# --- naming, tolerant of typos --------------------------------------------------------------------


def _norm(text):
	return " ".join(re.findall(r"[\wäöüß@.\-]+", cstr(text).lower()))


def _score(name, words):
	"""Best similarity of `name` with any run of words of the same length (±1) in the message. Short names only
	count when written exactly; cheap upper bounds skip most comparisons."""
	target = _norm(name)
	if not target:
		return 0
	if len(target) <= SHORT_NAME:
		return 1.0 if target in words or target in " ".join(words).split() else 0
	n = len(target.split())
	best = 0
	for size in {max(1, n - 1), n, n + 1}:
		for i in range(0, max(1, len(words) - size + 1)):
			matcher = difflib.SequenceMatcher(None, target, " ".join(words[i:i + size]))
			if matcher.real_quick_ratio() < CLOSE_MATCH or matcher.quick_ratio() < CLOSE_MATCH:
				continue
			best = max(best, matcher.ratio())
	return best


def _exact(name, text):
	return bool(name) and bool(re.search(r"(?<!\w)" + re.escape(cstr(name).lower()) + r"(?!\w)", text, re.IGNORECASE))


def _names(doctype, title_field, name):
	title = frappe.db.get_value(doctype, name, title_field) if title_field else None
	return [n for n in (name, title) if n]


def resolve_named(field, value, text):
	"""Whether the colleague's message names `value` for `field`:
	{"ok": bool, "note": "you wrote …" or None, "suggestions": [names of close records] }."""
	doctype, title_field = NAMED_FIELDS[field]
	if any(_exact(n, text) for n in _names(doctype, title_field, value)):
		return {"ok": True, "note": None, "suggestions": []}
	words = _norm(text).split()
	score = max((_score(n, words) for n in _names(doctype, title_field, value)), default=0)
	if score < CLOSE_MATCH:
		return {"ok": False, "note": None, "suggestions": []}
	fields = ["name"] + ([title_field] if title_field else [])
	rivals = []
	for row in frappe.get_all(doctype, fields=fields, limit_page_length=0):
		if row.name == value:
			continue
		rival = max(_score(row.name, words), _score(row.get(title_field), words) if title_field else 0)
		if rival >= max(CLOSE_MATCH, score - CLEAR_LEAD):
			rivals.append((rival, row.get(title_field) or row.name))
	if rivals:
		rivals.sort(reverse=True)
		own = (frappe.db.get_value(doctype, value, title_field) if title_field else None) or value
		return {"ok": False, "note": None, "suggestions": [own] + [r[1] for r in rivals[: MAX_SUGGESTIONS - 1]]}
	return {"ok": True, "note": _closest_phrase(_names(doctype, title_field, value), words), "suggestions": []}


def resolve_person(user, full_name, text):
	"""Like resolve_named, for a person: e-mail, full name or first name; rivals among enabled staff users."""
	names = [user, full_name, cstr(full_name).split(" ")[0]]
	if any(_exact(n, text) for n in names):
		return {"ok": True, "note": None, "suggestions": []}
	names = [user, full_name]  # a first name only when written exactly (AI review on !1407)
	words = _norm(text).split()
	score = max((_score(n, words) for n in names if n), default=0)
	if score < CLOSE_MATCH:
		return {"ok": False, "note": None, "suggestions": []}
	rivals = []
	for row in frappe.get_all("User", filters={"enabled": 1, "user_type": "System User", "name": ("!=", user)},
			fields=["name", "full_name"], limit_page_length=0):
		rival = max(_score(n, words) for n in (row.name, row.full_name) if n)
		if rival >= max(CLOSE_MATCH, score - CLEAR_LEAD):
			rivals.append((rival, row.full_name or row.name))
	if rivals:
		rivals.sort(reverse=True)
		return {"ok": False, "note": None, "suggestions": [full_name or user] + [r[1] for r in rivals[: MAX_SUGGESTIONS - 1]]}
	return {"ok": True, "note": _closest_phrase(names, words), "suggestions": []}


def _closest_phrase(names, words):
	"""The words in the message that matched, for "(you wrote …)"."""
	best, phrase = 0, ""
	for name in names:
		target = _norm(name)
		if not target:
			continue
		n = len(target.split())
		for size in {max(1, n - 1), n, n + 1}:
			for i in range(0, max(1, len(words) - size + 1)):
				candidate = " ".join(words[i:i + size])
				ratio = difflib.SequenceMatcher(None, target, candidate).ratio()
				if ratio > best:
					best, phrase = ratio, candidate
	return _("you wrote \"{0}\"").format(phrase) if phrase else None


def asked_for(df, value, text):
	"""Whether the colleague's message asks for this change: it mentions the field (its label or name) or the
	value. Keeps text in the customer's Issue from steering the model to fields nobody asked about (AI review on
	!1407). Clearing a field needs the field mentioned."""
	words = _norm(text).split()
	field_named = any(_exact(n, text) or (len(_norm(n)) > SHORT_NAME and _score(n, words) >= CLOSE_MATCH)
		for n in (_(df.label), df.label, df.fieldname.replace("_", " ")) if n)
	if field_named:
		return True
	if value in (None, ""):
		return False
	shown = cstr(value)
	if df.fieldtype == "Link":
		title_field = frappe.get_meta(df.options).get_title_field()
		title = frappe.db.get_value(df.options, value, title_field) if title_field and title_field != "name" else None
		return any(_exact(n, text) or _score(n, words) >= CLOSE_MATCH for n in (shown, title, _(shown)) if n)
	if df.fieldtype == "Select":
		# "close it" asks for Closed, "auf erledigt" for its translation
		return any(_exact(n, text) or (len(_norm(n)) > SHORT_NAME and _score(n, words) >= CLOSE_MATCH)
			for n in (shown, _(shown)) if n)
	return False
