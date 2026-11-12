import io
import re
import shutil
import subprocess

import frappe
from PIL import Image, UnidentifiedImageError
from pypdf import PdfReader
from pypdf.errors import PdfReadError

class UnsupportedFile(Exception):
	"""The attachment is not a PDF or a readable image."""


MATCH_TYPES = ("Label", "Email", "Phone", "Website", "Person", "Company", "Address")

EMAIL_RE = re.compile(r"(?i)(?<![A-Z0-9._%+\-])[A-Z0-9._%+\-]+@[A-Z0-9.\-]+\.[A-Z]{2,}(?![A-Z0-9._%+\-])")
_PHONE_GROUP_RE = re.compile(r"\+|\(\d{1,5}\)|\d+")
_WEBSITE_TLDS = "com|de|eu|org|net|io|co|uk|info|biz|ch|at|fr|nl|us|online"
WEBSITE_RE = re.compile(
	rf"(?i)(?:https?://|www\.)[^\s,;<>()]+|(?<![@\w])[a-z0-9][a-z0-9-]*\.(?:{_WEBSITE_TLDS})(?:\.[a-z]{{2}})?(?:/[^\s,;<>()]*)?"
)
STREET_RE = re.compile(
	r"(?i)str(?:\.|\b)|straße|strasse|\bstreet\b|\broad\b|\brd\.\b|\bweg\b|\bplatz\b|\ballee\b|\blane\b|\bave\.?\b|\bavenue\b|\bblvd\b"
)
POSTAL_RE = re.compile(r"\b\d{4,5}\b")
_CONTACT_WORDS_RE = re.compile(
	r"(?i)\b(?:tel|telefon|telephone|fax|e-mail|email|mail|mob|mobile|phone|web)\b\.?:?"
)
_NOISE = {
	"tel",
	"telefon",
	"telephone",
	"fax",
	"email",
	"e-mail",
	"mail",
	"mob",
	"mobile",
	"phone",
	"web",
	"www",
}


@frappe.whitelist()
def extract_values(file_url, source_labels=None, lines=None):
	"""Read an attached PDF or image and return one value per mapping line.

	`lines` is a list of {match_type, source_label, target_field}. The result is
	a list of strings in the same order. Label lines read the text after the
	source label. Email, Phone, Website, Person, Company, and Address recognize
	a value when the document has no printed label.

	`source_labels` is the older label-only call. It returns {label: value}.
	"""
	if isinstance(lines, str):
		lines = frappe.parse_json(lines)
	if isinstance(source_labels, str):
		source_labels = frappe.parse_json(source_labels)

	file_name = frappe.db.get_value("File", {"file_url": file_url}, "name")
	if not file_name:
		frappe.throw(frappe._("File not found"))

	file_doc = frappe.get_doc("File", file_name)
	file_doc.check_permission("read")

	try:
		text = text_from_file(file_doc.get_content(), file_doc.file_name)
	except UnsupportedFile as exc:
		frappe.throw(frappe._(str(exc)))
	except PdfReadError:
		frappe.throw(frappe._("This file is not a readable PDF"))

	if lines:
		return values_for_lines(text, lines)
	return labels_from_text(text, source_labels or [])


def values_from_file(content, source_labels, file_name=""):
	"""Read a PDF with pypdf, or an image with Pillow and Tesseract."""
	return labels_from_text(text_from_file(content, file_name), source_labels)


def values_from_pdf(content, source_labels):
	"""Map each source label to the text that follows it in a PDF."""
	return labels_from_text(text_from_pdf(content), source_labels)


def labels_from_text(text, source_labels):
	return {label: value_after_label(text, label) for label in (source_labels or [])}


def values_for_lines(text, lines):
	"""Return one extracted string per mapping line, in the same order."""
	rows = [_normalize_line(row) for row in (lines or [])]
	text = text or ""
	emails = _unique(match.group(0) for match in EMAIL_RE.finditer(text))
	phones = _find_phones(text)
	websites = _find_websites(text)
	leftovers, addresses = _leftovers_and_addresses(text, phones)

	person_count = sum(1 for row in rows if row["match_type"] == "Person")
	company_count = sum(1 for row in rows if row["match_type"] == "Company")
	persons = leftovers[:person_count]
	companies = leftovers[person_count:person_count + company_count]
	address_value = ", ".join(addresses)

	email_index = phone_index = website_index = 0
	person_index = company_index = 0
	address_used = False
	values = []
	for row in rows:
		kind = row["match_type"]
		if kind == "Label":
			values.append(value_after_label(text, row["source_label"]))
		elif kind == "Email":
			values.append(_take(emails, email_index))
			email_index += 1
		elif kind == "Phone":
			values.append(_take(phones, phone_index))
			phone_index += 1
		elif kind == "Website":
			values.append(_take(websites, website_index))
			website_index += 1
		elif kind == "Person":
			values.append(_take(persons, person_index))
			person_index += 1
		elif kind == "Company":
			values.append(_take(companies, company_index))
			company_index += 1
		elif kind == "Address":
			values.append("" if address_used else address_value)
			address_used = True
		else:
			values.append("")
	return values


