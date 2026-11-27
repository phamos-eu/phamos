# Copyright (c) 2026, phamos.eu and contributors
# For license information, please see license.txt

"""Backend of the Implementation Cockpit (phamos/phamos#1670, scaffold #1671).

The cockpit serves two kinds of users:

- customer users (website users): they see the Implementations where one of their Contacts is
  a stakeholder of organisation "Customer" and `show_on_customer_portal` is set;
- internal users (System Users): they see the Implementations they may read in Desk.

Every endpoint resolves that scope first and returns allow-listed fields only. Internal fields
(`forecast`, `notes`, the internal statuses) never leave the server, not even for internal
users, so they see what the customer sees.
"""

import frappe
from frappe import _
from frappe.query_builder import Order
from frappe.query_builder.functions import Count, Sum
from frappe.utils import add_days, add_months, cint, flt, getdate, now_datetime, today
from frappe.utils.html_utils import sanitize_html

from phamos.phamos.doctype.implementation_chapter.critical_path import critical_path, dependency_conflict
from phamos.setup.implementation_cockpit import IMPLEMENTATION_ROLE

# Fields of Implementation the cockpit may send. Anything else stays on the server.
OVERVIEW_FIELDS = (
	"name",
	"customer",
	"status",
	"maturity_level",
	"trend",
	"status_statement",
	"start_date",
	"review_cadence",
	"next_review_due",
	"account_manager",
)

# Customer-facing wording of Implementation.status; "Escalated" is internal (#1675).
STATUS_LABELS = {
	"Open": "Active",
	"Reactivated": "Active",
	"Escalated": "Active",
	"Hold": "Paused",
	"Completed": "Completed",
	"Cancelled": "Cancelled",
}


def check_app_permission():
	"""Show the cockpit on the Apps screen for users who can see at least one Implementation."""
	if frappe.session.user == "Guest":
		return False
	return bool(_allowed_implementations())


def is_internal_user(user=None):
	return frappe.get_cached_value("User", user or frappe.session.user, "user_type") == "System User"


def has_internal_access(user=None):
	"""phamos staff get in with the cockpit role or as System Manager (#1671, pattern of #1946).

	All internal users with access see everything for now; finer internal roles may follow
	(GDPR), so the check stays in this one place.
	"""
	roles = frappe.get_roles(user or frappe.session.user)
	return IMPLEMENTATION_ROLE in roles or "System Manager" in roles


def _allowed_implementations():
	"""Names of the Implementations the session user may open in the cockpit."""
	user = frappe.session.user
	if user == "Guest":
		return []
	if is_internal_user(user):
		if not has_internal_access(user):
			return []
		# Respects User Permissions like Desk does.
		return frappe.get_list("Implementation", pluck="name", order_by="name asc")
	return _customer_implementations(user)


def _customer_implementations(user):
	"""Implementations where a Contact of `user` is a Customer stakeholder."""
	contacts = frappe.get_all("Contact", filters={"user": user}, pluck="name")
	email = frappe.db.get_value("User", user, "email")
	stakeholder = frappe.qb.DocType("Implementation Stakeholder")
	conditions = stakeholder.email == email if email else None
	if contacts:
		by_contact = stakeholder.contact.isin(contacts)
		conditions = by_contact if conditions is None else (conditions | by_contact)
	if conditions is None:
		return []
	parents = (
		frappe.qb.from_(stakeholder)
		.select(stakeholder.parent)
		.distinct()
		.where(stakeholder.parenttype == "Implementation")
		.where(stakeholder.stakeholder_organisation == "Customer")
		.where(conditions)
		.run(pluck=True)
	)
	if not parents:
		return []
	return frappe.get_all(
		"Implementation",
		filters={"name": ["in", parents], "show_on_customer_portal": 1},
		pluck="name",
		order_by="name asc",
	)


def _require_implementation(implementation):
	if not implementation or implementation not in _allowed_implementations():
		frappe.throw(_("You do not have access to this implementation."), frappe.PermissionError)


@frappe.whitelist()
def get_scope():
	"""Customers and their Implementations the session user may choose from.

	The picker (#1672) sets a level automatically when it has one option and shows it read-only
	when the user has no choice there.
	"""
	names = _allowed_implementations()
	rows = (
		frappe.get_all(
			"Implementation",
			filters={"name": ["in", names]},
			fields=["name", "customer", "maturity_level", "status"],
			order_by="name asc",
		)
		if names
		else []
	)
	customers = {}
	for row in rows:
		key = row.customer or ""
		if key not in customers:
			info = (
				frappe.db.get_value("Customer", key, ["customer_name", "image"], as_dict=True)
				if key
				else None
			) or {}
			customers[key] = {
				"name": key,
				"customer_name": info.get("customer_name") or key or _("No customer"),
				"image": info.get("image"),
				"implementations": [],
			}
		customers[key]["implementations"].append(
			{
				"name": row.name,
				"phase": _phase_label(row.maturity_level),
				"status": STATUS_LABELS.get(row.status, row.status),
			}
		)
	return {
		"is_internal": is_internal_user(),
		"customers": sorted(customers.values(), key=lambda c: c["customer_name"].lower()),
	}


@frappe.whitelist()
def get_overview(implementation):
	"""Allow-listed basics of one Implementation for the Overview page."""
	_require_implementation(implementation)
	doc = frappe.db.get_value("Implementation", implementation, OVERVIEW_FIELDS, as_dict=True)
	# Until implementation_manager exists (#1674) the account manager is the contact.
	manager = _contact_person(doc.account_manager)
	return {
		"name": doc.name,
		"customer": doc.customer,
		"customer_name": frappe.db.get_value("Customer", doc.customer, "customer_name")
		if doc.customer
		else None,
		"status": STATUS_LABELS.get(doc.status, doc.status),
		"phase": _phase_label(doc.maturity_level),
		"phase_number": _phase_number(doc.maturity_level),
		"trend": doc.trend,
		"status_statement": doc.status_statement,
		"start_date": doc.start_date,
		"review_cadence": doc.review_cadence,
		"next_review_due": doc.next_review_due,
		"manager": manager,
	}


