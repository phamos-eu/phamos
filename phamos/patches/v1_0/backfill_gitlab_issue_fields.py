import html
import re

import frappe
from frappe.utils import strip_html


def execute():
	"""
	Backfill gitlab_child_issue, gitlab_parent_issue on Timesheet Record and
	custom_gitlab_child_issue_url, custom_gitlab_parent_issue_url on Timesheet
	for all previously created records.

	Two sources:
	  - Dev Action Panel records: gitlab_issue already set, just need parent resolved.
	  - Project Action Panel records: scan goal + result for GitLab URLs.
	"""

	for col in ("custom_gitlab_child_issue_url", "custom_gitlab_parent_issue_url"):
		if not frappe.db.has_column("Timesheet", col):
			frappe.db.add_column("Timesheet", col, "varchar(140) null")

	records = frappe.db.sql("""
		SELECT name, gitlab_issue, gitlab_parent_issue, goal, result, timesheet, docstatus
		FROM `tabTimesheet Record`
		WHERE timesheet IS NOT NULL AND timesheet != ''
	""", as_dict=True)

	updated_tr = 0
	updated_ts = 0

	for r in records:
		child_issue = r.gitlab_issue or None
		parent_issue = r.gitlab_parent_issue or None

		# --- Project Action Panel path: no gitlab_issue set, scan text ---
		if not child_issue:
			child_issue, parent_issue = _find_gitlab_issues_in_text(r.goal, r.result)

		if not child_issue and not parent_issue:
			continue

		# --- Resolve parent if missing (dev panel records with child but no parent) ---
		if child_issue and not parent_issue:
			parent_issue = frappe.db.get_value("GitLab Issue", child_issue, "parent_issue") or None

		# --- Update Timesheet Record if anything changed ---
		updates = {}
		if child_issue != r.gitlab_issue:
			updates["gitlab_issue"] = child_issue
		if parent_issue != r.gitlab_parent_issue:
			updates["gitlab_parent_issue"] = parent_issue

		if updates:
			frappe.db.set_value("Timesheet Record", r.name, updates, update_modified=False)
			updated_tr += 1

		# --- Resolve URLs and update Timesheet ---
		child_url = frappe.db.get_value("GitLab Issue", child_issue, "issue_url") or "" if child_issue else ""
		parent_url = frappe.db.get_value("GitLab Issue", parent_issue, "issue_url") or "" if parent_issue else ""

		if child_url or parent_url:
			frappe.db.set_value(
				"Timesheet", r.timesheet,
				{
					"custom_gitlab_child_issue_url": child_url,
					"custom_gitlab_parent_issue_url": parent_url,
				},
				update_modified=False,
			)
			updated_ts += 1

	frappe.db.commit()
	frappe.logger().info(
		f"backfill_gitlab_issue_fields: updated {updated_tr} Timesheet Records, "
		f"{updated_ts} Timesheets"
	)


def _find_gitlab_issues_in_text(*text_fields):
	text = " ".join(t for t in text_fields if t)
	text = html.unescape(strip_html(text))

	child_issue = None
	parent_issue = None

	for url in re.findall(r'https?://[^\s"\'<>]+/-/(?:issues|work_items)/\d+', text):
		if "/-/work_items/" in url and child_issue is None:
			child_issue = frappe.db.get_value("GitLab Issue", {"issue_url": url}, "name")
		elif "/-/issues/" in url and parent_issue is None:
			parent_issue = frappe.db.get_value("GitLab Issue", {"issue_url": url}, "name")

	if child_issue:
		resolved_parent = frappe.db.get_value("GitLab Issue", child_issue, "parent_issue") or None
		return child_issue, resolved_parent
	elif parent_issue:
		return parent_issue, parent_issue
	return None, None
