import frappe
from frappe.utils import cint, cstr


def normalize_percent_billable(value):
    """Return percent billable as canonical Select value (e.g. "0")."""
    try:
        percent = float(value or 0)
    except (TypeError, ValueError):
        percent = 0.0

    if percent <= 0:
        return "0"

    return cstr(value).strip()


# Presets when the Project has no Percent Billable of its own (#1896): phamos' own projects bill
# nothing, customer projects (a Customer, not Is Internal Project) bill everything.
DEFAULT_PERCENT_BILLABLE = "0"
CUSTOMER_PERCENT_BILLABLE = "100"
PROJECT_BILLING_FIELDS = ("percent_billable", "customer", "custom_is_internal_project")


def percent_billable_preset(project_value, customer=None, is_internal=0):
    """The Project's own Percent Billable; when it has none, 100 for a customer project and 0 for
    an internal one or one without a Customer (#1896)."""
    value = cstr(project_value).strip()
    if value:
        return value
    if customer and not cint(is_internal):
        return CUSTOMER_PERCENT_BILLABLE
    return DEFAULT_PERCENT_BILLABLE


def project_percent_billable_preset(project_row):
    """percent_billable_preset for a Project row holding PROJECT_BILLING_FIELDS."""
    row = project_row or {}
    return percent_billable_preset(
        row.get("percent_billable"), row.get("customer"), row.get("custom_is_internal_project")
    )


def percent_billable_or_preset(percent_billable, project):
    """The Percent Billable that was entered, or the project's preset when none was sent."""
    if percent_billable in (None, ""):
        percent_billable = billing_context(project)["percent_billable"]
    return normalize_percent_billable(percent_billable)


def billing_context(project):
    """Preset for Percent Billable: the Project's own value; when it has none, 100 for a customer
    project and 0 for phamos' own (percent_billable_preset)."""
    row = frappe.db.get_value("Project", project, PROJECT_BILLING_FIELDS, as_dict=True) if project else None
    return {"percent_billable": project_percent_billable_preset(row)}


@frappe.whitelist()
def get_billing_context(project):
    """billing_context for the panels; needs read access to the Project."""
    frappe.has_permission("Project", "read", project, throw=True)
    return billing_context(project)
