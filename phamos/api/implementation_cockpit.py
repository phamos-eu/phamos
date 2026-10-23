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


def _allowed_implementations():
	"""Names of the Implementations the session user may open in the cockpit."""
	user = frappe.session.user
	if user == "Guest":
		return []
	if is_internal_user(user):
		# Respects role and User Permissions like Desk does.
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
	periods = []
	if first and last:
		key = _period_start(first, group_by)
		end = _period_start(last, group_by)
		while key <= end:
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
