# Copyright (c) 2026, phamos.eu and contributors
# For license information, please see license.txt

"""Phriend: a report from the desk becomes an Issue (+ ToDo); a triaged Issue can become a GitLab issue."""

import base64
import binascii
import json
import re
from urllib.parse import quote, unquote, urlencode, urlparse

import frappe
import requests
from frappe import _
from frappe.desk.form.assign_to import add as assign_to
from frappe.utils import cint, cstr, escape_html, get_url, pretty_date, to_markdown
from frappe.utils.password import get_decrypted_password

from phamos.phriend import events as phriend_events
from phamos.phriend import feedback as phriend_feedback
from phamos.phriend import quiet as phriend_quiet
from phamos.phriend import shortcut as phriend_shortcut
from phamos.phriend import voice as phriend_voice
from phamos.phriend.boot import is_for_user, web_boot
from phamos.phriend.gitlab_issues import link_created

MAX_SCREENSHOT_BYTES = 15 * 1024 * 1024
REPORT_DOCTYPE = "Issue"
REPORT_TYPES = ("Bug", "Improvement", "Question", "Other")  # "Other" is "Something else" in the flow (#1900)
# "Improvement" was "Idea" (#1924); a tab still running the old flow, or its saved draft, sends "Idea"
OLD_REPORT_TYPES = {"Idea": "Improvement"}
PRIORITIES = ("Low", "Medium", "High", "Urgent")
CLOSED_STATUSES = ("Resolved", "Closed")
REPORT_LIST_CAP = 100  # badge and "Already reported here" count up to this
DEFAULT_GITLAB_PROJECT = "phamos/phamos"
TIMEOUT = 30


def _settings():
	return frappe.get_cached_doc("Phriend Settings")


def _check_allowed():
	settings = _settings()
	if not settings.enabled:
		frappe.throw(_("Phriend is disabled"), frappe.PermissionError)
	if settings.allowed_role and settings.allowed_role not in frappe.get_roles():
		frappe.throw(_("You are not allowed to use Phriend"), frappe.PermissionError)
	return settings


# --------------------------------------------------------------------------
# Report -> Issue (+ ToDo)
# --------------------------------------------------------------------------


# What a report is made of: the flow sends these, and a system with a target forwards them.
REPORT_FIELDS = (
	"title",
	"comment",
	"report_type",
	"priority",
	"route",
	"page_url",
	"ref_doctype",
	"ref_docname",
	"context",
	"screenshot",
	"page_title",
)


@frappe.whitelist(methods=["POST"])
def create_report(
	title=None,
	comment=None,
	report_type="Bug",
	priority="Medium",
	route=None,
	page_url=None,
	ref_doctype=None,
	ref_docname=None,
	context=None,
	screenshot=None,
	page_title=None,
):
	"""Every step of the report flow can be skipped, so only the page is required (#1899).

	`page_title` is what the flow showed as "Reported on" (for example "Issue ISS-2026-00012");
	an empty title becomes that.

	On a system with a target system (Phriend Settings), the report becomes an Issue there and
	nothing is created here: returns {"name", "url"} of that Issue (phamos.phriend.remote).
	"""
	settings = _check_allowed()
	fields = {
		"title": title,
		"comment": comment,
		"report_type": report_type,
		"priority": priority,
		"route": route,
		"page_url": page_url,
		"ref_doctype": ref_doctype,
		"ref_docname": ref_docname,
		"context": context,
		"screenshot": screenshot,
		"page_title": page_title,
	}
	if settings.target_url:
		from phamos.phriend.remote import forward_report

		return forward_report(settings, fields)

	reporter = frappe.session.user
	return make_report(
		settings,
		fields,
		reporter=reporter,
		reporter_name=_full_name(reporter),
		reporter_email=frappe.db.get_value("User", reporter, "email") or reporter,
	)


IMPLEMENTATION_COCKPIT_ROUTE = "implementation-cockpit/"


def report_implementation(settings, route, ref_doctype, ref_docname, source=None):
	"""The Implementation a report belongs to, so the Implementation Cockpit can show it (#1671).

	In this order: the implementation of the Implementation Cockpit page it was made on; the
	implementation of the record it was made on; the Implementation of this system (Phriend
	Settings). A report from another system has neither page nor record here, so it gets none
	until that system's Implementation is known (#1937, #1953).
	"""
	if source:
		return None
	route = cstr(route).lstrip("/")
	if route.startswith(IMPLEMENTATION_COCKPIT_ROUTE):
		name = unquote(route[len(IMPLEMENTATION_COCKPIT_ROUTE) :].split("/", 1)[0])
		if name and frappe.db.exists("Implementation", name):
			return name
	if ref_doctype and ref_docname:
		if ref_doctype == "Implementation":
			return ref_docname
		if frappe.get_meta(ref_doctype).has_field("custom_implementation"):
			value = frappe.db.get_value(ref_doctype, ref_docname, "custom_implementation")
			if value:
				return value
	return settings.get("system_implementation") or None


