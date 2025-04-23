from frappe import _


def get_project_dashboard_data(data):
	return {
		'heatmap': True, 
		'heatmap_message': 'This is based on the Time Sheets created against this project', 
		'fieldname': 'project', 
		'transactions': [
			{
				"label": _("Project"),
				"items": ["Task", "Timesheet", "Issue", "Project Update"],
			},
			{"label": _("Material"), "items": ["Material Request", "BOM", "Stock Entry"]},
			{"label": _("Sales"), "items": ["Sales Order", "Delivery Note", "Sales Invoice"]},
			{"label": _("Purchase"), "items": ["Purchase Order", "Purchase Receipt", "Purchase Invoice"]},
			{'label': 'Project', 'items': ['Task', 'Timesheet']}, 
			{'label': 'Phamos', 'items': ['Timesheet Record']}
		], 
		'non_standard_fieldnames': {'Timesheet Record': 'project', 'Expense Claim': 'project'}, 
		'internal_links': {}
	}


