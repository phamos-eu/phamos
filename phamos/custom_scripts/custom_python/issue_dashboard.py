from frappe import _


def get_issue_dashboard_data(data):
	"""Show the GitLab Issues linked to an Issue (GitLab Issue.issue) under the Issue form's connections.

	ERPNext's Issue dashboard already links on the fieldname "issue", so no non_standard_fieldnames.
	Desk hides the group from users who may not read GitLab Issue.
	"""
	data["transactions"].append({"label": _("GitLab"), "items": ["GitLab Issue"]})
	return data