def make_report(settings, fields, reporter, reporter_name, reporter_email, source=None):
	"""The Issue for one report, with its screenshot and ToDo. Returns {"name"}.

	reporter: the User who reported it, or None for a report from another system whose reporter
	has no user here (then only the name and e-mail are kept).
	source: {"system", "url"} for a report from another system (phamos.phriend.remote). Record
	names there say nothing here, so the record is not linked, only named and linked to there.
	"""
	f = {key: fields.get(key) for key in REPORT_FIELDS}
	report_type = OLD_REPORT_TYPES.get(cstr(f["report_type"]), f["report_type"] or "Bug")
	if report_type not in REPORT_TYPES:
		report_type = "Bug"
	priority = f["priority"] if f["priority"] in PRIORITIES else "Medium"
	route, comment = f["route"], f["comment"]
	ref_doctype, ref_docname = f["ref_doctype"], f["ref_docname"]
	if ref_doctype and not frappe.db.exists("DocType", ref_doctype):
		ref_doctype = None
	if not ref_doctype:
		ref_docname = None

	page_url = f["page_url"] or ""
	record_base = ""  # where the record link points: this site, or the system the report came from
	if source:
		page_url = _page_on(source["url"], page_url)
		record_base = source["url"]
	elif ref_docname and not frappe.db.exists(ref_doctype, ref_docname):
		# a form that is not saved yet ("new-sales-order-1") has no document to link; the route keeps the name
		ref_docname = None
	# a record on another system is named and linked to there, never linked here
	linked_docname = None if source else ref_docname

	title = cstr(f["title"]).strip() or _built_title(f["page_title"], route, ref_doctype, ref_docname)

	priority = "High" if priority == "Urgent" else priority  # Issue Priority has no Urgent

	issue = frappe.new_doc(REPORT_DOCTYPE)
	issue.subject = f"[{report_type}] {title}"[:140]
	issue.status = "Open"
	if frappe.db.exists("Issue Priority", priority):
		issue.priority = priority
	if frappe.db.exists("Issue Type", "Internal"):
		issue.issue_type = "Internal"
	issue.raised_by = reporter_email
	if settings.default_project:
		issue.project = settings.default_project
	issue.phriend_reported_by = reporter
	issue.phriend_reported_by_name = reporter_name
	issue.phriend_type = report_type
	issue.phriend_comment = comment or ""
	issue.phriend_route = cstr(route)[:140]
	issue.phriend_page_url = page_url
	issue.phriend_ref_doctype = ref_doctype
	issue.phriend_ref_docname = linked_docname
	issue.custom_implementation = report_implementation(settings, route, ref_doctype, linked_docname, source)
	issue.phriend_context = _pretty_json(f["context"])
	if source:
		issue.phriend_source_system = source["system"]
		issue.phriend_source_url = source["url"]
	issue.description = _description(
		comment, route, page_url, ref_doctype, ref_docname, reporter_name, record_base, source and source["system"]
	)

	# A screenshot that can't be used costs the screenshot, never the report (#1899).
	shot, shot_problem = _decode_screenshot(f["screenshot"]) if f["screenshot"] else (None, None)
	if shot_problem:
		issue.description += f"<p><small>{escape_html(_('The screenshot could not be saved: {0}').format(shot_problem))}</small></p>"
	issue.insert(ignore_permissions=True)
	if not reporter:
		# Reporter Name fetches from Reported By; with no user here, keep the name that was sent
		issue.db_set("phriend_reported_by_name", reporter_name, update_modified=False)

	if shot:
		file_url = _save_screenshot(issue.name, *shot)
		issue.db_set(
			{
				"phriend_screenshot": file_url,
				"description": issue.description
				+ f'<p><img src="{file_url}" alt="Screenshot" style="max-width: 100%"></p>',
			},
			update_modified=False,
		)

	assignee = settings.assign_to or reporter
	if assignee:
		assignment = {
			"assign_to": [assignee],
			"doctype": REPORT_DOCTYPE,
			"name": issue.name,
			"description": _("{0} (reported by {1})").format(issue.subject, reporter_name),
			"priority": priority,
		}
		if source:
			# the API user of the sending system may not read Issues here (role Phriend Remote
			# only); the Issue itself was inserted the same way, above
			from frappe.desk.form.assign_to import _add

			_add(assignment, ignore_permissions=True)
		else:
			assign_to(assignment)

	return {"name": issue.name}


def _page_on(base, page_url):
	"""The reported page on the system it was reported on: that system's address (sent by its
	server) with the path the browser sent. The browser's host is never used (see report._web_url)."""
	from phamos.phriend.report import _web_url

	path = _web_url(page_url)
	return f"{base}{path}" if path else ""


@frappe.whitelist(methods=["POST"])
def set_my_shortcut(shortcut=None):
	"""Change, switch off or reset the current user's Phriend shortcut (#1900).

	shortcut: a combination like "Mod+P", "Off" to switch it off, or empty to use the site's
	again (Phriend Settings). Returns the shortcut now in effect ("" when off).
	"""
	_check_allowed()
	value = cstr(shortcut).strip()
	if not value:
		frappe.defaults.clear_user_default(phriend_shortcut.USER_DEFAULT)
	elif value.lower() == phriend_shortcut.OFF.lower():
		frappe.defaults.set_user_default(phriend_shortcut.USER_DEFAULT, phriend_shortcut.OFF)
	else:
		frappe.defaults.set_user_default(phriend_shortcut.USER_DEFAULT, phriend_shortcut.normalize(value))
	return phriend_shortcut.user_shortcut()


def _check_quiet_allowed():
	settings = _check_allowed()
	if not cint(settings.get("quiet_mode")):
		frappe.throw(_("Leave me in peace is switched off in Phriend Settings"), frappe.PermissionError)


@frappe.whitelist(methods=["POST"])
def set_my_quiet(until=None, minutes=None):
	"""Leave me in peace (#2010) for the current user: minutes (counted on the server), or until
	"forever", a time in epoch ms (at most the rest of today), or empty to call Phriend back.
	Returns the user's quiet state."""
	_check_quiet_allowed()
	state = phriend_quiet.set_quiet(until, minutes)
	phriend_events.send_quiet_state(state)  # the user's other tabs (#2012)
	return state


