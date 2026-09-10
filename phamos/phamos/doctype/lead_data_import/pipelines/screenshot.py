"""Screenshot preview and extraction pipeline for Lead Data Import."""

import json
import re

import frappe
from frappe import _
from frappe.utils import cint


def preview(lead_data_import_name):
    """Extract screenshot leads without saving them."""
    from .. import lead_data_import as core

    core._ensure_lead_data_import_schema()
    doc = frappe.get_doc(core.LEAD_DATA_IMPORT_DOCTYPE, lead_data_import_name)
    if doc.status == "Processing":
        frappe.throw(_("Extraction is already running for this document."))
    file_urls = core._screenshot_file_urls(doc)
    if doc.input_type != "Screenshot" and not re.search(
        r"\.(?:png|jpe?g|webp)$", doc.upload_file or "", flags=re.I
    ):
        frappe.throw(_("Preview is only available for Screenshot input."))
    if not file_urls:
        frappe.throw(_("Please upload a screenshot file."))

    companies = extract(lead_data_import_name, file_urls)
    companies = [core._normalize_company_dict(company) for company in companies or []]
    return {
        "ok": True,
        "image_url": file_urls[0],
        "image_urls": file_urls,
        "leads": [_preview_company_payload(company) for company in companies],
        "lead_data_text": "\n\n---\n\n".join(
            core._build_import_info(company) for company in companies
        ),
    }


def create_from_preview(lead_data_import_name, leads_json, replace_existing=True):
    """Persist the screenshot leads accepted by the user."""
    from .. import lead_data_import as core

    core._ensure_lead_data_import_schema()
    doc = frappe.get_doc(core.LEAD_DATA_IMPORT_DOCTYPE, lead_data_import_name)
    if doc.status == "Processing":
        frappe.throw(_("Extraction is already running for this document."))

    companies = _companies_from_preview_payload(leads_json)
    if not companies:
        frappe.throw(_("No lead data found in preview."))

    if cint(replace_existing):
        frappe.db.delete(
            core.LEAD_DATA_DOCTYPE,
            {core.LEAD_DATA_IMPORT_FIELD: lead_data_import_name},
        )

    for company in companies:
        core._save_single_company(lead_data_import_name, company)

    frappe.db.set_value(
        core.LEAD_DATA_IMPORT_DOCTYPE,
        lead_data_import_name,
        {
            "status": "Ready",
            "status_log": f"Created {len(companies)} lead(s) from accepted screenshot preview.",
        },
    )
    frappe.db.commit()
    return {"ok": True, "message": f"Created {len(companies)} lead(s)."}


def extract(lead_data_import_name, file_url):
    """Extract leads from one image or multiple images of the same card."""
    from .. import lead_data_import as core

    file_urls = file_url if isinstance(file_url, (list, tuple)) else [file_url]
    file_urls = [url for url in file_urls if url]
    if not file_urls:
        frappe.throw(_("Please upload a screenshot file."))

    core._log(
        lead_data_import_name,
        f"Reading {len(file_urls)} screenshot/business-card image(s) via Mistral vision...",
    )
    images = []
    for url in file_urls:
        image_b64, mime = core._load_file_as_base64(url)
        if image_b64:
            images.append((image_b64, mime))
        crop_b64, crop_mime = core._load_card_crop_as_base64(url)
        if crop_b64:
            images.append((crop_b64, crop_mime))
    if not images:
        core._log(lead_data_import_name, "Could not read uploaded image files.")
        return []

    qr_urls = []
    for url in file_urls:
        for qr_url in core._decode_qr_urls_from_file(url):
            if qr_url not in qr_urls:
                qr_urls.append(qr_url)
    if qr_urls:
        core._log(lead_data_import_name, f"QR website found: {qr_urls[0]}")

    companies = core._mistral_extract_companies_from_image(images, None, qr_urls=qr_urls)
    if not companies:
        core._log(
            lead_data_import_name,
            "No direct lead found. Trying partner/logo extraction from screenshot...",
        )
        companies = core._mistral_extract_logo_companies_from_image(images[0][0], images[0][1])

    is_logo_list = any(company.get("source_type") == "logo_list" for company in companies)
    normalized_companies = []
    for company in companies:
        if not company.get("website") and qr_urls and not is_logo_list:
            company["website"] = qr_urls[0]
        if not company.get("website"):
            company["website"] = core._infer_or_search_website(company)
        if not company.get("company_name") and company.get("website"):
            company["company_name"] = core._domain_to_company_name(company["website"])
        # Mobile /scan uploads are business cards unless this is a logo wall.
        if not is_logo_list and "logo_list" not in str(company.get("source_type") or "").lower():
            company["source_type"] = "business_card"
        company = core._normalize_company_dict(
            core._prioritize_business_card_emails(company)
        )
        company["source_attachments"] = file_urls
        company["source_attachment"] = file_urls[0]
        normalized_companies.append(company)

    core._log(
        lead_data_import_name,
        f"Mistral identified {len(normalized_companies)} lead(s) in the screenshot.",
    )
    if core.MAX_COMPANIES_PER_IMPORT:
        return normalized_companies[:core.MAX_COMPANIES_PER_IMPORT]
    return normalized_companies


def _preview_company_payload(company):
    from .. import lead_data_import as core

    company = core._normalize_company_dict(company)
    return {
        "company_name": company.get("company_name") or "",
        "website": company.get("website") or "",
        "emails": company.get("emails") or [],
        "phones": company.get("phones") or [],
        "mobile_numbers": company.get("mobile_numbers") or [],
        "contact_persons": company.get("contact_persons") or [],
        "addresses": company.get("addresses") or [],
        "job_title": company.get("job_title") or "",
        "source_attachment": company.get("source_attachment") or "",
    }


def _companies_from_preview_payload(leads_json):
    from .. import lead_data_import as core

    try:
        data = json.loads(leads_json) if isinstance(leads_json, str) else leads_json
    except Exception:
        frappe.throw(_("Preview data is not valid JSON."))

    if isinstance(data, dict):
        data = [data]
    if not isinstance(data, list):
        frappe.throw(_("Preview data must be a JSON array."))

    companies = []
    for item in data:
        if not isinstance(item, dict):
            continue
        company = core._normalize_company_dict(item)
        if company.get("company_name") or company.get("website") or company.get("email"):
            companies.append(company)
    return companies
