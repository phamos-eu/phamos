# Copyright (c) 2026, phamos.eu and contributors
# For license information, please see license.txt

"""Phriend: a report from the desk becomes an Issue (+ ToDo); a triaged Issue can become a GitLab issue."""

import base64
import binascii
import json
import re
from urllib.parse import quote

import frappe
import requests
from frappe import _
from frappe.desk.form.assign_to import add as assign_to
from frappe.utils import cstr, escape_html, get_url, pretty_date
from frappe.utils.password import get_decrypted_password

from phamos.phriend import shortcut as phriend_shortcut
from phamos.phriend.boot import is_for_user

MAX_SCREENSHOT_BYTES = 15 * 1024 * 1024
REPORT_DOCTYPE = "Issue"
REPORT_TYPES = ("Bug", "Idea", "Question", "Other")  # "Other" is "Something else" in the flow (#1900)
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
	"""
	settings = _check_allowed()

	if report_type not in REPORT_TYPES:
		report_type = "Bug"
	if priority not in PRIORITIES:
		priority = "Medium"
	if ref_doctype and not frappe.db.exists("DocType", ref_doctype):
		ref_doctype = None
	# a form that is not saved yet ("new-sales-order-1") has no document to link; the route keeps the name
	if not ref_doctype or (ref_docname and not frappe.db.exists(ref_doctype, ref_docname)):
		ref_docname = None

	title = cstr(title).strip() or _built_title(page_title, route, ref_doctype, ref_docname)

	reporter = frappe.session.user
	reporter_name = _full_name(reporter)
	priority = "High" if priority == "Urgent" else priority  # Issue Priority has no Urgent

	issue = frappe.new_doc(REPORT_DOCTYPE)
	issue.subject = f"[{report_type}] {title}"[:140]
	issue.status = "Open"
	if frappe.db.exists("Issue Priority", priority):
		issue.priority = priority
	if frappe.db.exists("Issue Type", "Internal"):
		issue.issue_type = "Internal"
	issue.raised_by = frappe.db.get_value("User", reporter, "email") or reporter
	if settings.default_project:
		issue.project = settings.default_project
	issue.phriend_reported_by = reporter
	issue.phriend_reported_by_name = reporter_name
	issue.phriend_type = report_type
	issue.phriend_comment = comment or ""
	issue.phriend_route = cstr(route)[:140]
	issue.phriend_page_url = page_url or ""
	issue.phriend_ref_doctype = ref_doctype
	issue.phriend_ref_docname = ref_docname
	issue.phriend_context = _pretty_json(context)
	issue.description = _description(comment, route, page_url, ref_doctype, ref_docname, reporter_name)

	# A screenshot that can't be used costs the screenshot, never the report (#1899).
	shot, shot_problem = _decode_screenshot(screenshot) if screenshot else (None, None)
	if shot_problem:
		issue.description += f"<p><small>{escape_html(_('The screenshot could not be saved: {0}').format(shot_problem))}</small></p>"
	issue.insert(ignore_permissions=True)

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

	assign_to(
		{
			"assign_to": [settings.assign_to or reporter],
			"doctype": REPORT_DOCTYPE,
			"name": issue.name,
			"description": _("{0} (reported by {1})").format(issue.subject, reporter_name),
			"priority": priority,
		}
	)

	return {"name": issue.name}


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


def _description(comment, route, page_url, ref_doctype, ref_docname, reporter_name):
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
			f'<a href="/app/{slug}/{quote(ref_docname)}">{escape_html(ref_docname)}</a>'
		)
	elif ref_doctype:
		where.append(escape_html(_(ref_doctype)))
	if where:
		parts.append("<p><b>" + _("Page") + ":</b> " + " · ".join(where) + "</p>")

	parts.append(f"<p><small>{_('Reported via Phriend by {0}').format(escape_html(reporter_name))}</small></p>")
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
	doc = frappe.get_doc(REPORT_DOCTYPE, issue)
	doc.check_permission("write")
	if doc.get("gitlab_issue_url"):
		frappe.throw(_("This Issue already has a GitLab issue: {0}").format(doc.gitlab_issue_url))

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

	doc.db_set("gitlab_issue_url", web_url)
	reference = created.get("references", {}).get("full") or web_url
	doc.add_comment(
		"Comment",
		_("GitLab issue created: {0}").format(
			f'<a href="{escape_html(web_url)}" target="_blank">{escape_html(reference)}</a>'
		),
	)
	return {"web_url": web_url, "iid": created.get("iid")}


def _upload_screenshot(api, headers, file_url):
	file_doc = frappe.get_doc("File", {"file_url": file_url})
	content = file_doc.get_content()
	if isinstance(content, str):
		content = content.encode()
	mimetype = "image/jpeg" if file_doc.file_name.endswith(".jpg") else "image/png"
	response = requests.post(
		f"{api}/uploads",
		headers=headers,
		files={"file": (file_doc.file_name, content, mimetype)},
		timeout=TIMEOUT,
	)
	_raise_for_gitlab(response, _("screenshot upload"))
	return response.json().get("markdown", "")


def _issue_markdown(report, screenshot_md):
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
