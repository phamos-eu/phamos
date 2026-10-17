from frappe import _


def get_employee_dashboard_data(data):
	"""Show Employment Contracts under the Employee form's connections (HR Managers only can open them)."""
	data["transactions"].append({"label": _("Employment"), "items": ["Employment Contract"]})
	return data
