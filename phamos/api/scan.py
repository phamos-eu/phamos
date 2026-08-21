# Copyright (c) 2026, phamos.eu and contributors
# For license information, please see license.txt

"""Mobile Lead Scan API: create Lead Data Import from a card scan and poll status."""

from __future__ import annotations

import base64
import io
import re
from mimetypes import guess_type

import frappe
from frappe import _
from frappe.utils import cint, get_fullname

LEAD_DATA_IMPORT = "Lead Data Import"
LEAD_DATA = "Lead Data"

IMAGE_EXTENSIONS = (".png", ".jpg", ".jpeg", ".webp", ".gif", ".heic", ".heif")
PDF_EXTENSIONS = (".pdf",)


def check_app_permission():
	"""Show Lead Scan on the Apps screen for users who can create Lead Data Import."""
	if frappe.session.user in (None, "Guest"):
		return False
	if frappe.session.user == "Administrator":
		return True

	user_type = frappe.get_cached_value("User", frappe.session.user, "user_type")
	if user_type == "Website User":
		return False

	return frappe.has_permission(LEAD_DATA_IMPORT, ptype="create")


def _require_scan_access():
	if not check_app_permission():
		frappe.throw(_("You do not have permission to use Lead Scan"), frappe.PermissionError)
	frappe.has_permission(LEAD_DATA_IMPORT, ptype="create", throw=True)


def _detect_input_type(filename: str, content_type: str | None) -> str:
	name = (filename or "").lower()
	ctype = (content_type or "").lower()
	if ctype == "application/pdf" or any(name.endswith(ext) for ext in PDF_EXTENSIONS):
		return "PDF"
	if ctype.startswith("image/") or any(name.endswith(ext) for ext in IMAGE_EXTENSIONS):
		return "Screenshot"
	frappe.throw(_("Please upload a PDF or image of the business card."))


def _display_name(row) -> str:
	parts = [
		(row.get("salutation") or "").strip(),
		(row.get("first_name") or "").strip(),
		(row.get("middle_name") or "").strip(),
		(row.get("last_name") or "").strip(),
	]
	name = " ".join(p for p in parts if p)
	if name:
		return name
	return (row.get("organization_name") or "").strip() or _("Unknown contact")


def _serialize_lead(row) -> dict:
	# Prefer the full ranked email string (may be comma-separated); fall back to card stamp.
	email = (row.get("email") or row.get("card_email") or "").strip()
	mobile = (row.get("mobile_no") or "").strip()
	landline = (row.get("phone") or "").strip()
	# Primary dial target: mobile over landline.
	phone = mobile or landline
	return {
		"name": row.get("name"),
		"display_name": _display_name(row),
		"first_name": row.get("first_name") or "",
		"last_name": row.get("last_name") or "",
		"job_title": row.get("job_title") or "",
		"organization_name": row.get("organization_name") or "",
		"email": email,
		"phone": phone,
		"mobile_no": mobile,
		"phone_no": landline,
		"website": row.get("website") or "",
		"city": row.get("city") or "",
		"country": row.get("country") or "",
	}


def _serialize_child_contact(row) -> dict:
	parts = [
		(row.get("salutation") or "").strip(),
		(row.get("first_name") or "").strip(),
		(row.get("middle_name") or "").strip(),
		(row.get("last_name") or "").strip(),
	]
	display = " ".join(p for p in parts if p)
	mobile = (row.get("mobile_no") or "").strip()
	landline = (row.get("phone") or "").strip()
	return {
		"first_name": row.get("first_name") or "",
		"last_name": row.get("last_name") or "",
		"salutation": row.get("salutation") or "",
		"display_name": display,
		"email": (row.get("email_address") or "").strip(),
		"phone": mobile or landline,
		"mobile_no": mobile,
		"phone_no": landline,
		"designation": row.get("designation") or "",
		"is_primary": int(row.get("is_primary") or 0),
	}


def _compose_address_display(parts: dict) -> str:
	street = (parts.get("address_line_1") or "").strip()
	postal = (parts.get("postal_code") or "").strip()
	city = (parts.get("city") or parts.get("citytown") or "").strip()
	country = (parts.get("country") or "").strip()
	locality = " ".join(p for p in (postal, city) if p)
	chunks = [c for c in (street, locality, country) if c]
	return ", ".join(chunks)


def _primary_address_for_lead(lead_name: str) -> dict:
	rows = frappe.get_all(
		"Lead Data Address",
		filters={"parent": lead_name, "parenttype": LEAD_DATA},
		fields=[
			"address_line_1",
			"address_line_2",
			"citytown",
			"postal_code",
			"country",
			"stateprovince",
		],
		order_by="idx asc",
		limit_page_length=1,
	)
	if not rows:
		return {
			"address_line_1": "",
			"postal_code": "",
			"city": "",
			"country": "",
			"address_display": "",
		}
	row = rows[0]
	city = (row.get("citytown") or "").strip()
	payload = {
		"address_line_1": (row.get("address_line_1") or "").strip(),
		"postal_code": (row.get("postal_code") or "").strip(),
		"city": city,
		"country": (row.get("country") or "").strip(),
	}
	payload["address_display"] = _compose_address_display(
		{
			**payload,
			"citytown": city,
		}
	)
	return payload


