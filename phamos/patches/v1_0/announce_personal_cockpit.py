# Copyright (c) 2026, phamos.eu and contributors
# For license information, please see license.txt

"""Tell colleagues about the Personal Cockpit with a login pop-up (phamos/phamos#1769).

version-15 only: the first production release (15.124.0, #1768). A public Note with
"notify on login" pops up once per user in Desk at their next login (Frappe marks it seen
when closed) and stops after NOTIFY_DAYS. Decisions of 2026-10-31: English, once per
person, 14 days, created by this patch so it appears with the deploy.
"""

import frappe
from frappe.utils import add_days, today

TITLE = "Your own cockpit: Personal Cockpit is live"
NOTIFY_DAYS = 14

CONTENT = """
<p><strong>Apply for leave in under a minute. And all your own work on one page.</strong></p>
<p>From today, <a href="/personal-cockpit">Personal Cockpit</a> replaces "I Own My Work".
Everything in it is about you: your leave, your ToDos, and the Issues and Tasks assigned to you.</p>

<h4>Apply for leave in a few clicks</h4>
<p>Open <strong>My Leave</strong>, click <strong>Apply for leave</strong>, pick the type and the dates,
and name the colleague who covers for you. Done.</p>
<ul>
<li>Your leave approver gets the request straight away.</li>
<li>You see how many days you have left, per leave type.</li>
<li>While a request is open, you can change or withdraw it.</li>
</ul>
<p><strong>Please apply for your leave here from now on.</strong></p>

<h4>Your work on one page</h4>
<ul>
<li><strong>My ToDos:</strong> what is due and what has gone stale, a list, and a matrix of urgent and important.</li>
<li><strong>My Issues and My Tasks:</strong> only what is assigned to you, with overdue, due soon and your booked hours.</li>
<li><strong>Checklists, focus mode and private daily targets.</strong></li>
<li><strong>Timesheet timer:</strong> start, pause and stop your timesheet records from the top bar.</li>
</ul>

<h4>Good to know</h4>
<ul>
<li><strong>Ctrl/⌘ + B</strong> creates something new: a ToDo, Task, Issue, checklist or leave request. <strong>?</strong> shows all shortcuts.</li>
<li>The cockpit follows your language setting and opens where you left off.</li>
<li>Coming later: "My Day" for planning your day, and checking in and out.</li>
</ul>
<p>Questions or ideas? Write to Wolfram.</p>
<p><a href="/personal-cockpit">Open the Personal Cockpit</a></p>
"""


def execute():
	if frappe.db.exists("Note", {"title": TITLE}):
		return
	frappe.get_doc(
		{
			"doctype": "Note",
			"title": TITLE,
			"public": 1,
			"notify_on_login": 1,
			"notify_on_every_login": 0,
			"expire_notification_on": add_days(today(), NOTIFY_DAYS),
			"content": CONTENT,
		}
	).insert(ignore_permissions=True)
