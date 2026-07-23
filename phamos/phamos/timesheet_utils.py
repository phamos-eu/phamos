from frappe.utils import cstr


def normalize_percent_billable(value):
    """Return percent billable as canonical Select value (e.g. "0")."""
    try:
        percent = float(value or 0)
    except (TypeError, ValueError):
        percent = 0.0

    if percent <= 0:
        return "0"

    return cstr(value).strip()
