"""PDF OCR pipeline for Lead Data Import."""

import base64
import os

import frappe
import requests
from frappe import _

from phamos.phamos.doctype.accounting_receipt.mistral_pdf import _get_phamos_settings


def extract(lead_data_import_name, file_url):
    """OCR an uploaded PDF and extract company candidates from its text."""
    from .. import lead_data_import as core

    if not file_url:
        frappe.throw(_("Please upload a PDF file."))

    core._log(lead_data_import_name, "Running OCR on PDF via Mistral...")
    settings = _get_phamos_settings()
    if not settings:
        frappe.throw(_("Mistral API key is not configured in phamos Settings."))

    path = core._get_file_path_from_url(file_url)
    if not path or not os.path.isfile(path):
        core._log(lead_data_import_name, "PDF file not found on disk.")
        return []

    with open(path, "rb") as pdf_file:
        pdf_b64 = base64.b64encode(pdf_file.read()).decode("utf-8")

    ocr_url = f"{settings['base_url'].rstrip('/')}/ocr"
    headers = {
        "Authorization": f"Bearer {settings['api_key']}",
        "Content-Type": "application/json",
    }
    payload = {
        "model": "mistral-ocr-latest",
        "document": {
            "type": "document_url",
            "document_url": f"data:application/pdf;base64,{pdf_b64}",
        },
    }
    response = requests.post(ocr_url, json=payload, headers=headers, timeout=120)
    if not response.ok:
        core._log(lead_data_import_name, f"OCR failed: {response.status_code}")
        return []

    markdown = "\n\n".join(
        page.get("markdown", "") for page in response.json().get("pages", [])
    )
    if not markdown.strip():
        core._log(lead_data_import_name, "OCR returned empty text.")
        return []

    companies = core._mistral_extract_companies_from_text(markdown)
    core._log(
        lead_data_import_name,
        f"Mistral identified {len(companies)} companies in the PDF.",
    )
    if core.MAX_COMPANIES_PER_IMPORT:
        return companies[:core.MAX_COMPANIES_PER_IMPORT]
    return companies