@frappe.whitelist(methods=["POST"])
def set_my_warning_mute(minutes=0):
	"""Mute Phriend's red warnings for 30, 60 or 90 minutes (#2010); 0 to hear them again."""
	_check_quiet_allowed()
	state = phriend_quiet.set_warning_mute(minutes)
	phriend_events.send_quiet_state(state)  # the user's other tabs (#2012)
	return state


@frappe.whitelist(methods=["POST"])
def claim_my_bubble(day=None):
	"""One voice (#2011): may Phriend open a bubble by itself now? Uses one of the current user's
	bubbles for today (day: the browser's local date). Returns the day's count and "granted"."""
	settings = _check_allowed()
	if not cint(settings.get("one_voice")):
		frappe.throw(_("One voice is switched off in Phriend Settings"), frappe.PermissionError)
	return phriend_voice.claim(settings, day)


def _check_feedback_allowed():
	settings = _check_allowed()
	if not phriend_feedback.is_on(settings):
		frappe.throw(_("Rating questions are switched off in Phriend Settings"), frappe.PermissionError)
	return settings


@frappe.whitelist(methods=["POST"])
def get_my_feedback_requests():
	"""The current user's open rating questions (#2014). Fetched after the page loads, not in the
	boot: Desk caches the boot per user, and a new question would not show until that cache is
	cleared."""
	_check_feedback_allowed()
	return phriend_feedback.open_requests()


@frappe.whitelist(methods=["POST"])
def answer_feedback(name=None, rating=None, comment=None):
	"""Rating a fix (#2014): the current user's answer to one of their questions."""
	_check_feedback_allowed()
	return phriend_feedback.answer(cstr(name), rating, comment)


@frappe.whitelist(methods=["POST"])
def defer_feedback(name=None):
	"""The question was closed without an answer: ask again another day (at most 3 times)."""
	_check_feedback_allowed()
	return phriend_feedback.defer(cstr(name))


@frappe.whitelist(methods=["POST"])
def decline_feedback(name=None):
	"""'No thanks': never ask this question again."""
	_check_feedback_allowed()
	return phriend_feedback.decline(cstr(name))


@frappe.whitelist(methods=["POST"])
def ask_feedback_now(issue=None, round=None):
	"""Debug (phriend.ask_rating): ask the rating question for one report now, whether or not it
	is live. For those who may change Phriend Settings."""
	_check_feedback_allowed()
	frappe.has_permission("Phriend Settings", "write", throw=True)
	round_ = cstr(round) or phriend_feedback.FIRST
	if round_ not in (phriend_feedback.FIRST, phriend_feedback.LATER):
		frappe.throw(_("Round is First impression or Battle tested."))
	return phriend_feedback.ask(cstr(issue), round_, phriend_feedback.live_since(cstr(issue)))


@frappe.whitelist(methods=["POST"])
def send_test_event(kind=None):
	"""Debug (phriend.emit, #2012): a sample event of `kind` to the current user's own Phriend.
	For those who may change Phriend Settings, while events are on."""
	settings = _check_allowed()
	frappe.has_permission("Phriend Settings", "write", throw=True)
	if not cint(settings.get("events")):
		frappe.throw(_("Events are switched off in Phriend Settings"), frappe.PermissionError)
	return phriend_events.test_event(cstr(kind))


def _open_report_filters(route, ref_doctype, ref_docname):
	"""Filters for open Phriend reports about one record, a DocType, or a page; None for none.

	The most specific given wins: a record (ref_doctype + ref_docname), else a DocType, else the
	route. None, quietly (no message, no error), when Phriend is not for this user, the user
	can't read Issues, or can't read the record or DocType asked about: the titles of reports
	about a record say something about it (GDPR review of !1162). The cockpits ask on every
	page change.
	"""
	if not is_for_user() or not frappe.has_permission(REPORT_DOCTYPE, "read"):
		return None
	if _settings().target_url:
		# reports from here are Issues on the target system; the ones here would mislead
		return None
	route, ref_doctype, ref_docname = cstr(route), cstr(ref_doctype), cstr(ref_docname)
	filters = {"phriend_type": ["is", "set"], "status": ["not in", CLOSED_STATUSES]}
	if ref_doctype:
		if not _may_read(ref_doctype, ref_docname):
			return None
		filters["phriend_ref_doctype"] = ref_doctype
		if ref_docname:
			filters["phriend_ref_docname"] = ref_docname
	elif route:
		filters["phriend_route"] = route[:140]
	else:
		return None
	return filters


def _may_read(doctype, name=None):
	try:
		return bool(frappe.has_permission(doctype, "read", doc=name or None))
	except Exception:
		# an unknown DocType or record: nothing to say about it
		frappe.clear_last_message()
		return False


@frappe.whitelist(allow_guest=True, methods=["GET"])
def get_web_boot():
	"""Whether the Phriend ball shows on the website pages, and what it needs (#2104).

	The website has no Desk boot: phriend_web.bundle.js asks here, and only for users whose
	`system_user` cookie says Desk user. None for everyone Phriend is not for, Guests included
	(a stale cookie after logout must not raise an error).
	"""
	return web_boot()


@frappe.whitelist(methods=["GET"])
def get_web_translations():
	"""Phriend's words in the user's language, for the website pages (#2104): the table the
	cockpits boot with. Fetched once per language and phamos version; empty when Phriend is not
	for the user."""
	from phamos.www.spa_boot import spa_translations

	if not web_boot():
		return {}
	return spa_translations(frappe.local.lang)