def _secondary_contacts_for_lead(lead_name: str) -> list:
	child_contacts = frappe.get_all(
		"Lead Data Contact",
		filters={"parent": lead_name, "parenttype": LEAD_DATA},
		fields=[
			"first_name",
			"middle_name",
			"last_name",
			"salutation",
			"email_address",
			"phone",
			"mobile_no",
			"designation",
			"is_primary",
		],
		order_by="idx asc",
	)
	return [
		_serialize_child_contact(c)
		for c in child_contacts
		if not int(c.get("is_primary") or 0)
	]


def _preview_file_for_import(import_name: str) -> str:
	if not import_name or not frappe.db.exists(LEAD_DATA_IMPORT, import_name):
		return ""
	doc = frappe.get_doc(LEAD_DATA_IMPORT, import_name)
	preview = doc.upload_file or ""
	if not preview and doc.input_type == "Screenshot":
		for row in doc.upload_files or []:
			if row.lead_data_attachment:
				preview = row.lead_data_attachment
				break
	return preview


def _enrich_lead_payload(contact: dict, lead_name: str, include_secondaries: bool = True) -> dict:
	address = _primary_address_for_lead(lead_name)
	contact.update(address)
	if not contact.get("city") and address.get("city"):
		contact["city"] = address["city"]
	if not contact.get("country") and address.get("country"):
		contact["country"] = address["country"]
	if include_secondaries:
		contact["secondary_contacts"] = _secondary_contacts_for_lead(lead_name)
	return contact


def _serialize_import(doc_or_row, include_log: bool = False) -> dict:
	data = {
		"name": doc_or_row.get("name"),
		"status": doc_or_row.get("status") or "Draft",
		"input_type": doc_or_row.get("input_type"),
		"upload_file": doc_or_row.get("upload_file") or "",
		"modified": str(doc_or_row.get("modified") or ""),
		"creation": str(doc_or_row.get("creation") or ""),
		"owner": doc_or_row.get("owner"),
		"owner_name": get_fullname(doc_or_row.get("owner")) if doc_or_row.get("owner") else "",
	}
	if include_log:
		data["status_log"] = doc_or_row.get("status_log") or ""
	return data


def _save_uploaded_file(content_b64: str, filename: str, dt: str, dn: str, fieldname: str):
	from frappe.handler import ALLOWED_MIMETYPES

	raw = content_b64
	if "," in raw and raw.strip().startswith("data:"):
		raw = raw.split(",", 1)[1]

	try:
		decoded = base64.b64decode(raw)
	except Exception:
		frappe.throw(_("Invalid file content."))

	content_type = guess_type(filename)[0]
	if not content_type:
		# iOS Scan Documents often yields application/pdf without extension quirks
		if filename.lower().endswith(".pdf"):
			content_type = "application/pdf"
		elif any(filename.lower().endswith(ext) for ext in IMAGE_EXTENSIONS):
			content_type = "image/jpeg"

	if content_type and content_type not in ALLOWED_MIMETYPES:
		# Allow HEIC from iPhone camera roll if present as octet-stream renamed
		if not (
			content_type.startswith("image/")
			or content_type == "application/pdf"
			or content_type == "application/octet-stream"
		):
			frappe.throw(_("You can only upload PDF or image files."))

	file_content = decoded
	if content_type and content_type.startswith("image/jpeg"):
		try:
			from PIL import Image, ImageOps

			with Image.open(io.BytesIO(decoded)) as image:
				transpose_img = ImageOps.exif_transpose(image)
				buf = io.BytesIO()
				transpose_img.save(buf, format="JPEG")
				file_content = buf.getvalue()
		except Exception:
			file_content = decoded

	file_doc = frappe.get_doc(
		{
			"doctype": "File",
			"attached_to_doctype": dt,
			"attached_to_name": dn,
			"attached_to_field": fieldname,
			"folder": "Home",
			"file_name": filename,
			"content": file_content,
			"is_private": 1,
		}
	).insert(ignore_permissions=False)

	return file_doc, content_type


