from frappe import _


def get_issue_dashboard_data(data):
	"""Extra groups under the Issue form's connections.

	- GitLab Issues linked to the Issue (GitLab Issue.issue). ERPNext's Issue dashboard already links
	  on the fieldname "issue", so no non_standard_fieldnames.
	- The Issue Assistant's runs (AI Agent Run, #2154): linked by the Dynamic Link reference_doctype /
	  reference_name.

	Desk hides a group from users who may not read its doctype.
	"""
	data["transactions"].append({"label": _("GitLab"), "items": ["GitLab Issue"]})
	data["transactions"].append({"label": _("Issue Assistant"), "items": ["AI Agent Run"]})
	data.setdefault("non_standard_fieldnames", {})["AI Agent Run"] = "reference_name"
	data.setdefault("dynamic_links", {})["reference_name"] = ["Issue", "reference_doctype"]
	return data
