# Copyright (c) 2026, phamos.eu and contributors
# For license information, please see license.txt

"""Events (#2012): server code tells one person's Phriend that something happened, live, on Desk
and in every cockpit (realtime event "phriend_event" in the user's own room). Phriend hands it to
its one voice (#2011): a reaction, a note behind the dot, a question, or a red warning.

    from phamos.phriend.events import send
    send(user, "gitlab_issue", text=..., link=...)

Sending never fails the caller: Phriend is a companion, not a reason for an error.
"""

from urllib.parse import quote

import frappe
from frappe import _
from frappe.utils import cint, cstr

EVENT = "phriend_event"

# kind → how it reaches the user. "warn_field": a tick in Phriend Settings → Features that
# makes it a red warning; without the tick it is a note behind the dot. "now": sent at once,
# not after the commit: failures often end in a rollback, and then nothing would arrive.
KINDS = {
	"gitlab_issue": {"level": "note", "gesture": "praise"},  # your report became a GitLab issue
	"idea_vote": {"level": "reaction", "gesture": "heart"},  # someone voted for your idea
	"ai_run_failed": {"level": "note", "gesture": "alert", "warn_field": "warn_ai_run_failed", "now": True},
	"email_failed": {"level": "note", "gesture": "alert", "warn_field": "warn_email_failed", "now": True},
	"gitlab_sync_failed": {"level": "note", "gesture": "alert", "warn_field": "warn_gitlab_sync_failed", "now": True},
	# a customer proposed, agreed, rejected, confirmed or disputed a plan change (#2219)
	"plan_change": {"level": "note", "gesture": "alert"},
}


def _settings():
	return frappe.get_cached_doc("Phriend Settings")


def _for_user(settings, user):
	"""Phriend is on, events are on, and the user is a real, enabled user Phriend is for."""
	if not settings.enabled or not cint(settings.get("events")):
		return False
	if not user or user == "Guest" or not frappe.db.get_value("User", user, "enabled"):
		return False
	return not settings.allowed_role or settings.allowed_role in frappe.get_roles(user)


def safe_link(link):
	"""A path on this site ("/app/…", not "//host" or "/\\host", which browsers open elsewhere)
	or an https URL (AI review of !1279)."""
	return (link.startswith("/") and not link.startswith(("//", "/\\"))) or link.startswith("https://")


def level_of(settings, kind):
	spec = KINDS[kind]
	field = spec.get("warn_field")
	return "warning" if field and cint(settings.get(field)) else spec["level"]


def send(user, kind, text="", link=None):
	"""Tell `user`'s Phriend about `kind` (a key of KINDS). text: plain text, shown escaped;
	link: a path on this site ("/app/issue/ISS-1") or an https URL. Returns True when sent."""
	try:
		settings = _settings()
		if kind not in KINDS or not _for_user(settings, user):
			return False
		link = cstr(link)
		if link and not safe_link(link):
			link = ""
		payload = {
			"kind": kind,
			"level": level_of(settings, kind),
			"gesture": KINDS[kind]["gesture"],
			"text": cstr(text)[:300],
			"link": link,
		}
		frappe.publish_realtime(EVENT, payload, user=user, after_commit=not KINDS[kind].get("now"))
		return True
	except Exception:
		frappe.log_error(title=f"Phriend: event {kind} for {user} not sent")
		return False


def warning_receivers(settings=None):
	"""The users of the role in Phriend Settings → "Warnings Go To" (default System Manager)."""
	settings = settings or _settings()
	role = settings.get("warning_role") or "System Manager"
	users = frappe.get_all("Has Role", filters={"role": role, "parenttype": "User"}, pluck="parent")
	return sorted({u for u in users if u not in ("Guest",)})


def send_to_warning_role(kind, text="", link=None):
	"""A system-wide event (a failed GitLab sync): to everyone in the warning role."""
	try:
		settings = _settings()
		if not cint(settings.get("events")):
			return 0
		return sum(1 for user in warning_receivers(settings) if send(user, kind, text, link))
	except Exception:
		frappe.log_error(title=f"Phriend: event {kind} for the warning role not sent")
		return 0


def send_quiet_state(state):
	"""Leave me in peace (#2010) changed in one tab: tell the user's other tabs at once."""
	frappe.publish_realtime(EVENT, {"kind": "quiet", "state": state}, user=frappe.session.user, after_commit=True)


# ---- the first senders (#2012)


def gitlab_issue_created(issue_doc, web_url, reference):
	reporter = issue_doc.get("phriend_reported_by")
	if reporter:
		send(reporter, "gitlab_issue", _("Your report is now a GitLab issue: {0}").format(reference), web_url)


def idea_voted(idea_owner, idea_title):
	send(idea_owner, "idea_vote", _("Someone voted for your idea: {0}").format(idea_title))


def ai_run_failed(run):
	send(
		run.get("triggered_by"),
		"ai_run_failed",
		_("The AI agent couldn't finish on {0} {1}.").format(_(run.reference_doctype), run.reference_name),
		f"/app/{frappe.scrub(run.reference_doctype).replace('_', '-')}/{quote(cstr(run.reference_name), safe='')}",
	)


def email_failed(user, message):
	send(user, "email_failed", message, "/app/error-log")


def gitlab_sync_failed():
	send_to_warning_role("gitlab_sync_failed", _("The GitLab sync failed. See the Error Log."), "/app/error-log")


def plan_change(users, text, link):
	"""A customer's decision on a plan change, for the implementation's internal PMs (#2219)."""
	for user in users:
		send(user, "plan_change", text, link)


def test_event(kind):
	"""Debug (phriend.emit): a sample of `kind` to the current user."""
	samples = {
		"gitlab_issue": (_("Your report is now a GitLab issue: phamos/phamos#1234"), "https://git.phamos.eu/phamos/phamos"),
		"idea_vote": (_("Someone voted for your idea: A test idea"), None),
		"ai_run_failed": (_("The AI agent couldn't finish on {0} {1}.").format(_("Issue"), "ISS-TEST"), "/app/issue"),
		"email_failed": (_("Some e-mails from {0} could not be read. See the Error Log.").format("Receipts"), "/app/error-log"),
		"gitlab_sync_failed": (_("The GitLab sync failed. See the Error Log."), "/app/error-log"),
		"plan_change": (_("{0} proposes a change to {1}.").format("IC Customer", "Quotations"), "/implementation-cockpit"),
	}
	if kind not in samples:
		frappe.throw(_("Unknown Phriend event: {0}").format(kind))
	text, link = samples[kind]
	return send(frappe.session.user, kind, text, link)
