"""Who came, who paid, who needs a call: one row per attendee of an event (follow-up list)."""

import json

import frappe
from frappe import _

FILTER_FIELDS = ("event", "role", "status", "payment_status", "crm_status", "follow_up_status")


def execute(filters=None):
	filters = frappe._dict(filters or {})
	conditions = {key: filters[key] for key in FILTER_FIELDS if filters.get(key)}
	if filters.get("vip"):
		conditions["vip"] = 1
	rows = frappe.get_list("Attendee", filters=conditions, fields=[
		"name", "event", "full_name", "email", "phone", "company_name", "job_title", "role", "vip", "status",
		"payment_status", "crm_status", "customer", "lead", "contact", "opportunity", "sales_order",
		"sales_invoice", "follow_up_status", "follow_up_on", "follow_up_notes", "_assign",
	], order_by="company_name asc, full_name asc", limit_page_length=0)
	for row in rows:
		row["assigned_to"] = ", ".join(json.loads(row.pop("_assign") or "[]"))
	return columns(), rows


def columns():
	def col(fieldname, label, fieldtype="Data", options=None, width=120):
		return {"fieldname": fieldname, "label": _(label), "fieldtype": fieldtype, "options": options, "width": width}

	return [
		col("name", "Attendee", "Link", "Attendee", 140),
		col("full_name", "Name", width=170),
		col("company_name", "Company", width=160),
		col("email", "Email", width=200),
		col("phone", "Phone"),
		col("role", "Role", width=90),
		col("vip", "VIP", "Check", width=60),
		col("status", "Status", width=100),
		col("payment_status", "Payment", width=100),
		col("crm_status", "CRM", width=100),
		col("customer", "Customer", "Link", "Customer", 150),
		col("lead", "Lead", "Link", "Lead"),
		col("contact", "Contact", "Link", "Contact"),
		col("opportunity", "Opportunity", "Link", "Opportunity"),
		col("sales_order", "Sales Order", "Link", "Sales Order"),
		col("sales_invoice", "Sales Invoice", "Link", "Sales Invoice"),
		col("follow_up_status", "Follow-up", width=100),
		col("follow_up_on", "Follow-up On", "Date", width=100),
		col("follow_up_notes", "Follow-up Notes", width=200),
		col("assigned_to", "Assigned To", width=160),
		col("event", "Event", "Link", "Marketing Content", 160),
	]
