from frappe import _


def get_project_dashboard_data(data):
	return {
		'heatmap': True, 
		'heatmap_message': 'This is based on the Time Sheets created against this project', 
		'fieldname': 'project', 
		'transactions': [
			{'label': 'Project', 'items': ['Task', 'Timesheet']}, 
			{'label': 'Phamos', 'items': ['Timesheet Record']}
		], 
		'non_standard_fieldnames': {'Timesheet Record': 'project', 'Expense Claim': 'project'}, 
		'internal_links': {}
	}