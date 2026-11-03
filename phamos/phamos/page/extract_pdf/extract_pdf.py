import io
import re
import shutil
import subprocess

import frappe
from PIL import Image, UnidentifiedImageError
from pypdf import PdfReader
from pypdf.errors import PdfReadError

from phamos.phamos.doctype.pdf_party_rule.pdf_party_rule import get_party_rules, replace_party_rules


class UnsupportedFile(Exception):
	"""The attachment is not a PDF or a readable image."""


@frappe.whitelist()
def extract_values(file_url, source_labels):
	"""Return the text found after each source label in the attached PDF or image."""
	if isinstance(source_labels, str):
		source_labels = frappe.parse_json(source_labels)
	source_labels = source_labels or []

	file_name = frappe.db.get_value("File", {"file_url": file_url}, "name")
	if not file_name:
		frappe.throw(frappe._("File not found"))

	file_doc = frappe.get_doc("File", file_name)
	file_doc.check_permission("read")

	try:
		return values_from_file(file_doc.get_content(), source_labels, file_doc.file_name)
	except UnsupportedFile as exc:
		frappe.throw(frappe._(str(exc)))
	except PdfReadError:
		frappe.throw(frappe._("This file is not a readable PDF"))


def values_from_file(content, source_labels, file_name=""):
	"""Read a PDF with pypdf, or an image with Pillow and Tesseract."""
	return labels_from_text(text_from_file(content, file_name), source_labels)


def values_from_pdf(content, source_labels):
	"""Map each source label to the text that follows it in a PDF."""
	return labels_from_text(text_from_pdf(content), source_labels)


def labels_from_text(text, source_labels):
	return {label: value_after_label(text, label) for label in (source_labels or [])}


def text_from_file(content, file_name=""):
	content = content or b""
	if content.startswith(b"%PDF") or _extension(file_name) == ".pdf":
		return text_from_pdf(content)
	if _is_image(content):
		return text_from_image(content)
	raise UnsupportedFile("Attach a PDF or an image")


def text_from_pdf(content):
	reader = PdfReader(io.BytesIO(content))
	return "\n".join((page.extract_text() or "") for page in reader.pages)


def text_from_image(content):
	if not shutil.which("tesseract"):
		raise UnsupportedFile("Tesseract is not installed, so image text cannot be read")
	result = subprocess.run(
		["tesseract", "stdin", "stdout"],
		input=content,
		capture_output=True,
		check=False,
	)
	if result.returncode != 0:
		raise UnsupportedFile("Image text could not be read")
	return result.stdout.decode("utf-8", errors="replace")


def _is_image(content):
	try:
		with Image.open(io.BytesIO(content)) as image:
			image.verify()
		return True
	except (UnidentifiedImageError, OSError):
		return False


def _extension(file_name):
	name = (file_name or "").lower()
	dot = name.rfind(".")
	return name[dot:] if dot >= 0 else ""


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


@frappe.whitelist()
def party_rules(party_doctype, party, pdf_mapping):
	"""Learned source labels for the mapping's primary key. Does not read Supplier PDF Rule."""
	return get_party_rules(party_doctype, party, pdf_mapping)


@frappe.whitelist()
def save_party_rules(party_doctype, party, pdf_mapping, rules):
	"""Store learned source labels on PDF Party Rule. Does not write Supplier PDF Rule."""
	if isinstance(rules, str):
		rules = frappe.parse_json(rules)
	return replace_party_rules(party_doctype, party, pdf_mapping, rules or [])