def _contact_person(user):
	"""Name, image and company phone/email of a phamos user, from the linked Employee."""
	if not user:
		return None
	info = frappe.db.get_value("User", user, ["full_name", "user_image"], as_dict=True) or {}
	employee = (
		frappe.db.get_value(
			"Employee",
			{"user_id": user, "status": "Active"},
			["company_email", "cell_number"],
			as_dict=True,
		)
		or {}
	)
	return {
		"full_name": info.get("full_name") or user,
		"image": info.get("user_image"),
		"email": employee.get("company_email") or user,
		"phone": employee.get("cell_number"),
	}


def _phase_number(maturity_level):
	"""Maturity levels are stored as "4 - Go Live Phase. ..."; return 4."""
	head = (maturity_level or "").split(" ", 1)[0]
	return int(head) if head.isdigit() else None


def _phase_label(maturity_level):
	"""Short phase name, e.g. "Go Live" from "4 - Go Live Phase. Go Live, first modules ..."."""
	if not maturity_level or " - " not in maturity_level:
		return None
	label = maturity_level.split(" - ", 1)[1].split(".", 1)[0]
	return label.removesuffix(" Phase").strip()


# Timesheets (#1685): what the /timesheet portal shows, scoped to one Implementation.

TIMESHEET_SORT_FIELDS = {
	"name": "name",
	"start_date": "start_date",
	"employee_name": "employee_name",
	"billing_status": "custom_billing_status",
	"total_hours": "total_hours",
	"billable_hours": "total_billable_hours",
	"rating": "custom_rating",
}
MAX_PAGE_LENGTH = 500
MAX_EXPORT_ROWS = 10000
# Bars in the timesheet chart: five years of weeks, or about 20 years of months.
MAX_PERIODS = 260


def _implementation_projects(implementation):
	"""Projects of the Implementation, the same way Monthly Implementation Summary finds them."""
	return frappe.get_all("Project", filters={"custom_implementation": implementation}, pluck="name")


def _timesheet_query(implementation, from_date=None, to_date=None, project=None):
	"""Base query on Timesheet for one Implementation, or None when it has no projects.

	Timesheet.custom_implementation is copied in on save and goes stale, so the scope comes from
	the projects; the customer is a second guard.
	"""
	_require_implementation(implementation)
	projects = _implementation_projects(implementation)
	if project:
		projects = [p for p in projects if p == project]
	if not projects:
		return None
	customer = frappe.db.get_value("Implementation", implementation, "customer")
	ts = frappe.qb.DocType("Timesheet")
	query = (
		frappe.qb.from_(ts)
		.where(ts.docstatus.isin([0, 1]))
		.where(ts.parent_project.isin(projects))
		.where(ts.customer == customer)
	)
	if from_date:
		query = query.where(ts.start_date >= getdate(from_date))
	if to_date:
		query = query.where(ts.start_date <= getdate(to_date))
	return query, ts


def _timesheet_rows(query, ts, sort_by=None, sort_order=None, start=0, page_length=20):
	field = TIMESHEET_SORT_FIELDS.get(sort_by, "start_date")
	order = Order.asc if sort_order == "asc" else Order.desc
	rows = (
		query.select(
			ts.name,
			ts.start_date,
			ts.employee_name,
			ts.custom_billing_status,
			ts.total_hours,
			ts.total_billable_hours,
			ts.project_name,
			ts.parent_project,
			ts.custom_rating,
			ts.customer_comment,
		)
		.orderby(ts[field], order=order)
		.orderby(ts.name, order=order)
		.limit(page_length)
		.offset(start)
		.run(as_dict=True)
	)
	_add_first_time_log(rows)
	return rows


def _add_first_time_log(rows):
	"""Activity type and description of each Timesheet's first time log, as the portal shows."""
	if not rows:
		return
	td = frappe.qb.DocType("Timesheet Detail")
	logs = (
		frappe.qb.from_(td)
		.select(td.parent, td.activity_type, td.description, td.idx)
		.where(td.parenttype == "Timesheet")
		.where(td.parent.isin([r.name for r in rows]))
		.orderby(td.idx)
		.run(as_dict=True)
	)
	first = {}
	for log in logs:
		first.setdefault(log.parent, log)
	for row in rows:
		log = first.get(row.name) or {}
		row["activity_type"] = log.get("activity_type")
		row["related_issue"] = log.get("description")


@frappe.whitelist()
def get_timesheet_filters(implementation):
	"""Projects to filter by, and the default range (the last 6 months, as on /timesheet)."""
	_require_implementation(implementation)
	projects = frappe.get_all(
		"Project",
		filters={"custom_implementation": implementation},
		fields=["name", "project_name"],
		order_by="project_name asc",
	)
	return {
		"projects": projects,
		"default_from": add_months(today(), -6),
		"default_to": today(),
	}


@frappe.whitelist()
def get_timesheets(
	implementation, from_date=None, to_date=None, project=None, start=0, page_length=20, sort_by=None, sort_order=None
):
	base = _timesheet_query(implementation, from_date, to_date, project)
	if not base:
		return {"timesheets": [], "total": 0}
	query, ts = base
	total = query.select(Count(ts.name)).run()[0][0]
	page_length = min(max(cint(page_length), 1), MAX_PAGE_LENGTH)
	rows = _timesheet_rows(query, ts, sort_by, sort_order, max(cint(start), 0), page_length)
	return {"timesheets": rows, "total": total}


@frappe.whitelist()
def export_timesheets(implementation, from_date=None, to_date=None, project=None, sort_by=None, sort_order=None):
	"""Every row of the filter for the CSV download (the client writes the file)."""
	base = _timesheet_query(implementation, from_date, to_date, project)
	if not base:
		return []
	query, ts = base
	return _timesheet_rows(query, ts, sort_by, sort_order, 0, MAX_EXPORT_ROWS)


