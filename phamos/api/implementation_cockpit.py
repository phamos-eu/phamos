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
