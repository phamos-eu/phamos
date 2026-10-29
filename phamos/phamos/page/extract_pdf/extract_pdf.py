import io
import re

import frappe
from pypdf import PdfReader


@frappe.whitelist()
def extract_values(file_url, source_labels):
	"""Return the text found after each source label in the attached PDF."""
	if isinstance(source_labels, str):
		source_labels = frappe.parse_json(source_labels)
	source_labels = source_labels or []

	file_name = frappe.db.get_value("File", {"file_url": file_url}, "name")
	if not file_name:
		frappe.throw(frappe._("File not found"))

	file_doc = frappe.get_doc("File", file_name)
	file_doc.check_permission("read")

	reader = PdfReader(io.BytesIO(file_doc.get_content()))
	text = "\n".join((page.extract_text() or "") for page in reader.pages)

	return {label: value_after_label(text, label) for label in source_labels}


def value_after_label(text, label):
	label = (label or "").strip()
	if not label or not text:
		return ""

	pattern = re.compile(
		r"(?i)(?<!\w)" + re.escape(label) + r"(?!\w)\s*[:.]?\s*([^\n]+)"
	)
	match = pattern.search(text)
	if not match:
		return ""

	value = re.split(r"\s{2,}", match.group(1).strip(), maxsplit=1)[0]
	return value.strip(" :.")