@frappe.whitelist()
def count_open_reports(route=None, ref_doctype=None, ref_docname=None):
	"""How many open Phriend reports there are about this record or page: the badge on the ball
	(#1900). Only Issues the user may read, up to 100."""
	filters = _open_report_filters(route, ref_doctype, ref_docname)
	if not filters:
		return 0
	# names, not a SQL count: Frappe v16 no longer takes "count(name)" as a field
	return len(frappe.get_list(REPORT_DOCTYPE, filters=filters, pluck="name", limit_page_length=REPORT_LIST_CAP))


@frappe.whitelist()
def get_open_reports(route=None, ref_doctype=None, ref_docname=None):
	"""The open Phriend reports about this record or page, newest first, for the first step of
	the report flow: "Already reported here?" (PM, 2026-11-15, #1900).

	Returns {"count": up to 100, "capped": more than that, "reports": the newest 5}. Only Issues
	the user may read; empty when Phriend is not for this user.
	"""
	filters = _open_report_filters(route, ref_doctype, ref_docname)
	if not filters:
		return {"count": 0, "capped": False, "reports": []}
	rows = frappe.get_list(
		REPORT_DOCTYPE,
		filters=filters,
		fields=["name", "subject", "status", "priority", "phriend_type", "phriend_reported_by_name", "creation"],
		order_by="creation desc",
		limit_page_length=REPORT_LIST_CAP + 1,
	)
	return {
		"count": min(len(rows), REPORT_LIST_CAP),
		"capped": len(rows) > REPORT_LIST_CAP,  # "100+"
		"reports": [
			{
				"name": row.name,
				# the subject without the "[Bug] " the report got from its type
				"title": re.sub(r"^\[[^\]]*\]\s*", "", row.subject or "") or row.name,
				"type": row.phriend_type,
				"status": _(row.status),
				"priority": _(row.priority) if row.priority else "",
				"reported_by": row.phriend_reported_by_name or "",
				"when": pretty_date(row.creation),
			}
			for row in rows[:5]
		],
	}


TESTING_LABEL = "Testing on Production"
HEX_COLOR = re.compile(r"^#[0-9a-fA-F]{3,8}$")


TESTING_CACHE_KEY = "phriend:testing_on_production"
TESTING_CACHE_SECONDS = 300  # the count may be up to 5 minutes old; failures are retried after 1
TESTING_RETRY_SECONDS = 60


@frappe.whitelist()
def get_testing_on_production(route=None, ref_doctype=None, ref_docname=None):
	"""The second (purple) badge on the ball: the open GitLab issues labelled "Testing on
	Production" that are about where Phriend is, and that list in GitLab, which a click opens.

	"About where Phriend is" is GitLab's own search (title and description) for the record's
	DocType, or on a Desk page without one the page's title. Workspaces and cockpit pages without
	a record have nothing to search for: no badge there. The docname is not searched: the badge
	is per DocType.
	Asks GitLab with the token in Phriend Settings, at most every 5 minutes per DocType or page.
	Returns {"count", "url", "about", "color": the label's colour in GitLab, or None};
	count 0 hides the badge.
	"""
	empty = {"count": 0, "url": None, "about": None, "color": None}
	if not _is_tester():  # staff only: portal users never make the server ask GitLab
		return empty
	about = _testing_search_term(route, ref_doctype)
	if not about:
		return empty
	settings = _settings()
	url, token = _gitlab_url_and_token(settings)
	if not (url and token):
		return empty
	key = f"{TESTING_CACHE_KEY}:{about}"
	cached = frappe.cache.get_value(key, expires=True)  # not kept in process memory
	if cached is not None:
		return cached
	result = _testing_on_production_from_gitlab(settings, about)
	empty["about"] = about
	frappe.cache.set_value(
		key, result or empty, expires_in_sec=TESTING_CACHE_SECONDS if result else TESTING_RETRY_SECONDS
	)
	return result or empty


def _testing_search_term(route, ref_doctype):
	"""What GitLab searches for: the DocType of a record, list or report, else the title of the
	Desk page (Developer Action Panel), else None."""
	doctype = cstr(ref_doctype).strip()
	if doctype and frappe.db.exists("DocType", doctype):
		return doctype
	first = cstr(route).strip().strip("/").split("/")[0]
	if first and "/" not in cstr(route).strip().strip("/"):
		title = frappe.db.get_value("Page", first, "title")
		if title:
			return title
	return None


def _gitlab_search(term):
	"""A phrase in quotes, so "Sales Invoice" doesn't also match every invoice and every sale."""
	return f'"{term}"' if " " in term else term


def _testing_list_url(base, project, about):
	return f"{base.rstrip('/')}/{project.strip('/')}/-/issues/?" + urlencode(
		[("state", "opened"), ("label_name[]", TESTING_LABEL), ("search", _gitlab_search(about))]
	)


def _testing_on_production_from_gitlab(settings, about):
	"""{count, url, about, color} from GitLab, or None when GitLab can't be asked (logged, not
	raised: a badge must never break a page)."""
	try:
		base, headers = _gitlab(settings)
		project = settings.gitlab_project or DEFAULT_GITLAB_PROJECT
		api = _project_api(base, project)
		response = requests.get(
			f"{api}/issues",
			headers=headers,
			params={"labels": TESTING_LABEL, "state": "opened", "per_page": 1, "search": _gitlab_search(about)},
			timeout=TIMEOUT,
		)
		if not response.ok:
			frappe.log_error(f"Phriend: Testing on Production count: {response.status_code} {response.text[:300]}", "Phriend")
			return None
		count = cint(response.headers.get("X-Total"))
		if not count and response.json():
			count = 1  # GitLab leaves X-Total out on very large projects; at least the badge shows
		if not count:
			return {"count": 0, "url": None, "about": about, "color": None}  # nothing to colour
		color = None
		labels = requests.get(f"{api}/labels", headers=headers, params={"search": TESTING_LABEL}, timeout=TIMEOUT)
		if labels.ok:
			match = next((l for l in labels.json() if l.get("name") == TESTING_LABEL), None)
			color = match and match.get("color")
		return {
			"count": count,
			"url": _testing_list_url(base, project, about),
			"about": about,
			"color": color if color and HEX_COLOR.match(color) else None,
		}
	except Exception:
		frappe.log_error("Phriend: Testing on Production count failed", "Phriend")
		return None


