# Copyright (c) 2026, phamos.eu and contributors
# For license information, please see license.txt

"""Phriend: a report from the desk becomes an Issue (+ ToDo); a triaged Issue can become a GitLab issue."""

import base64
import json
from urllib.parse import quote

import frappe
import requests
from frappe import _
from frappe.desk.form.assign_to import add as assign_to
from frappe.utils import cstr, escape_html, get_url
from frappe.utils.password import get_decrypted_password

MAX_SCREENSHOT_BYTES = 15 * 1024 * 1024
REPORT_DOCTYPE = "Issue"
REPORT_TYPES = ("Bug", "Idea", "Question")
PRIORITIES = ("Low", "Medium", "High", "Urgent")
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
	title,
	comment=None,
	report_type="Bug",
	priority="Medium",
	route=None,
	page_url=None,
	ref_doctype=None,
	ref_docname=None,
	context=None,
	screenshot=None,
):
	settings = _check_allowed()

	title = cstr(title).strip()
	if not title:
		frappe.throw(_("Please give the report a title"))
	if report_type not in REPORT_TYPES:
		report_type = "Bug"
	if priority not in PRIORITIES:
		priority = "Medium"
	if ref_doctype and not frappe.db.exists("DocType", ref_doctype):
		ref_doctype = None
	# a form that is not saved yet ("new-sales-order-1") has no document to link; the route keeps the name
	if not ref_doctype or (ref_docname and not frappe.db.exists(ref_doctype, ref_docname)):
		ref_docname = None

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
	issue.insert(ignore_permissions=True)

	if screenshot:
		file_url = _save_screenshot(issue.name, screenshot)
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


def _save_screenshot(docname, data_url):
	if not isinstance(data_url, str) or not data_url.startswith("data:image/"):
		frappe.throw(_("Invalid screenshot"))

	header, _sep, encoded = data_url.partition(",")
	ext = "jpg" if "jpeg" in header else "png"
	content = base64.b64decode(encoded)
	if len(content) > MAX_SCREENSHOT_BYTES:
		frappe.throw(_("Screenshot is too large"))

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