def _normalize_line(row):
	if isinstance(row, str):
		return {"match_type": "Label", "source_label": row, "target_field": ""}
	row = row or {}
	match_type = (row.get("match_type") or "Label").strip().title()
	if match_type not in MATCH_TYPES:
		match_type = "Label"
	return {
		"match_type": match_type,
		"source_label": row.get("source_label") or "",
		"target_field": row.get("target_field") or "",
	}


def _take(items, index):
	return items[index] if index < len(items) else ""


def _unique(items):
	seen = set()
	result = []
	for item in items:
		key = item.lower()
		if key in seen:
			continue
		seen.add(key)
		result.append(item)
	return result


def _unique_phones(items):
	seen = set()
	result = []
	for item in items:
		key = re.sub(r"\D", "", item)
		if not key or key in seen:
			continue
		seen.add(key)
		result.append(item)
	return result


def _find_phones(text):
	found = []
	for line in (text or "").splitlines():
		groups = list(_PHONE_GROUP_RE.finditer(line))
		index = 0
		while index < len(groups):
			phone, index = _consume_phone(line, groups, index)
			if phone:
				found.append(phone)
	return _unique_phones(found)


def _consume_phone(line, groups, index):
	"""Read one phone starting at this digit group, without swallowing the next number."""
	end = index
	for nxt in range(index, len(groups)):
		if nxt > index:
			gap = line[groups[nxt - 1].end():groups[nxt].start()]
			if not re.fullmatch(r"[ \t./()\-]{0,3}", gap):
				break
		token = line[groups[index].start():groups[nxt].end()]
		digits = re.sub(r"\D", "", token)
		if len(digits) > 15:
			break
		end = nxt
		if not _is_phone(token) or nxt + 1 >= len(groups):
			continue
		next_gap = line[groups[nxt].end():groups[nxt + 1].start()]
		next_digits = re.sub(r"\D", "", groups[nxt + 1].group(0))
		if re.fullmatch(r" ", next_gap) and len(digits) >= 7 and len(next_digits) >= 3:
			break
	token = _phone_token(line[groups[index].start():groups[end].end()])
	if _is_phone(token):
		return token, end + 1
	return None, index + 1


def _phone_token(token):
	return re.sub(r"\s+", " ", token.strip())


def _is_phone(token):
	compact = _phone_token(token)
	if re.fullmatch(r"\d{1,2}[./-]\d{1,2}[./-]\d{2,4}", compact):
		return False
	digits = re.sub(r"\D", "", compact)
	if not 7 <= len(digits) <= 15:
		return False
	if compact.startswith("+") or compact.startswith("00"):
		return True
	if re.search(r"[\s()/\-.]", compact):
		return True
	return bool(re.fullmatch(r"0\d{7,14}", compact))


def _find_websites(text):
	without_emails = EMAIL_RE.sub(" ", text or "")
	found = []
	for match in WEBSITE_RE.finditer(without_emails):
		token = match.group(0).strip().strip(".,;:)")
		if token:
			found.append(token)
	return _unique(found)


def _leftovers_and_addresses(text, phones):
	leftovers = []
	addresses = []
	for raw in (text or "").splitlines():
		# A colon marks a printed label. Those values are read by Label lines.
		if ":" in raw:
			continue
		cleaned = _strip_contacts(raw, phones)
		if not cleaned or cleaned.lower() in _NOISE:
			continue
		identity, address = _split_identity_and_address(cleaned)
		if address:
			addresses.append(address)
		for part in re.split(r"\s{2,}", identity):
			part = part.strip(" ,;|-")
			if part and part.lower() not in _NOISE:
				leftovers.append(part)
	return leftovers, addresses


def _strip_contacts(line, phones):
	line = EMAIL_RE.sub(" ", line or "")
	for phone in sorted(phones or [], key=len, reverse=True):
		line = line.replace(phone, " ")
	line = WEBSITE_RE.sub(" ", line)
	line = _CONTACT_WORDS_RE.sub(" ", line)
	return re.sub(r"\s+", " ", line).strip(" ,;|:-")


def _split_identity_and_address(cleaned):
	start = _address_start(cleaned)
	if start is None:
		return cleaned, ""
	identity = cleaned[:start].strip(" ,;|-")
	address = cleaned[start:].strip(" ,;|-")
	if not address:
		return cleaned, ""
	return identity, address


def _address_start(cleaned):
	starts = []
	for pattern in (STREET_RE, POSTAL_RE):
		match = pattern.search(cleaned)
		if not match:
			continue
		word_start = cleaned.rfind(" ", 0, match.start())
		starts.append(0 if word_start < 0 else word_start + 1)
	if not starts:
		return None
	return min(starts)


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
	from phamos.phamos.doctype.pdf_party_rule.pdf_party_rule import get_party_rules

	return get_party_rules(party_doctype, party, pdf_mapping)


@frappe.whitelist()
def save_party_rules(party_doctype, party, pdf_mapping, rules):
	"""Store learned source labels on PDF Party Rule. Does not write Supplier PDF Rule."""
	from phamos.phamos.doctype.pdf_party_rule.pdf_party_rule import replace_party_rules

	if isinstance(rules, str):
		rules = frappe.parse_json(rules)
	return replace_party_rules(party_doctype, party, pdf_mapping, rules or [])