def _built_title(page_title, route, ref_doctype, ref_docname):
	"""The title of a report whose title step was skipped: where it was reported."""
	if cstr(page_title).strip():
		return cstr(page_title).strip()
	if ref_doctype and ref_docname:
		return f"{_(ref_doctype)} {ref_docname}"
	if ref_doctype:
		return _(ref_doctype)
	return cstr(route).strip() or _("a page")


def _full_name(user):
	# the same value the Reporter Name field fetches, so Issue, ToDo and GitLab agree
	return frappe.db.get_value("User", user, "full_name") or user


def _pretty_json(value):
	if not value:
		return None
	try:
		data = json.loads(value) if isinstance(value, str) else value
		return json.dumps(data, indent=2, ensure_ascii=False, default=str)
	except Exception:
		return cstr(value)


def _description(comment, route, page_url, ref_doctype, ref_docname, reporter_name, record_base="", source_system=None):
	parts = []
	if comment:
		parts.append("<p>" + escape_html(comment).replace("\n", "<br>") + "</p>")

	where = []
	if page_url:
		where.append(f'<a href="{escape_html(page_url)}">{escape_html(route or page_url)}</a>')
	if ref_doctype and ref_docname:
		slug = frappe.scrub(ref_doctype).replace("_", "-")
		where.append(
			f"{escape_html(_(ref_doctype))}: "
			f'<a href="{escape_html(record_base)}/app/{slug}/{quote(ref_docname)}">{escape_html(ref_docname)}</a>'
		)
	elif ref_doctype:
		where.append(escape_html(_(ref_doctype)))
	if where:
		parts.append("<p><b>" + _("Page") + ":</b> " + " · ".join(where) + "</p>")

	if source_system:
		reported = _("Reported via Phriend by {0} on {1}").format(escape_html(reporter_name), escape_html(source_system))
	else:
		reported = _("Reported via Phriend by {0}").format(escape_html(reporter_name))
	parts.append(f"<p><small>{reported}</small></p>")
	return "".join(parts)


# What the browser sends (canvas.toDataURL), and how such a file starts.
SCREENSHOT_TYPES = {
	"data:image/png;base64": ("png", b"\x89PNG\r\n\x1a\n"),
	"data:image/jpeg;base64": ("jpg", b"\xff\xd8\xff"),
}


