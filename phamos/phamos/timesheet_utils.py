import frappe
from frappe.utils import cstr

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


def billing_context(project):
    """Preset for Percent Billable: the Project's own value, 100 when it has none.

    Percent Billable is set on every project, internal ones included, because external people
    may bill there too (#1031, revised decision 2).
    """
    preset = frappe.db.get_value("Project", project, "percent_billable") if project else None
    return {"percent_billable": preset or "100"}


@frappe.whitelist()
def get_billing_context(project):
    """billing_context for the Timesheet Record form and the panels; needs read access to the Project."""
    frappe.has_permission("Project", "read", project, throw=True)
    return billing_context(project)
