# Copyright (c) 2026, phamos.eu and contributors
# For license information, please see license.txt

"""Phriend reports from a develop or test system become Issues on the main system.

The sending system has a target system in Phriend Settings (URL + API key and secret of a user
with the role Phriend Remote there). Its server forwards each report to `receive_report` on the
target; nothing is created on the sending system. The browser only ever talks to its own site.
"""

from urllib.parse import quote, urlparse

import frappe
import requests
from frappe import _
from frappe.utils import cstr, escape_html, get_url

from phamos.phriend.api import REPORT_FIELDS, _full_name, _settings, make_report
from phamos.phriend.setup import REMOTE_ROLE

RECEIVE_METHOD = "phamos.phriend.remote.receive_report"
PING_METHOD = "phamos.phriend.remote.ping"
TIMEOUT = 60  # a screenshot can be a few MB


def system_name(settings):
	"""How the target's Issues name this system."""
	return cstr(settings.system_name).strip() or frappe.local.site


# --------------------------------------------------------------------------
# Sending side (the develop or test system)
# --------------------------------------------------------------------------


def forward_report(settings, fields):
	"""Send a report to the target system. Returns {"name", "url"} of the Issue made there."""
	user = frappe.session.user
	payload = {
		**{key: fields.get(key) for key in REPORT_FIELDS},
		"reporter_email": frappe.db.get_value("User", user, "email") or user,
		"reporter_name": _full_name(user),
		"source_system": system_name(settings),
		"source_url": get_url().rstrip("/"),
	}
	result = _call(settings, RECEIVE_METHOD, payload)
	name = cstr((result or {}).get("name"))
	if not name:
		frappe.throw(_("The target system sent an unexpected answer"))
	# the link is built here, from the configured address, not taken from the answer
	return {"name": name, "url": f"{settings.target_url}/app/issue/{quote(name, safe='')}"}


@frappe.whitelist()
def test_target_connection():
	frappe.only_for("System Manager")
	settings = _settings()
	result = _call(settings, PING_METHOD, {}) or {}
	if not result.get("enabled"):
		frappe.throw(_("Phriend is switched off on the target system"))
	return {"url": settings.target_url, "system_name": system_name(settings)}


def _call(settings, method, payload):
	url = cstr(settings.target_url).strip().rstrip("/")
	key = cstr(settings.target_api_key).strip()
	secret = settings.get_password("target_api_secret", raise_exception=False)
	if not (url and key and secret):
		frappe.throw(_("Set the target system's URL, API key and API secret in Phriend Settings"))
	try:
		response = requests.post(
			f"{url}/api/method/{method}",
			headers={"Authorization": f"token {key}:{secret}", "Accept": "application/json"},
			json=payload,
			timeout=TIMEOUT,
			# the report and the screenshot go only to the address that was checked (AI review of !1193)
			allow_redirects=False,
		)
	except requests.RequestException as e:
		frappe.log_error(title="Phriend: target system not reachable", message=f"{url}: {e!r}")
		frappe.throw(_("The target system {0} can't be reached").format(escape_html(url)))

	# before `ok`: requests counts a redirect as ok
	if 300 <= response.status_code < 400:
		frappe.throw(
			_("The target system redirects to {0}: set that address as the Target URL in Phriend Settings").format(
				escape_html(cstr(response.headers.get("Location")) or "?")
			)
		)
	if response.ok:
		try:
			return response.json().get("message")
		except ValueError:
			frappe.throw(_("The target system sent an unexpected answer"))

	# a plain ValidationError on purpose: a 403 here would tell the browser the user may not report
	if response.status_code in (401, 403):
		frappe.throw(
			_(
				"The target system refused the API key: check the key and secret in Phriend Settings and "
				"that the user on the target system has the role {0}"
			).format(REMOTE_ROLE)
		)
	frappe.throw(
		_("The target system answered with an error ({0}): {1}").format(
			response.status_code, escape_html(_error_text(response))
		)
	)


def _error_text(response):
	try:
		body = response.json()
	except ValueError:
		return cstr(response.text)[:300]
	messages = []
	try:
		for message in frappe.parse_json(body.get("_server_messages") or "[]"):
			message = frappe.parse_json(message)
			messages.append(cstr(message.get("message") if isinstance(message, dict) else message))
	except Exception:
		pass
	text = " ".join(messages) or cstr(body.get("exception") or "").split("\n")[-1]
	return frappe.utils.strip_html(text)[:300]


# --------------------------------------------------------------------------
# Receiving side (the main system)
# --------------------------------------------------------------------------


@frappe.whitelist(methods=["POST"])
def receive_report(reporter_email=None, reporter_name=None, source_system=None, source_url=None, **fields):
	"""A report from another system (its forward_report): becomes an Issue here, as create_report
	makes one, marked with the system it came from. Only for users with the role Phriend Remote.

	The reporter is the User with that e-mail if there is one; else only name and e-mail are kept.
	Phriend's allowed role is not asked for: the API user stands for the sending system, whose
	own Phriend checked its user before forwarding.
	"""
	_require_remote_role()
	settings = _settings()
	if not settings.enabled:
		frappe.throw(_("Phriend is disabled"))

	source = {"system": cstr(source_system).strip()[:140] or _("another system"), "url": _origin(source_url)}
	if not source["url"]:
		# the page and record links of the Issue point there
		frappe.throw(_("The sending system did not say its address"))
	email = cstr(reporter_email).strip()
	reporter = frappe.db.get_value("User", {"email": email, "enabled": 1}, "name") if email else None
	name = _full_name(reporter) if reporter else (cstr(reporter_name).strip()[:140] or email or source["system"])
	return make_report(
		settings,
		{key: fields.get(key) for key in REPORT_FIELDS},
		reporter=reporter,
		reporter_name=name,
		reporter_email=email,
		source=source,
	)


@frappe.whitelist()
def ping():
	"""For "Test Target Connection" on the sending system."""
	_require_remote_role()
	return {"enabled": _settings().enabled}


def _require_remote_role():
	# not frappe.only_for: that lets everyone through while tests run, so a test could not show this
	if REMOTE_ROLE not in frappe.get_roles():
		frappe.throw(_("Only for the role {0}").format(REMOTE_ROLE), frappe.PermissionError)


def _origin(url):
	"""scheme://host[:port] of the sending system's address, or "" when it isn't one.

	Rebuilt from its parts, not netloc: "https://main.example.com@evil.example" keeps the user
	info in netloc, and the Issue's links would open on evil.example (AI review of !1193).
	"""
	parsed = urlparse(cstr(url).strip())
	host = parsed.hostname
	if parsed.scheme not in ("http", "https") or not host:
		return ""
	try:
		port = f":{parsed.port}" if parsed.port else ""
	except ValueError:  # a port that is not a number or out of range
		return ""
	if ":" in host:  # IPv6
		host = f"[{host}]"
	return f"{parsed.scheme}://{host}{port}"
