import frappe
from frappe import _
import json


@frappe.whitelist()
def make_timesheet(doc):
	if not isinstance(doc, dict):
		doc = frappe._dict(json.loads(doc))

	timesheet = frappe.new_doc("Timesheet Record")

	timesheet.project = doc.project
	timesheet.customer =  doc.customer
	timesheet.activity_type =  doc.activity_type
	timesheet.task =  doc.task
	timesheet.from_time =  doc.from_time
	timesheet.expected_time =  doc.expected_time
	timesheet.goal = doc.goal

	timesheet.save()
	return timesheet.name


def get_data():
	return {
		"heatmap": True,
		"heatmap_message": _("This is based on the Time Sheets created against this project"),
		"fieldname": "project",
		"transactions": [
			{
				"label": _("Project"),
				"items": ["Task", "Timesheet", "Timesheet Record", "Issue", "Project Update"],
			},
			{"label": _("Material"), "items": ["Material Request", "BOM", "Stock Entry"]},
			{"label": _("Sales"), "items": ["Sales Order", "Delivery Note", "Sales Invoice"]},
			{"label": _("Purchase"), "items": ["Purchase Order", "Purchase Receipt", "Purchase Invoice"]},
		],
	}
