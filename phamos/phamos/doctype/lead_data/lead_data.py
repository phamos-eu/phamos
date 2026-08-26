# Copyright (c) 2026, phamos.eu and contributors
# For license information, please see license.txt

import frappe
from frappe.model.document import Document

from phamos.phamos.doctype.lead_data.crm_handoff import (
	create_crm_records as _create_crm_records,
	get_improve_form as _get_improve_form,
	get_review_payload as _get_review_payload,
	link_crm_records as _link_crm_records,
	refresh_handoff_status as _refresh_handoff_status,
	skip_handoff as _skip_handoff,
	update_lead_data_fields as _update_lead_data_fields,
)


class LeadData(Document):
	pass


@frappe.whitelist()
def create_crm_records(lead_data_name, force=0, customer=None, supplier=None):
	return _create_crm_records(
		lead_data_name, force=force, customer=customer, supplier=supplier
	)


@frappe.whitelist()
def link_crm_records(lead_data_name, lead=None, contact=None, customer=None, supplier=None):
	return _link_crm_records(
		lead_data_name,
		lead=lead,
		contact=contact,
		customer=customer,
		supplier=supplier,
	)


@frappe.whitelist()
def skip_handoff(lead_data_name):
	return _skip_handoff(lead_data_name)


@frappe.whitelist()
def get_review_payload(lead_data_name):
	return _get_review_payload(lead_data_name)


@frappe.whitelist()
def refresh_handoff_status(lead_data_name):
	doc = frappe.get_doc("Lead Data", lead_data_name)
	frappe.has_permission("Lead Data", doc=doc.name, ptype="write", throw=True)
	_refresh_handoff_status(doc, commit=True)
	return _get_review_payload(lead_data_name)


@frappe.whitelist()
def get_improve_form(lead_data_name):
	return _get_improve_form(lead_data_name)


@frappe.whitelist()
def update_lead_data_fields(lead_data_name, values=None, create_after=1):
	return _update_lead_data_fields(lead_data_name, values=values, create_after=create_after)
