from frappe import _


def get_employee_dashboard_data(data):
	"""Connections of the Employee form: Employment Contracts (HR Managers only can open them) and Team
	Assignments, the person's team memberships over time (#1974)."""
	data["transactions"].append({"label": _("Employment"), "items": ["Employment Contract", "Team Assignment"]})
	return data