@frappe.whitelist()
def create_scan(filename: str, content: str):
	"""Upload a scanned card (PDF/image) and create a Lead Data Import that auto-extracts."""
	_require_scan_access()

	if not filename or not content:
		frappe.throw(_("Filename and file content are required."))

	# Sanitize filename
	safe_name = re.sub(r"[^\w.\-]+", "_", filename.strip())[:140] or "scan.pdf"
	content_type = guess_type(safe_name)[0]
	input_type = _detect_input_type(safe_name, content_type)

	doc = frappe.get_doc(
		{
			"doctype": LEAD_DATA_IMPORT,
			"input_type": input_type,
			"status": "Draft",
		}
	)
	doc.insert()

	fieldname = "upload_file"
	file_doc, _ctype = _save_uploaded_file(
		content, safe_name, LEAD_DATA_IMPORT, doc.name, fieldname
	)

	doc.reload()
	if input_type == "PDF":
		doc.upload_file = file_doc.file_url
	else:
		# Screenshot pipeline expects the multi-image child table
		already = any(
			(row.lead_data_attachment or "") == file_doc.file_url
			for row in (doc.upload_files or [])
		)
		if not already:
			doc.append("upload_files", {"lead_data_attachment": file_doc.file_url})
		# Keep upload_file empty for screenshots (desk UI clears it after adding to table)
		doc.upload_file = ""

	doc.save()
	doc.reload()

	return {
		"ok": True,
		"name": doc.name,
		"status": doc.status,
		"input_type": doc.input_type,
		"file_url": file_doc.file_url,
	}


@frappe.whitelist()
def list_scans(limit: int = 30):
	"""Recent Lead Data Imports created by the current user."""
	_require_scan_access()
	limit = min(max(cint(limit) or 30, 1), 100)
	user = frappe.session.user

	rows = frappe.get_all(
		LEAD_DATA_IMPORT,
		filters={"owner": user},
		fields=[
			"name",
			"status",
			"input_type",
			"upload_file",
			"modified",
			"creation",
			"owner",
		],
		order_by="modified desc",
		limit_page_length=limit,
	)

	# Prefer first card image from child table when upload_file is empty (screenshots)
	result = []
	for row in rows:
		item = _serialize_import(row)
		if not item["upload_file"] and row.input_type == "Screenshot":
			attachments = frappe.get_all(
				"Lead Data Attachment",
				filters={"parent": row.name, "parenttype": LEAD_DATA_IMPORT},
				fields=["lead_data_attachment"],
				order_by="idx asc",
				limit_page_length=1,
			)
			if attachments and attachments[0].lead_data_attachment:
				item["upload_file"] = attachments[0].lead_data_attachment
		# Contact count
		item["contact_count"] = frappe.db.count(
			LEAD_DATA, {"lead_data_import": row.name}
		)
		result.append(item)

	return result


@frappe.whitelist()
def get_scan(name: str):
	"""Lead Data Import status, log, and related Lead Data contacts."""
	_require_scan_access()
	if not name:
		frappe.throw(_("Scan name is required."))

	if not frappe.db.exists(LEAD_DATA_IMPORT, name):
		frappe.throw(_("Scan not found."), frappe.DoesNotExistError)

	frappe.has_permission(LEAD_DATA_IMPORT, doc=name, ptype="read", throw=True)

	doc = frappe.get_doc(LEAD_DATA_IMPORT, name)
	preview = _preview_file_for_import(name)

	leads = frappe.get_all(
		LEAD_DATA,
		filters={"lead_data_import": name},
		fields=[
			"name",
			"salutation",
			"first_name",
			"middle_name",
			"last_name",
			"job_title",
			"organization_name",
			"email",
			"card_email",
			"mobile_no",
			"phone",
			"website",
			"city",
			"country",
		],
		order_by="creation asc",
	)

	contacts = []
	for row in leads:
		contact = _serialize_lead(row)
		_enrich_lead_payload(contact, row.get("name"), include_secondaries=True)
		contacts.append(contact)

	payload = _serialize_import(doc.as_dict(), include_log=True)
	payload["upload_file"] = preview
	payload["contacts"] = contacts
	payload["contact_count"] = len(contacts)
	return payload


@frappe.whitelist()
def get_contact(name: str):
	"""Single Lead Data row for the contact detail screen."""
	_require_scan_access()
	if not name or not frappe.db.exists(LEAD_DATA, name):
		frappe.throw(_("Contact not found."), frappe.DoesNotExistError)

	frappe.has_permission(LEAD_DATA, doc=name, ptype="read", throw=True)
	row = frappe.db.get_value(
		LEAD_DATA,
		name,
		[
			"name",
			"lead_data_import",
			"salutation",
			"first_name",
			"middle_name",
			"last_name",
			"job_title",
			"organization_name",
			"email",
			"card_email",
			"mobile_no",
			"phone",
			"website",
			"city",
			"country",
		],
		as_dict=True,
	)
	contact = _serialize_lead(row)
	contact["lead_data_import"] = row.get("lead_data_import")
	_enrich_lead_payload(contact, name, include_secondaries=False)
	contact["upload_file"] = _preview_file_for_import(row.get("lead_data_import"))
	return contact