@frappe.whitelist()
def get_timesheet_summary(implementation, from_date=None, to_date=None, project=None, group_by="month"):
	"""Totals and hours per week or month; every period of the range is present, empty ones too."""
	group_by = "week" if group_by == "week" else "month"
	base = _timesheet_query(implementation, from_date, to_date, project)
	rows = []
	if base:
		query, ts = base
		rows = query.select(ts.start_date, ts.total_hours, ts.total_billable_hours).run(as_dict=True)

	hours = sum(flt(r.total_hours) for r in rows)
	billable = sum(flt(r.total_billable_hours) for r in rows)
	buckets = {}
	for r in rows:
		key = _period_start(r.start_date, group_by)
		bucket = buckets.setdefault(key, [0.0, 0.0])
		bucket[0] += flt(r.total_hours)
		bucket[1] += flt(r.total_billable_hours)

	dates = [r.start_date for r in rows]
	first = getdate(from_date) if from_date else (min(dates) if dates else None)
	last = getdate(to_date) if to_date else (max(dates) if dates else None)
	# A very wide range (dates come from the caller) would mean thousands of empty periods:
	# then show the span that has timesheets, and never more than MAX_PERIODS bars.
	if first and last and _period_count(first, last, group_by) > MAX_PERIODS and dates:
		first, last = max(first, min(dates)), min(last, max(dates))
	periods = []
	if first and last:
		key = _period_start(first, group_by)
		end = _period_start(last, group_by)
		while key <= end and len(periods) < MAX_PERIODS:
			total, bill = buckets.get(key, (0.0, 0.0))
			periods.append({"start": key, "hours": round(total, 2), "billable": round(bill, 2)})
			key = add_days(key, 7) if group_by == "week" else add_months(key, 1)

	return {
		"hours": round(hours, 2),
		"billable_hours": round(billable, 2),
		"non_billable_hours": round(hours - billable, 2),
		"count": len(rows),
		"group_by": group_by,
		"periods": periods,
	}


def _period_count(first, last, group_by):
	first, last = getdate(first), getdate(last)
	if group_by == "week":
		return (last - first).days // 7 + 1
	return (last.year - first.year) * 12 + last.month - first.month + 1


def _period_start(value, group_by):
	day = getdate(value)
	if group_by == "week":
		return add_days(day, -day.weekday())  # Monday
	return day.replace(day=1)


@frappe.whitelist(methods=["POST"])
def set_timesheet_feedback(implementation, timesheet, rating, comment=None):
	"""Rating (1-5) and comment on a Timesheet, once, as the portal's "Give Feedback" did.

	Writes the same fields as phamos.api.update_customer_comment, so the daily comment summary
	(send_daily_timesheet_comment_summary) picks it up unchanged.
	"""
	base = _timesheet_query(implementation)
	if not base:
		frappe.throw(_("This timesheet does not belong to the implementation."), frappe.PermissionError)
	query, ts = base
	if not query.select(ts.name).where(ts.name == timesheet).run():
		frappe.throw(_("This timesheet does not belong to the implementation."), frappe.PermissionError)

	rating = cint(rating)
	if rating < 1 or rating > 5:
		frappe.throw(_("Please give a rating from 1 to 5."))
	if cint(frappe.db.get_value("Timesheet", timesheet, "custom_rating")) > 0:
		frappe.throw(_("Feedback for this timesheet was already given and is under review."))

	from phamos.api import _set_gitlab_urls_from_comment

	doc = frappe.get_doc("Timesheet", timesheet)
	comment = (comment or "").strip()
	doc.db_set(
		{
			"customer_comment": comment,
			"custom_rating": rating,
			"custom_customer_comment_timestamp": now_datetime(),
			"custom_daily_comment_report_sent": 0,
		}
	)
	if comment:
		_set_gitlab_urls_from_comment(doc, comment)
	return {"name": timesheet, "custom_rating": rating, "customer_comment": comment}


# Sales Orders and Links: the other two tabs of /timesheet, scoped to one Implementation.


@frappe.whitelist()
def get_sales_orders(implementation):
	"""Submitted Sales Orders of the Implementation with delivered and remaining hours.

	Same figures as the portal's get_customer_sales_order_status, for one Implementation. Hours
	only: amounts wait for the role views (#1673).
	"""
	_require_implementation(implementation)
	so = frappe.qb.DocType("Sales Order")
	orders = (
		frappe.qb.from_(so)
		.select(
			so.name,
			so.customer_name.as_("title"),
			so.status,
			so.total_qty.as_("total_hrs"),
			so.transaction_date,
			so.delivery_date,
			so.per_delivered,
			so.per_billed,
		)
		.where(so.custom_implementation == implementation)
		.where(so.docstatus == 1)
		.where(so.status != "Cancelled")
		.orderby(so.transaction_date, order=Order.desc)
		.run(as_dict=True)
	)

	delivered = {}
	if orders:
		soi = frappe.qb.DocType("Sales Order Item")
		delivered = dict(
			frappe.qb.from_(soi)
			.select(soi.parent, Sum(soi.delivered_qty))
			.where(soi.parent.isin([o.name for o in orders]))
			.groupby(soi.parent)
			.run()
		)

	total_so_hrs = total_delivered = 0.0
	open_count = 0
	for order in orders:
		order.total_hrs = flt(order.total_hrs)
		order.delivered_hrs = flt(delivered.get(order.name))
		order.remaining_hrs = order.total_hrs - order.delivered_hrs
		total_so_hrs += order.total_hrs
		total_delivered += order.delivered_hrs
		if order.status not in ("Completed", "Closed"):
			open_count += 1

	timesheet_hrs = _billable_hours_not_delivered(implementation)
	return {
		"sales_orders": orders,
		"summary": {
			"total_so_hrs": total_so_hrs,
			"delivered_hrs": total_delivered,
			"timesheet_hrs": timesheet_hrs,
			"remaining_hrs": total_so_hrs - (total_delivered + timesheet_hrs),
			"open_so_count": open_count,
			"total_so_count": len(orders),
		},
	}


