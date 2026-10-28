import frappe
from frappe.utils import cint, cstr

RATING_OPTIONS = ("0", "25", "50", "75", "100")


def normalize_percent_billable(value):
    """Return percent billable as canonical Select value (e.g. "0")."""
    try:
        percent = float(value or 0)
    except (TypeError, ValueError):
        percent = 0.0

    if percent <= 0:
        return "0"

    return cstr(value).strip()


def is_billable_project(project):
    """Percent Billable only counts on projects with an Implementation that are not internal (#1031)."""
    if not project:
        return False
    values = frappe.db.get_value(
        "Project", project, ["custom_implementation", "custom_is_internal_project"], as_dict=True
    )
    return bool(values and values.custom_implementation and not cint(values.custom_is_internal_project))


def billing_context(project):
    """Whether a project's records show Percent Billable, and its preset (0 when not billable)."""
    if not is_billable_project(project):
        return {"is_billable": False, "percent_billable": "0"}
    return {
        "is_billable": True,
        "percent_billable": frappe.db.get_value("Project", project, "percent_billable") or "100",
    }


@frappe.whitelist()
def get_billing_context(project):
    """billing_context for the Timesheet Record form and the panels; needs read access to the Project."""
    frappe.has_permission("Project", "read", project, throw=True)
    return billing_context(project)