def _decode_screenshot(data_url):
	"""Check a screenshot data URL. Returns ((ext, content), None) or (None, problem).

	Only PNG and JPEG whose bytes really are PNG or JPEG are kept: the file is stored and shown
	on the Issue. An empty canvas gives "data:," (a page of 0 x 0 pixels), which lands here too.
	"""
	header, _sep, encoded = cstr(data_url).partition(",")
	kind = SCREENSHOT_TYPES.get(header)
	problem = None
	if not kind or not encoded:
		problem = _("not a PNG or JPEG image")
	else:
		try:
			content = base64.b64decode(encoded, validate=True)
		except (binascii.Error, ValueError):
			content = None
		if not content or not content.startswith(kind[1]):
			problem = _("not a PNG or JPEG image")
		elif len(content) > MAX_SCREENSHOT_BYTES:
			problem = _("larger than {0} MB").format(MAX_SCREENSHOT_BYTES // (1024 * 1024))
	if problem:
		frappe.log_error(
			title="Phriend: screenshot dropped",
			message=f"{problem}; starts with {cstr(data_url)[:40]!r}, {len(cstr(data_url))} characters",
		)
		return None, problem
	return (kind[0], content), None


def _save_screenshot(docname, ext, content):
	file_doc = frappe.get_doc(
		{
			"doctype": "File",
			"file_name": f"phriend-{docname}.{ext}",
			"attached_to_doctype": REPORT_DOCTYPE,
			"attached_to_name": docname,
			"attached_to_field": "phriend_screenshot",
			"is_private": 1,
			"content": content,
		}
	)
	file_doc.insert(ignore_permissions=True)
	return file_doc.file_url


# --------------------------------------------------------------------------
# Issue -> GitLab issue
# --------------------------------------------------------------------------


def _gitlab_url_and_token(settings):
	"""Phriend Settings first; empty fields fall back to GitLab Settings (the sync integration)."""
	url = settings.gitlab_url or frappe.db.get_single_value("GitLab Settings", "gitlab_url")
	token = settings.get_password("gitlab_token", raise_exception=False) or get_decrypted_password(
		"GitLab Settings", "GitLab Settings", "access_token", raise_exception=False
	)
	return cstr(url).strip().rstrip("/"), token


def _gitlab(settings=None):
	url, token = _gitlab_url_and_token(settings or _settings())
	if not url:
		frappe.throw(_("Set the GitLab URL in Phriend Settings first"))
	if not token:
		frappe.throw(_("Set a GitLab token in Phriend Settings first"))
	return url, {"PRIVATE-TOKEN": token}


def _project_api(base, project):
	project = cstr(project).strip().strip("/")
	if not project:
		frappe.throw(_("Set the GitLab project in Phriend Settings first"))
	return f"{base}/api/v4/projects/{quote(project, safe='')}"


def _raise_for_gitlab(response, what):
	if response.ok:
		return
	try:
		detail = response.json()
		detail = detail.get("message") or detail.get("error") or detail
	except Exception:
		detail = response.text[:500]
	if cstr(detail) == "insufficient_scope":
		frappe.throw(
			_(
				"GitLab {0} failed: the GitLab token is missing the <b>api</b> scope. "
				"Create a token with the <b>api</b> scope (Reporter role or higher) and add it in Phriend Settings."
			).format(what),
			title=_("GitLab token needs the api scope"),
		)
	frappe.throw(_("GitLab {0} failed ({1}): {2}").format(what, response.status_code, escape_html(cstr(detail))))


@frappe.whitelist()
def get_gitlab_defaults():
	frappe.has_permission(REPORT_DOCTYPE, "write", throw=True)
	settings = _settings()
	url, token = _gitlab_url_and_token(settings)
	return {
		"gitlab_url": url,
		"gitlab_project": settings.gitlab_project or DEFAULT_GITLAB_PROJECT,
		"gitlab_labels": settings.gitlab_labels,
		"has_token": bool(token),
	}


@frappe.whitelist()
def test_gitlab_connection():
	frappe.only_for("System Manager")
	settings = _settings()
	base, headers = _gitlab(settings)
	response = requests.get(
		_project_api(base, settings.gitlab_project or DEFAULT_GITLAB_PROJECT), headers=headers, timeout=TIMEOUT
	)
	_raise_for_gitlab(response, _("connection test"))
	data = response.json()
	return {"name_with_namespace": data.get("name_with_namespace"), "web_url": data.get("web_url")}


@frappe.whitelist(methods=["POST"])
def create_gitlab_issue(issue, labels=None, title=None):
	"""A GitLab issue from an Issue, linked to it as a GitLab Issue record.

	Any Issue, and as often as needed: one Issue can hold several GitLab issues (PM, 2026-11-17).
	`gitlab_issue_url` keeps the first one.
	"""
	doc = frappe.get_doc(REPORT_DOCTYPE, issue)
	doc.check_permission("write")

	settings = _settings()
	base, headers = _gitlab(settings)
	# internal assistant: always the configured project (phamos/phamos by default), never a user's choice
	api = _project_api(base, settings.gitlab_project or DEFAULT_GITLAB_PROJECT)

	screenshot_md = _upload_screenshot(api, headers, doc.phriend_screenshot) if doc.get("phriend_screenshot") else ""

	payload = {
		"title": cstr(title or doc.subject)[:255],
		"description": _issue_markdown(doc, screenshot_md),
		"labels": labels if labels is not None else (settings.gitlab_labels or ""),
	}
	response = requests.post(f"{api}/issues", headers=headers, data=payload, timeout=TIMEOUT)
	_raise_for_gitlab(response, _("issue creation"))
	created = response.json()
	web_url = created.get("web_url")

	if not doc.get("gitlab_issue_url"):
		doc.db_set("gitlab_issue_url", web_url)
	# GitLab has the issue now: a failed link must not fail the request, or the user clicks
	# again and a second GitLab issue is made (AI review of !1192). The URL and comment stay.
	frappe.db.savepoint("phriend_link_gitlab_issue")
	try:
		record = link_created(doc.name, created)
	except Exception:
		frappe.db.rollback(save_point="phriend_link_gitlab_issue")
		frappe.log_error(title="Phriend: linking the GitLab issue failed", reference_doctype=REPORT_DOCTYPE,
			reference_name=doc.name)
		record = None
	reference = created.get("references", {}).get("full") or web_url
	doc.add_comment(
		"Comment",
		_("GitLab issue created: {0}").format(
			f'<a href="{escape_html(web_url)}" target="_blank">{escape_html(reference)}</a>'
		),
	)
	# tell the reporter's Phriend (#2012)
	phriend_events.gitlab_issue_created(doc, web_url, reference)
	# no record: the GitLab Project is not synced to ERPNext yet, or linking failed (both logged)
	return {"web_url": web_url, "iid": created.get("iid"), "reference": reference, "gitlab_issue": record}


def _upload_screenshot(api, headers, file_url):
	file_doc = frappe.get_doc("File", {"file_url": file_url})
	content = file_doc.get_content()
	if isinstance(content, str):
		content = content.encode()
	return _upload_image(api, headers, file_doc.file_name, content)


def _upload_image(api, headers, file_name, content):
	"""Upload an image to the GitLab project; returns the markdown that shows it."""
	mimetype = "image/jpeg" if file_name.endswith(".jpg") else "image/png"
	response = requests.post(
		f"{api}/uploads",
		headers=headers,
		files={"file": (file_name, content, mimetype)},
		timeout=TIMEOUT,
	)
	_raise_for_gitlab(response, _("screenshot upload"))
	return response.json().get("markdown", "")


# --------------------------------------------------------------------------
# Test result -> comment on a GitLab issue
# --------------------------------------------------------------------------
# While testing (for example a new DAP feature), "Test result" in the flow posts the screenshot
# and a note straight onto the GitLab issue being tested, as a comment. No ERPNext Issue: it is
# proof of a test, not a problem report.

TEST_RESULTS = ("Passed", "Failed", "Note")
TEST_HEADINGS = {"Passed": "✅ Test passed", "Failed": "❌ Test failed", "Note": "📝 Test note"}
LAST_TEST_ISSUE = "phriend_last_test_issue"  # user default: the issue of the last test result
_ISSUE_URL_RE = re.compile(r"^(?P<base>https?://[^/\s]+)/(?P<path>[^\s]+?)/-/(?:issues|work_items)/(?P<iid>\d+)/?(?:[?#]\S*)?$")
_SHORT_REF_RE = re.compile(r"^(?:(?P<path>[\w.-]+(?:/[\w.-]+)+))?#?(?P<iid>\d+)$")


# The team's status labels (gitlab-issue-workflow): an issue has exactly one at a time.
STATUS_LABELS = ("Working", "Ready for Dev", "PM Review", "Testing", "Ready for Production", "Testing on Production")
# Old status labels the workflow no longer uses: removed whenever Phriend sets a status
RETIRED_STATUS_LABELS = ("Ready for Staging", "Ready for Release", "Testing on Staging")


def _is_tester():
	"""Everyone who has Phriend in Desk or a cockpit; never a portal (website) user."""
	return is_for_user() and frappe.get_cached_value("User", frappe.session.user, "user_type") == "System User"


def _check_tester():
	settings = _check_allowed()
	if not _is_tester():
		frappe.throw(_("Test results can only be posted from Desk."), frappe.PermissionError)
	return settings


def _parse_gitlab_reference(reference, base, default_project):
	"""(project path, iid) for "#123", "123", "group/project#123", a GitLab Issue record or an issue
	link. Links must point at our GitLab: the token is only ever sent there."""
	ref = cstr(reference).strip()
	if not ref:
		frappe.throw(_("Which GitLab issue did you test? Enter its number or link."))
	if not _SHORT_REF_RE.match(ref) and frappe.db.exists("GitLab Issue", ref):
		ref = frappe.db.get_value("GitLab Issue", ref, "issue_url") or ref
	match = _ISSUE_URL_RE.match(ref)
	if match:
		if urlparse(match.group("base")).netloc.lower() != urlparse(base).netloc.lower():
			frappe.throw(_("Only issues on {0} can get test results.").format(escape_html(base)))
		return match.group("path"), int(match.group("iid"))
	match = _SHORT_REF_RE.match(ref)
	if match:
		return (match.group("path") or cstr(default_project).strip("/")), int(match.group("iid"))
	frappe.throw(
		_("{0} is not a GitLab issue. Use #123, group/project#123 or the issue's link.").format(escape_html(ref))
	)


def _timer_issue():
	"""The GitLab issue of my running (or paused) DAP timer, as {reference, label}, or None."""
	try:
		from phamos.api.personal_timer import _session
		from phamos.gitlab_integration.issue_refs import find_gitlab_issues_in_text

		session = _session()
	except Exception:
		return None  # no Employee, no timer: nothing to suggest
	if not session:
		return None
	name = session.get("gitlab_issue")
	if not name:
		child, parent = find_gitlab_issues_in_text(session.get("goal") or "")
		name = child or parent
	if not name:
		return None
	row = frappe.db.get_value("GitLab Issue", name, ["issue_url", "issue_id", "title"], as_dict=True)
	if not row or not row.issue_url:
		return None
	return {"reference": row.issue_url, "label": f"#{row.issue_id} {row.title or ''}".strip()}


@frappe.whitelist()
def get_test_target():
	"""Whether the user may post test results, and the GitLab issue to suggest: the one on the
	running DAP timer, else the one of their last test result."""
	if not _is_tester():
		return {"allowed": False}
	settings = _settings()
	url, token = _gitlab_url_and_token(settings)
	target = _timer_issue()
	if target:
		target["from"] = "timer"
	else:
		last = frappe.defaults.get_user_default(LAST_TEST_ISSUE)
		if last:
			target = {"reference": last, "label": last, "from": "last"}
	return {
		"allowed": bool(url and token),
		"project": settings.gitlab_project or DEFAULT_GITLAB_PROJECT,
		"target": target,
		"statuses": list(STATUS_LABELS),
	}


@frappe.whitelist(methods=["POST"])
def add_test_evidence(
	gitlab_issue=None,
	result="Note",
	title=None,
	comment=None,
	route=None,
	page_url=None,
	page_title=None,
	context=None,
	screenshot=None,
	status=None,
):
	"""Post a test result (screenshot + note) as a comment on a GitLab issue and, when a status
	is chosen, make it the issue's one status label."""
	settings = _check_tester()
	if result not in TEST_RESULTS:
		result = "Note"
	status = cstr(status).strip() or None
	if status and status not in STATUS_LABELS:
		frappe.throw(_("{0} is not a status label.").format(escape_html(status)))
	base, headers = _gitlab(settings)
	configured = cstr(settings.gitlab_project or DEFAULT_GITLAB_PROJECT).strip("/")
	project, iid = _parse_gitlab_reference(gitlab_issue, base, configured)
	# the shared token may reach more projects than the tester may: only the configured one
	if project.strip("/").lower() != configured.lower():
		frappe.throw(_("Test results can only be posted to issues in {0}.").format(escape_html(configured)))
	api = _project_api(base, project)

	response = requests.get(f"{api}/issues/{iid}", headers=headers, timeout=TIMEOUT)
	if response.status_code == 404:
		frappe.throw(_("GitLab issue {0}#{1} was not found, or the token can't see it.").format(escape_html(project), iid))
	_raise_for_gitlab(response, _("issue lookup"))
	gitlab_issue_data = response.json()

	shot, shot_problem = _decode_screenshot(screenshot) if screenshot else (None, None)
	screenshot_md = ""
	if shot:
		ext, content = shot
		stamp = frappe.utils.now_datetime().strftime("%Y%m%d-%H%M%S")
		screenshot_md = _upload_image(api, headers, f"phriend-test-{iid}-{stamp}.{ext}", content)

	body = _test_markdown(
		result=result,
		title=cstr(title).strip() or cstr(page_title).strip() or cstr(route).strip() or _("a page"),
		comment=cstr(comment).strip(),
		route=route,
		page_url=page_url,
		context=_pretty_json(context),
		screenshot_md=screenshot_md,
		shot_problem=shot_problem,
		status=status,
	)
	response = requests.post(f"{api}/issues/{iid}/notes", headers=headers, data={"body": body}, timeout=TIMEOUT)
	_raise_for_gitlab(response, _("comment"))
	note = response.json()

	status_error = None
	if status:
		status_error = _set_status_label(api, headers, iid, status, gitlab_issue_data.get("labels") or [])

	web_url = gitlab_issue_data.get("web_url") or ""
	if web_url:
		frappe.defaults.set_user_default(LAST_TEST_ISSUE, web_url)
	references = gitlab_issue_data.get("references") or {}
	return {
		"web_url": f"{web_url}#note_{note.get('id')}" if web_url and note.get("id") else web_url,
		"reference": references.get("full") or f"{project}#{iid}",
		"title": gitlab_issue_data.get("title") or "",
		"status": None if status_error else status,
		"status_error": status_error,
	}


def _set_status_label(api, headers, iid, status, current_labels):
	"""Add the new status label and remove every other status label in the same call, so the
	issue never has two. The comment is already posted: a failure here is reported, not raised."""
	remove = [
		label for label in current_labels
		if label != status and (label in STATUS_LABELS or label in RETIRED_STATUS_LABELS)
	]
	data = {"add_labels": status}
	if remove:
		data["remove_labels"] = ",".join(remove)
	try:
		response = requests.put(f"{api}/issues/{iid}", headers=headers, data=data, timeout=TIMEOUT)
	except requests.RequestException as e:
		return cstr(e)
	if response.status_code >= 400:
		frappe.log_error(f"Phriend: setting status {status} on issue {iid}: {response.status_code} {response.text[:500]}", "Phriend")
		return _("GitLab answered {0}").format(response.status_code)
	frappe.cache.delete_keys(TESTING_CACHE_KEY)  # the purple badges count status labels
	return None


def _test_markdown(result, title, comment, route, page_url, context, screenshot_md, shot_problem, status=None):
	lines = [f"### {TEST_HEADINGS[result]}: {' '.join(title.split())}", ""]
	if status:
		lines += [f"**Status → {status}**", ""]
	if comment:
		lines += [comment, ""]
	if screenshot_md:
		lines += [screenshot_md, ""]
	elif shot_problem:
		lines += [f"_The screenshot could not be added: {shot_problem}_", ""]

	lines += [
		f"- Page: {_page_markdown(route, page_url)}",
		f"- Tested by: {_full_name(frappe.session.user)}",
		f"- Site: {get_url()}",
		"",
	]
	if context:
		lines += ["<details><summary>Captured context</summary>", "", "```json", context, "```", "", "</details>", ""]
	lines.append("_Captured with Phriend_")
	return "\n".join(lines)


def _page_markdown(route, page_url):
	"""The page line of a test result. route and page_url come from the browser: only an http(s)
	link is linked, percent-encoded so it can't close the link, and the route loses every character
	that could end the link text or the code span."""
	route = re.sub(r"[`\[\]()<>\s]+", " ", cstr(route)).strip()[:200]
	url = cstr(page_url).strip()
	if urlparse(url).scheme in ("http", "https"):
		url = quote(url, safe=":/?#@!$&'*+,;=%~")
		return f"[{route or url}]({url})"
	return f"`{route}`" if route else "-"


def _issue_markdown(report, screenshot_md):
	if not report.get("phriend_type"):
		return _plain_issue_markdown(report)

	lines = []
	if report.get("phriend_comment"):
		lines += ["## What happened", "", report.phriend_comment, ""]

	lines += ["## Where", ""]
	if report.get("phriend_ref_doctype"):
		where = f"**{report.phriend_ref_doctype}**"
		if report.get("phriend_ref_docname"):
			where += f" `{report.phriend_ref_docname}`"
		lines.append(f"- Document: {where}")
	if report.get("phriend_route"):
		lines.append(f"- Route: `{report.phriend_route}`")
	if report.get("phriend_page_url"):
		lines.append(f"- Page URL: {report.phriend_page_url}")
	lines.append(f"- Type / priority: {report.get('phriend_type') or '-'} / {report.priority or '-'}")
	reporter = report.get("phriend_reported_by_name") or report.get("phriend_reported_by") or report.owner
	lines.append(f"- Reported by: {reporter}")
	lines.append("")

	if screenshot_md:
		lines += ["## Screenshot", "", screenshot_md, ""]

	if report.get("phriend_context"):
		lines += [
			"<details><summary>Captured context</summary>",
			"",
			"```json",
			report.phriend_context,
			"```",
			"",
			"</details>",
			"",
		]

	issue_url = get_url(f"/app/issue/{quote(report.name)}")
	lines.append(f"_Reported via Phriend · ERPNext Issue [{report.name}]({issue_url})_")
	return "\n".join(lines)


def _plain_issue_markdown(issue):
	"""An Issue that did not come from Phriend: its description, then the link back."""
	lines = []
	description = to_markdown(issue.description or "").strip() if issue.get("description") else ""
	if description:
		lines += [description, ""]
	issue_url = get_url(f"/app/issue/{quote(issue.name)}")
	lines.append(f"_From ERPNext Issue [{issue.name}]({issue_url})_")
	return "\n".join(lines)