def _billable_hours_not_delivered(implementation):
	"""Billable draft Timesheet hours not yet on a Delivery Note (as the Implementation computes it)."""
	projects = _implementation_projects(implementation)
	if not projects:
		return 0.0
	ts = frappe.qb.DocType("Timesheet")
	td = frappe.qb.DocType("Timesheet Detail")
	result = (
		frappe.qb.from_(ts)
		.join(td)
		.on(td.parent == ts.name)
		.select(Sum(td.hours))
		.where(td.is_billable == 1)
		.where(ts.docstatus == 0)
		.where(td.project.isin(projects))
		.where(td.custom_implementation == implementation)
		.where(ts.custom_delivery_note.isnull())
		.run()
	)
	return flt(result[0][0]) if result else 0.0


@frappe.whitelist()
def get_links(implementation):
	"""The Implementation's links (today a Text Editor field) as sanitized HTML; a table follows in #1682."""
	_require_implementation(implementation)
	html = frappe.db.get_value("Implementation", implementation, "links") or ""
	return {"html": sanitize_html(html, linkify=True, always_sanitize=True)}


# Issues (#1671, phase A): the reports made through Phriend about an Implementation, with the
# stage their GitLab issues are in. Internal users only for now; customers follow with #1938.

ISSUE_SCOPES = ("record", "page", "mine", "implementation")
ISSUE_LIST_FIELDS = (
	"name",
	"subject",
	"status",
	"priority",
	"phriend_type",
	"phriend_reported_by",
	"phriend_reported_by_name",
	"phriend_route",
	"phriend_ref_doctype",
	"phriend_ref_docname",
	"opening_date",
	"modified",
)
CLOSED_ISSUE_STATUSES = ("Resolved", "Closed")
# GitLab labels that move an issue on (phamos label workflow); anything else open counts as "In GitLab".
TESTING_LABELS = ("testing", "ready for production")
WORKING_LABELS = ("working", "in progress", "doing")
STAGES = ("Reported", "In GitLab", "In Progress", "Testing", "Done")


def _require_internal():
	if not is_internal_user() or not has_internal_access():
		frappe.throw(_("Only phamos staff can see the issues of an implementation for now."), frappe.PermissionError)


def _issue_filters(implementation, scope, route=None, ref_doctype=None, ref_docname=None):
	filters = {"custom_implementation": implementation}
	if scope == "record":
		filters.update({"phriend_ref_doctype": ref_doctype or "", "phriend_ref_docname": ref_docname or ""})
	elif scope == "page":
		filters["phriend_route"] = (route or "").lstrip("/")[:140]
	elif scope == "mine":
		filters["phriend_reported_by"] = frappe.session.user
	return filters


def _count_issues(filters):
	"""Issues the user may read in Desk (role and User Permissions), counted.

	The cockpit never shows more reports than Desk would: `frappe.get_list` applies the
	doctype permissions and User Permissions that `frappe.db.count` skips.
	"""
	return len(frappe.get_list("Issue", filters=filters, pluck="name", limit_page_length=0))


def issue_stage(status, gitlab_issues):
	"""Where an Issue stands, from its own status and its GitLab issues' state and labels."""
	if status in CLOSED_ISSUE_STATUSES:
		return "Done"
	if not gitlab_issues:
		return "Reported"
	open_issues = [g for g in gitlab_issues if g["state"] != "closed"]
	if not open_issues:
		return "Done"
	labels = {label.lower() for g in open_issues for label in g["labels"]}
	if any(label.startswith(t) for label in labels for t in TESTING_LABELS):
		return "Testing"
	if labels & set(WORKING_LABELS):
		return "In Progress"
	return "In GitLab"


@frappe.whitelist()
def get_issues(implementation, scope=None, route=None, ref_doctype=None, ref_docname=None, include_closed=0):
	"""Issues of the Implementation for one scope, narrowest first: this record, this page, mine, all.

	Opened from Phriend the cockpit gets the record or page of the report; without one it shows
	the user's own reports. `counts` tells the switcher how many each scope has.
	"""
	_require_implementation(implementation)
	_require_internal()
	from phamos.phriend.gitlab_issues import issue_gitlab_issues

	available = ["mine", "implementation"]
	if route:
		available.insert(0, "page")
	if ref_doctype and ref_docname:
		available.insert(0, "record")
	scope = scope if scope in available else available[0]

	status_filter = {} if cint(include_closed) else {"status": ["not in", CLOSED_ISSUE_STATUSES]}
	counts = {
		s: _count_issues({**_issue_filters(implementation, s, route, ref_doctype, ref_docname), **status_filter})
		for s in available
	}
	rows = frappe.get_list(  # as Desk shows them: role and User Permissions apply
		"Issue",
		filters={**_issue_filters(implementation, scope, route, ref_doctype, ref_docname), **status_filter},
		fields=ISSUE_LIST_FIELDS,
		order_by="modified desc",
		limit_page_length=200,
	)
	for row in rows:
		row["gitlab_issues"] = issue_gitlab_issues(row.name)
		row["stage"] = issue_stage(row.status, row["gitlab_issues"])
	return {"scope": scope, "available": available, "counts": counts, "issues": rows, "stages": STAGES}


@frappe.whitelist()
def get_issue_counts(implementation):
	"""Open reports of the Implementation, all and mine, for the Overview tile (internal only)."""
	_require_implementation(implementation)
	if not is_internal_user() or not has_internal_access():
		return None
	open_filter = {"custom_implementation": implementation, "status": ["not in", CLOSED_ISSUE_STATUSES]}
	return {
		"open": _count_issues(open_filter),
		"mine": _count_issues({**open_filter, "phriend_reported_by": frappe.session.user}),
	}


