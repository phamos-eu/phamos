# Copyright (c) 2026, phamos.eu and contributors
# For license information, please see license.txt

"""Rating a fix (#2014): when a Phriend report has gone live on production, Phriend asks the
person who reported it how it turned out - right after it went live ("Did it fix it?") and again
when it has been in daily use for a while ("Still good?", Phriend Settings → Battle-tested after,
default 6 weeks).

- Bugs are rated 👍 / 👎, improvements ★ 1-5; questions and "something else" are not asked
  (PM, 2026-11-21).
- "Live" means every GitLab issue behind the report carries a production date (the labels
  "Merged into Production" or "Testing on Production", stamped by the GitLab webhook).
- One Phriend Feedback record per question. Closing the bubble puts it off to another day, at most
  3 times; "No thanks" declines it (PM, 2026-11-21).
- Named or anonymous by Phriend Settings → Anonymous Feedback. The person is stored either way,
  only so nobody is asked twice; with anonymous feedback the name is never shown.
"""

import frappe
from frappe import _
from frappe.utils import add_days, cint, cstr, get_datetime, getdate, now_datetime, today

DOCTYPE = "Phriend Feedback"
FIRST = "First impression"
LATER = "Battle tested"
KIND_FOR = {"Bug": "Thumbs", "Improvement": "Stars"}
ASK_WINDOW_DAYS = 14  # a round is asked within two weeks of becoming due, never about old go-lives
MAX_DEFERRALS = 3
EVENT = "phriend_event"


def _settings():
	return frappe.get_cached_doc("Phriend Settings")


def is_on(settings=None):
	settings = settings or _settings()
	return bool(settings.enabled and cint(settings.get("rate_fixes")))


def battle_tested_days(settings=None):
	settings = settings or _settings()
	return 7 * (cint(settings.get("battle_tested_weeks")) or 6)


def live_since(issue):
	"""When the report went live: the latest production date of its GitLab issues, or None while
	one of them isn't on production yet (or none is linked)."""
	rows = frappe.get_all(
		"GitLab Issue",
		filters={"issue": issue},
		fields=["merged_to_production_at", "testing_on_production_at"],
	)
	if not rows:
		return None
	dates = []
	for row in rows:
		live = row.merged_to_production_at or row.testing_on_production_at
		if not live:
			return None
		dates.append(get_datetime(live))
	return max(dates)


def due_round(live, now, settings=None):
	"""Which round is due for a report live since `live`: FIRST, LATER or None."""
	age = (get_datetime(now) - get_datetime(live)).days
	if 0 <= age < ASK_WINDOW_DAYS:
		return FIRST
	later = battle_tested_days(settings)
	if later <= age < later + ASK_WINDOW_DAYS:
		return LATER
	return None


def _reporter_may_get_it(settings, user):
	if not user or user == "Guest" or not frappe.db.get_value("User", user, "enabled"):
		return False
	return not settings.allowed_role or settings.allowed_role in frappe.get_roles(user)


def ask(issue, round_, live=None, settings=None):
	"""Create the question for the report's reporter (once per report, round and person) and tell
	their Phriend at once if it is open. Returns the Phriend Feedback name, or None."""
	settings = settings or _settings()
	report = frappe.db.get_value(
		"Issue", issue, ["name", "subject", "phriend_type", "phriend_reported_by"], as_dict=True
	)
	if not report or report.phriend_type not in KIND_FOR:
		return None
	user = report.phriend_reported_by
	if not _reporter_may_get_it(settings, user):
		return None
	if frappe.db.exists(DOCTYPE, {"subject_doctype": "Issue", "subject_name": issue, "round": round_, "user": user}):
		return None
	doc = frappe.get_doc(
		{
			"doctype": DOCTYPE,
			"subject_doctype": "Issue",
			"subject_name": issue,
			"subject_title": cstr(report.subject)[:140],
			"round": round_,
			"user": user,
			"kind": KIND_FOR[report.phriend_type],
			"status": "Open",
			"live_since": live,
			"asked_at": now_datetime(),
		}
	).insert(ignore_permissions=True)
	frappe.publish_realtime(EVENT, {"kind": "rate_fix", "feedback": request_payload(doc)}, user=user, after_commit=True)
	return doc.name


def create_due_requests(now=None):
	"""Daily (hooks.scheduler_events): the questions due today, for reports that went live."""
	settings = _settings()
	if not is_on(settings):
		return []
	now = now or now_datetime()
	since = add_days(now, -(battle_tested_days(settings) + ASK_WINDOW_DAYS + 1))
	issues = frappe.db.sql(
		"""select distinct gi.issue from `tabGitLab Issue` gi
		where gi.issue is not null and gi.issue != ''
		and coalesce(gi.merged_to_production_at, gi.testing_on_production_at) >= %s""",
		since,
	)
	created = []
	for (issue,) in issues:
		live = live_since(issue)
		round_ = live and due_round(live, now, settings)
		if round_:
			name = ask(issue, round_, live, settings)
			if name:
				created.append(name)
	return created


def request_payload(doc):
	return {
		"name": doc.name,
		"kind": doc.kind,
		"round": doc.round,
		"title": doc.subject_title,
		"subject": doc.subject_name,
	}


def open_requests(user=None):
	"""The current user's open questions for the boot: at most 3, not put off today."""
	user = user or frappe.session.user
	rows = frappe.get_all(
		DOCTYPE,
		filters={"user": user, "status": "Open", "times_deferred": ["<", MAX_DEFERRALS]},
		fields=["name", "kind", "round", "subject_title", "subject_name", "modified", "times_deferred"],
		order_by="asked_at asc",
		limit=10,
	)
	day = getdate(today())
	waiting = [r for r in rows if not (r.times_deferred and getdate(r.modified) == day)]
	return [request_payload(frappe._dict(r)) for r in waiting[:3]]


def _own_open(name):
	doc = frappe.get_doc(DOCTYPE, name)
	if doc.user != frappe.session.user:
		frappe.throw(_("This question was not for you."), frappe.PermissionError)
	if doc.status != "Open":
		frappe.throw(_("This question is already answered."))
	return doc


def answer(name, rating, comment=None):
	settings = _settings()
	doc = _own_open(name)
	rating = cint(rating)
	if doc.kind == "Thumbs" and rating not in (1, -1):
		frappe.throw(_("Please choose thumbs up or down."))
	if doc.kind == "Stars" and not 1 <= rating <= 5:
		frappe.throw(_("Please choose 1 to 5 stars."))
	doc.update(
		{
			"status": "Answered",
			"rating": rating,
			"comment": cstr(comment).strip()[:2000],
			"answered_at": now_datetime(),
			"anonymous": 1 if cint(settings.get("anonymous_feedback")) else 0,
		}
	)
	doc.save(ignore_permissions=True)
	return {"name": doc.name, "status": doc.status}


def defer(name):
	"""Closed without an answer: another day, at most MAX_DEFERRALS times, then it rests."""
	doc = _own_open(name)
	doc.times_deferred = cint(doc.times_deferred) + 1
	if doc.times_deferred >= MAX_DEFERRALS:
		doc.status = "Declined"
	doc.save(ignore_permissions=True)
	return {"name": doc.name, "status": doc.status}


def decline(name):
	doc = _own_open(name)
	doc.status = "Declined"
	doc.save(ignore_permissions=True)
	return {"name": doc.name, "status": doc.status}
