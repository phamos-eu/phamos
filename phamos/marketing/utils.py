"""Small helpers shared by the Marketing services (no imports of other Marketing modules)."""

import re

import frappe
from frappe import _

# Full-string match: Frappe's character set, anchored, so trailing garbage such as a slash is rejected
# instead of being silently cut off.
_STRICT_EMAIL_RE = re.compile(
	r"^[a-z0-9][a-z0-9!#$%&'*+/=?^_`{|}~-]*(?:\.[a-z0-9!#$%&'*+/=?^_`{|}~-]+)*"
	r"@(?:[a-z0-9](?:[a-z0-9-]*[a-z0-9])?\.)+[a-z0-9](?:[a-z0-9-]*[a-z0-9])?$",
	re.IGNORECASE,
)


def normalize_email(value, throw=True):
	"""The bare, lower-case address, or "" (or an error) when it is not a valid single address."""
	raw = (value or "").strip()
	parsed = frappe.utils.validate_email_address(raw) if raw else ""
	cleaned = (parsed or "").split(",")[0].strip().lower()
	if cleaned and _STRICT_EMAIL_RE.match(cleaned):
		return cleaned
	if throw:
		frappe.throw(_("Please enter a valid email address: {0}").format(frappe.utils.escape_html(raw)))
	return ""


def split_name(full_name):
	"""("Anna Maria", "Schmidt") from "Anna Maria Schmidt": the last word is the last name."""
	parts = (full_name or "").split()
	if len(parts) < 2:
		return (parts[0] if parts else "", "")
	return " ".join(parts[:-1]), parts[-1]


def join_name(*parts):
	return " ".join(p.strip() for p in parts if p and p.strip())