@frappe.whitelist()
def get_issue(implementation, name):
	"""One Issue of the Implementation with its report details and GitLab issues."""
	_require_implementation(implementation)
	_require_internal()
	if frappe.db.get_value("Issue", name, "custom_implementation") != implementation:
		frappe.throw(_("This issue does not belong to the implementation."), frappe.PermissionError)
	# what Desk would allow, including User Permissions; screenshot and comment are part of it
	if not frappe.has_permission("Issue", "read", doc=name):
		frappe.throw(_("You do not have access to this issue."), frappe.PermissionError)
	from phamos.phriend.gitlab_issues import issue_gitlab_issues

	row = frappe.db.get_value(
		"Issue",
		name,
		[*ISSUE_LIST_FIELDS, "phriend_comment", "phriend_screenshot", "phriend_page_url", "resolution_details"],
		as_dict=True,
	)
	row["gitlab_issues"] = issue_gitlab_issues(name)
	row["stage"] = issue_stage(row.status, row["gitlab_issues"])
	row["stages"] = STAGES
	return row


@frappe.whitelist()
def resolve_status(route=None, ref_doctype=None, ref_docname=None, issue=None):
	"""The Implementation to open from Phriend (badge, "See their status", "Follow its status") (#1671).

	For one Issue: the Implementation it was filed under. For a page or record: the same rule
	Phriend uses when it files a report (phamos.phriend.api.report_implementation). Limited to
	Implementations the user may open; None makes the cockpit open the last one used.
	"""
	_require_internal()
	if issue:
		readable = frappe.db.exists("Issue", issue) and frappe.has_permission("Issue", "read", doc=issue)
		implementation = frappe.db.get_value("Issue", issue, "custom_implementation") if readable else None
	else:
		from phamos.phriend.api import report_implementation

		settings = frappe.get_cached_doc("Phriend Settings")
		implementation = report_implementation(settings, route, ref_doctype, ref_docname)
	return implementation if implementation in _allowed_implementations() else None


# Features (#1972): list, Kanban and WBS of the implementation's features. Customers see them
# read-only; staff who may write Implementation Feature move cards on the Kanban.

FEATURE_STATUSES = ("Idea", "Agreed", "Planned", "In Progress", "In Testing", "Live", "Dropped")
FEATURE_LIST_FIELDS = (
	"name",
	"title",
	"status",
	"priority",
	"module",
	"owner_user",
	"target_level",
	"current_level",
	"estimated_hours",
	"planned_start",
	"target_date",
	"gitlab_milestone",
	"dod_agreed_on",
)
GITLAB_ISSUE_FIELDS = (
	"name",
	"issue_id",
	"title",
	"state",
	"issue_url",
	"gitlab_milestone",
	"implementation_feature",
	"created_at",
	"closed_at",
	"aging_days",
	"total_touch_time",
	"time_estimate_hours",
	"time_spent_hours",
)


def _can_move_features():
	"""Staff who may change features in Desk move cards; customers only look."""
	return is_internal_user() and bool(frappe.has_permission("Implementation Feature", "write"))


def _feature_rows(implementation):
	return frappe.get_all(
		"Implementation Feature",
		filters={"implementation": implementation},
		fields=list(FEATURE_LIST_FIELDS),
		order_by="planned_start asc, creation asc",
	)


def _issues_by_feature(features):
	issues = {}
	for issue in frappe.get_all(
		"GitLab Issue",
		filters={"implementation_feature": ["in", features or [""]]},
		fields=list(GITLAB_ISSUE_FIELDS),
		order_by="created_at asc",
	):
		issues.setdefault(issue.implementation_feature, []).append(issue)
	return issues


def _parents_by_feature(child_doctype, parent_doctype, features, label_field):
	"""{feature: [{name, label}]} for chapters or releases that list the feature."""
	rows = frappe.get_all(
		child_doctype,
		filters={"feature": ["in", features or [""]], "parenttype": parent_doctype},
		fields=["feature", "parent"],
	)
	labels = dict(
		frappe.get_all(
			parent_doctype,
			filters={"name": ["in", list({r.parent for r in rows}) or [""]]},
			fields=["name", label_field],
			as_list=True,
		)
	)
	out = {}
	for row in rows:
		out.setdefault(row.feature, []).append({"name": row.parent, "label": labels.get(row.parent) or row.parent})
	return out


def _percent(value):
	"""Half-up, as people read percentages (Python's round() would make 62.5 into 62)."""
	return int(value + 0.5)


def feature_progress(feature, issues):
	"""Progress of one feature in percent: Live is done; otherwise the closed share of its GitLab
	issues; otherwise how far its level has come towards the target. Dropped counts nowhere."""
	if feature.status == "Live":
		return 100
	if issues:
		return _percent(100 * sum(1 for i in issues if i.state == "closed") / len(issues))
	if cint(feature.target_level):
		return min(100, _percent(100 * cint(feature.current_level) / cint(feature.target_level)))
	return 0


def feature_weight(feature, issues):
	"""Hours a feature weighs in the WBS roll-up: its estimate, or its issues' estimates if larger."""
	return max(flt(feature.estimated_hours), sum(flt(i.time_estimate_hours) for i in issues))


def roll_up(items):
	"""Weighted progress of (progress, weight) pairs; plain average when no item has hours."""
	items = list(items)
	if not items:
		return 0
	total = sum(weight for _progress, weight in items)
	if total:
		return _percent(sum(progress * weight for progress, weight in items) / total)
	return _percent(sum(progress for progress, _weight in items) / len(items))


def _wip(implementation, features):
	limit = cint(frappe.db.get_value("Implementation", implementation, "max_parallel_features"))
	running = sum(1 for f in features if f.status == "In Progress")
	return {"running": running, "limit": limit, "over": bool(limit and running > limit)}


