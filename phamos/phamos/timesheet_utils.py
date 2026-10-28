import frappe
from frappe.utils import cint, cstr, flt

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


def value_add_in_billing():
    """Phamos Settings switch: does Value Add reduce billable hours? On unless switched off (#1746)."""
    value = frappe.db.get_single_value("Phamos Settings", "value_add_in_billing")
    return True if value is None else bool(cint(value))


def compute_billable_hours(actual_time, percent_billable, value_add):
    """Billable hours of a record: actual time × Percent Billable, × Value Add when the switch is on (#1746).

    `actual_time` is in seconds, the two ratings in percent (0–100, as strings or numbers).
    """
    hours = flt(actual_time) / 3600 * flt(percent_billable) / 100
    if value_add_in_billing():
        hours *= flt(value_add if value_add not in (None, "") else 100) / 100
    return hours


def billable_seconds_term(table):
    """Query-builder term for billable seconds: the stored Billable Hours of submitted records, a live
    estimate (same formula, current switch) for drafts, which have nothing stored yet (#1746)."""
    from frappe.query_builder import Case

    live = table.actual_time * table.percent_billable / 100
    if value_add_in_billing():
        live = live * table.value_add / 100
    return Case().when(table.docstatus == 1, table.billable_hours * 3600).else_(live)


def billable_seconds_sql(alias):
    """billable_seconds_term for raw SQL, `alias` being the Timesheet Record table alias."""
    live = f"{alias}.actual_time * {alias}.percent_billable / 100"
    if value_add_in_billing():
        live += f" * {alias}.value_add / 100"
    return f"CASE WHEN {alias}.docstatus = 1 THEN {alias}.billable_hours * 3600 ELSE {live} END"