@frappe.whitelist()
def get_features(implementation):
	"""The implementation's features with effort, progress, chapters, releases and issue figures."""
	_require_implementation(implementation)
	from phamos.phamos.doctype.implementation_release.implementation_release import feature_efforts

	features = _feature_rows(implementation)
	names = [f.name for f in features]
	issues = _issues_by_feature(names)
	efforts = feature_efforts(features) if features else {}
	chapters = _parents_by_feature("Implementation Chapter Feature", "Implementation Chapter", names, "chapter_title")
	releases = _parents_by_feature("Implementation Release Feature", "Implementation Release", names, "title")
	owners = {u: frappe.utils.get_fullname(u) for u in {f.owner_user for f in features if f.owner_user}}
	today_date = getdate(today())
	rows = []
	for feature in features:
		linked = issues.get(feature.name, [])
		open_issues = [i for i in linked if i.state != "closed"]
		rows.append(
			{
				# the responsible's name only: a staff e-mail address is not needed in the cockpit
				**{key: value for key, value in feature.items() if key != "owner_user"},
				"owner_name": owners.get(feature.owner_user),
				"effort_hours": round(flt(efforts.get(feature.name)), 1),
				"progress": feature_progress(feature, linked),
				"chapters": chapters.get(feature.name, []),
				"releases": releases.get(feature.name, []),
				"issues_open": len(open_issues),
				"issues_total": len(linked),
				# the oldest open issue, in days: what has been waiting longest on this card
				"oldest_open_days": max(
					((today_date - getdate(i.created_at)).days for i in open_issues if i.created_at), default=None
				),
				"touch_hours": round(sum(flt(i.total_touch_time) for i in linked) / 3600, 1),
			}
		)
	return {
		"features": rows,
		"statuses": FEATURE_STATUSES,
		"wip": _wip(implementation, features),
		"can_move": _can_move_features(),
	}


@frappe.whitelist()
def get_feature(implementation, name):
	"""One feature in full: definition of done, history, doctypes and its GitLab issues."""
	_require_implementation(implementation)
	if frappe.db.get_value("Implementation Feature", name, "implementation") != implementation:
		frappe.throw(_("This feature does not belong to the implementation."), frappe.PermissionError)
	doc = frappe.get_doc("Implementation Feature", name)
	issues = _issues_by_feature([name]).get(name, [])
	library = dict(
		frappe.get_all(
			"Implementation Doctype",
			filters={"name": ["in", [d.implementation_doctype for d in doc.doctypes] or [""]]},
			fields=["name", "kind"],
			as_list=True,
		)
	)
	contact = doc.dod_agreed_by and frappe.db.get_value("Contact", doc.dod_agreed_by, "full_name")
	return {
		**{field: doc.get(field) for field in FEATURE_LIST_FIELDS if field != "owner_user"},
		"description": sanitize_html(doc.description or "", always_sanitize=True),
		"definition_of_done": doc.definition_of_done,
		"dod_agreed_by_name": contact or doc.dod_agreed_by,
		"owner_name": doc.owner_user and frappe.utils.get_fullname(doc.owner_user),
		"progress": feature_progress(doc, issues),
		"chapters": _parents_by_feature("Implementation Chapter Feature", "Implementation Chapter", [name], "chapter_title").get(name, []),
		"releases": _parents_by_feature("Implementation Release Feature", "Implementation Release", [name], "title").get(name, []),
		"history": [
			{"date": row.date, "status": row.status, "level": row.level, "note": row.note, "by": frappe.utils.get_fullname(row.by) if row.by else None}
			for row in reversed(doc.progress)
		],
		"doctypes": [
			{"name": row.implementation_doctype, "kind": library.get(row.implementation_doctype), "work_done": row.work_done}
			for row in doc.doctypes
		],
		"touch_hours": round(sum(flt(i.total_touch_time) for i in issues) / 3600, 1),
		# what the cockpit shows of each issue; GitLab-internal figures stay on the server
		"issues": [
			{field: i.get(field) for field in ("name", "issue_id", "title", "state", "issue_url", "time_estimate_hours")}
			for i in issues
		],
		"can_move": _can_move_features(),
		"statuses": FEATURE_STATUSES,
	}


@frappe.whitelist()
def set_feature_status(implementation, name, status):
	"""Move a card on the Kanban. Status is daily work (#1971); a move to Dropped after the
	baseline is recorded as a scope change for the customer by the feature's own hooks."""
	_require_implementation(implementation)
	if not _can_move_features():
		frappe.throw(_("Only phamos staff can move features."), frappe.PermissionError)
	if status not in FEATURE_STATUSES:
		frappe.throw(_("Unknown status {0}.").format(status))
	if frappe.db.get_value("Implementation Feature", name, "implementation") != implementation:
		frappe.throw(_("This feature does not belong to the implementation."), frappe.PermissionError)
	doc = frappe.get_doc("Implementation Feature", name)
	doc.check_permission("write")
	doc.status = status
	doc.save()
	return {"status": doc.status, "wip": _wip(implementation, _feature_rows(implementation))}


@frappe.whitelist()
def get_wbs(implementation):
	"""Implementation → Modules → Features → GitLab issues, with progress rolled up by hours."""
	_require_implementation(implementation)
	features = [f for f in _feature_rows(implementation) if f.status != "Dropped"]
	issues = _issues_by_feature([f.name for f in features])
	milestones = dict(
		frappe.get_all(
			"GitLab Milestones",
			filters={"name": ["in", list({i.gitlab_milestone for rows in issues.values() for i in rows if i.gitlab_milestone}) or [""]]},
			fields=["name", "title"],
			as_list=True,
		)
	)
	modules = {}
	for feature in features:
		linked = issues.get(feature.name, [])
		node = {
			"name": feature.name,
			"title": feature.title,
			"status": feature.status,
			"progress": feature_progress(feature, linked),
			"weight_hours": round(feature_weight(feature, linked), 1),
			"issues": [
				{
					"name": i.name,
					"issue_id": i.issue_id,
					"title": i.title,
					"state": i.state,
					"url": i.issue_url,
					"milestone": milestones.get(i.gitlab_milestone) or i.gitlab_milestone,
				}
				for i in linked
			],
		}
		modules.setdefault(feature.module or "", []).append(node)
	tree = []
	for module, nodes in sorted(modules.items(), key=lambda item: (item[0] == "", item[0])):
		tree.append(
			{
				"module": module,
				"progress": roll_up((n["progress"], n["weight_hours"]) for n in nodes),
				"weight_hours": round(sum(n["weight_hours"] for n in nodes), 1),
				"features": nodes,
			}
		)
	all_nodes = [n for m in tree for n in m["features"]]
	return {
		"progress": roll_up((n["progress"], n["weight_hours"]) for n in all_nodes),
		"weight_hours": round(sum(n["weight_hours"] for n in all_nodes), 1),
		"weighted": any(n["weight_hours"] for n in all_nodes),
		"modules": tree,
	}


# Roadmap (#1694, data #2033): modules in their depth levels over time.
CHAPTER_STATUSES_HIDDEN_FROM_CUSTOMERS = ("Draft", "Cancelled")
# Draft chapters are not agreed yet and Cancelled ones won't happen: neither decides the end date.
CHAPTER_STATUSES_ON_CRITICAL_PATH = ("Planned", "In Progress", "Blocked")
ROADMAP_CHAPTER_FIELDS = (
	"name",
	"chapter_title",
	"status",
	"module",
	"planned_start",
	"target_date",
	"current_level",
	"target_level",
)


def _can_propose_dates():
	"""Staff who may create an Implementation Change get "Propose a date change"; customers don't."""
	return is_internal_user() and bool(frappe.has_permission("Implementation Change", "create"))


def _baseline_rows(implementation):
	"""The current baseline and its chapter dates and levels by chapter, and the features it holds.

	Read here rather than through `get_baseline_variance`: that one checks Desk read permission on
	Implementation, which customers (website users) don't have, and reads every chapter again.
	"""
	baseline = frappe.db.get_value(
		"Implementation Baseline",
		{"implementation": implementation, "is_current": 1},
		["name", "baseline_date"],
		as_dict=True,
	)
	if not baseline:
		return None, {}, set()
	chapters = {
		row.chapter: row
		for row in frappe.get_all(
			"Implementation Baseline Chapter",
			filters={"parent": baseline.name, "parenttype": "Implementation Baseline"},
			fields=["chapter", "planned_start", "target_date", "current_level"],
		)
	}
	features = set(
		frappe.get_all(
			"Implementation Baseline Feature",
			filters={"parent": baseline.name, "parenttype": "Implementation Baseline"},
			pluck="feature",
		)
	)
	return baseline, chapters, features


def _target_reached(row):
	"""A chapter (or module row) is done when it has reached its target level.

	Chapters have no Done status; their level says how far they are (#2033 decision 7). Done
	work has no slack and doesn't decide the end date any more.
	"""
	target = cint(row.target_level)
	return bool(target) and cint(row.current_level) >= target


def _days_between(then, now):
	if not then or not now:
		return None
	return (getdate(now) - getdate(then)).days


def _finished_dates(features):
	"""{feature: date of its latest progress row with status Live}."""
	finished = {}
	for row in frappe.get_all(
		"Implementation Feature Progress",
		filters={"parent": ["in", features or [""]], "parenttype": "Implementation Feature", "status": "Live"},
		fields=["parent", "date"],
	):
		if row.date and (row.parent not in finished or getdate(row.date) > getdate(finished[row.parent])):
			finished[row.parent] = row.date
	return finished


def _roadmap_markers(implementation, features_by_name, visible_chapters):
	"""GitLab milestones with a due date and the releases still planned, as dated markers.

	A release tied to a chapter the viewer doesn't see (a Draft one, for customers) stays hidden
	with it.
	"""
	projects = frappe.get_all("GitLab Project", filters={"implementation": implementation}, pluck="name")
	milestones = (
		frappe.get_all(
			"GitLab Milestones",
			filters={"gitlab_project": ["in", projects], "due_date": ["is", "set"]},
			fields=["name", "title", "due_date", "state", "web_url"],
			order_by="due_date asc",
		)
		if projects
		else []
	)
	releases = frappe.get_all(
		"Implementation Release",
		filters={"implementation": implementation, "status": ["!=", "Cancelled"], "target_date": ["is", "set"]},
		fields=["name", "title", "target_date", "chapter"],
		order_by="target_date asc",
	)
	releases = [r for r in releases if not r.chapter or r.chapter in visible_chapters]
	release_features = {}
	for row in frappe.get_all(
		"Implementation Release Feature",
		filters={"parent": ["in", [r.name for r in releases] or [""]], "parenttype": "Implementation Release"},
		fields=["parent", "feature"],
	):
		release_features.setdefault(row.parent, []).append(row.feature)

	markers = [
		{
			"type": "milestone",
			"name": m.name,
			"title": m.title,
			"date": m.due_date,
			"state": m.state,
			"web_url": m.web_url,
		}
		for m in milestones
	]
	for release in releases:
		late = [
			{"name": f.name, "title": f.title}
			for f in (features_by_name.get(name) for name in release_features.get(release.name, []))
			# a Live feature is done, however late: only open work can still miss the release
			if f and f.status != "Live" and f.target_date and getdate(f.target_date) > getdate(release.target_date)
		]
		markers.append(
			{
				"type": "release",
				"name": release.name,
				"title": release.title,
				"date": release.target_date,
				"late_features": late,
			}
		)
	return markers


def _roadmap_dates(rows, markers):
	"""Every date the Roadmap draws (bars, baseline bars, events, markers), for its initial range."""
	dates = []
	for row in rows:
		for bar in row["bars"]:
			dates += [bar["planned_start"], bar["target_date"]]
			if bar["baseline"]:
				dates += [bar["baseline"]["planned_start"], bar["baseline"]["target_date"]]
		dates += [event["date"] for event in row["events"]]
	dates += [marker["date"] for marker in markers]
	return [getdate(value) for value in dates if value]


@frappe.whitelist()
def get_roadmap(implementation):
	"""Everything the Roadmap draws: one row per module with its chapters as level-step bars,
	features as events, chapter dependencies, the critical path, markers and the baseline.

	Customers get the same picture without Draft and Cancelled chapters (#1694 decision 12).
	The critical path runs through the agreed chapters only, for staff and customers alike, so
	both see the same slack.
	"""
	_require_implementation(implementation)

	internal = is_internal_user()
	chapters = frappe.get_all(
		"Implementation Chapter",
		filters={"implementation": implementation},
		fields=list(ROADMAP_CHAPTER_FIELDS),
		order_by="planned_start asc, creation asc",
	)
	if not internal:
		chapters = [c for c in chapters if c.status not in CHAPTER_STATUSES_HIDDEN_FROM_CUSTOMERS]
	chapter_names = {c.name for c in chapters}
	depends_on = {}
	for row in frappe.get_all(
		"Implementation Chapter Dependency",
		filters={"parent": ["in", list(chapter_names) or [""]], "parenttype": "Implementation Chapter"},
		fields=["parent", "chapter"],
	):
		if row.chapter not in depends_on.setdefault(row.parent, []):
			depends_on[row.parent].append(row.chapter)

	path = critical_path(
		[
			{
				"name": c.name,
				"planned_start": c.planned_start,
				"target_date": c.target_date,
				"depends_on": depends_on.get(c.name, []),
			}
			for c in chapters
			if c.status in CHAPTER_STATUSES_ON_CRITICAL_PATH and not _target_reached(c)
		]
	)["items"]

	baseline, baseline_chapters, baseline_features = _baseline_rows(implementation)

	def chapter_bar(chapter):
		then = baseline_chapters.get(chapter.name)
		on_path = path.get(chapter.name, {})
		done = _target_reached(chapter)
		return {
			"name": chapter.name,
			"chapter": chapter.name,
			"title": chapter.chapter_title or chapter.name,
			"status": chapter.status,
			"planned_start": chapter.planned_start,
			"target_date": chapter.target_date,
			# the level when the plan was agreed: where the level step starts (None without baseline)
			"start_level": (cint(then.current_level) or None) if then else None,
			"current_level": cint(chapter.current_level) or None,
			"target_level": cint(chapter.target_level) or None,
			"done": done,
			"critical": False if done else on_path.get("critical"),
			"slack_days": None if done else on_path.get("slack_days"),
			"cycle": bool(on_path.get("cycle")),
			"baseline": {
				"planned_start": then.planned_start,
				"target_date": then.target_date,
				"shift_days": _days_between(then.target_date, chapter.target_date),
			}
			if then
			else None,
			"is_new": bool(baseline) and not then,
		}

	features = [f for f in _feature_rows(implementation) if f.status != "Dropped"]
	features_by_name = {f.name: f for f in features}
	finished = _finished_dates([f.name for f in features if f.status == "Live"])

	def feature_events(feature):
		common = {
			"name": feature.name,
			"title": feature.title,
			"status": feature.status,
			"is_new": bool(baseline) and feature.name not in baseline_features,
		}
		events = []
		if feature.planned_start:
			events.append({**common, "kind": "planned", "date": feature.planned_start})
		if feature.status == "Live" and finished.get(feature.name):
			events.append({**common, "kind": "finished", "date": finished[feature.name]})
		return events

	# Rows in the order of the Implementation's Modules table (Implementation Item). Saving a
	# chapter adds a row for it there, often without a module; a chapter's module is its own
	# `module`, else the module set on its row. Chapters of a module missing from the table get a
	# row after the others; chapters and features without any module go to "No module".
	items = frappe.get_all(
		"Implementation Item",
		filters={"parent": implementation, "parenttype": "Implementation", "parentfield": "modules"},
		fields=["name", "module", "implementation_chapter", "planned_start", "target_date", "current_level", "target_level"],
		order_by="idx asc",
	)
	# two rows pointing at the same chapter with different modules: the later row wins
	module_of_chapter = {i.implementation_chapter: i.module for i in items if i.implementation_chapter and i.module}
	rows = {}
	for item in items:
		# a row whose chapter the viewer doesn't see (Draft, for customers) would show up empty
		# and give the chapter away
		if item.module and (not item.implementation_chapter or item.implementation_chapter in chapter_names):
			rows.setdefault(item.module, {"module": item.module, "label": item.module, "bars": [], "events": []})
	no_module = {"bars": [], "events": []}
	for chapter in chapters:
		module = chapter.module or module_of_chapter.get(chapter.name)
		if not module:
			no_module["bars"].append(chapter_bar(chapter))
			continue
		rows.setdefault(module, {"module": module, "label": module, "bars": [], "events": []})
		rows[module]["bars"].append(chapter_bar(chapter))
	for item in items:
		if item.module and not item.implementation_chapter:
			# A module row without a chapter is planned on the Modules table only: a bar from its
			# own dates and levels, outside the critical path. (A row with a chapter never shows its
			# own dates: the chapter is the plan, and a hidden Draft chapter must stay hidden.)
			rows[item.module]["bars"].append(
				{
					"name": f"item:{item.name}",
					"chapter": None,
					"title": item.module,
					"status": None,
					"planned_start": item.planned_start,
					"target_date": item.target_date,
					"start_level": None,
					"current_level": cint(item.current_level) or None,
					"target_level": cint(item.target_level) or None,
					"done": _target_reached(item),
					"critical": None,
					"slack_days": None,
					"cycle": False,
					"baseline": None,
					"is_new": False,
				}
			)
	for feature in features:
		if feature.module:
			target = rows.setdefault(feature.module, {"module": feature.module, "label": feature.module, "bars": [], "events": []})
		else:
			target = no_module
		target["events"].extend(feature_events(feature))
	modules = list(rows.values())

	# All links between the chapters shown, Draft ones included for staff; critical_path() only
	# saw the agreed chapters, so its own list is not enough here.
	by_name = {c.name: c for c in chapters}
	dependencies = [
		{"from": predecessor, "to": successor, "conflict": dependency_conflict(by_name[predecessor], by_name[successor])}
		for successor, predecessors in depends_on.items()
		for predecessor in predecessors
		if predecessor in by_name and successor in by_name
	]

	markers = _roadmap_markers(implementation, features_by_name, chapter_names)
	dates = _roadmap_dates([*modules, no_module], markers)
	return {
		"modules": modules,
		"no_module": no_module,
		"dependencies": dependencies,
		"markers": markers,
		"baseline": {"name": baseline.name, "baseline_date": baseline.baseline_date} if baseline else None,
		"range": {"start": min(dates), "end": max(dates)} if dates else None,
		"can_propose": _can_propose_dates(),
	}
