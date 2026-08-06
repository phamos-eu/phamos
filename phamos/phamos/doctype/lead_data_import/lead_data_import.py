# Copyright (c) 2026, phamos.eu and contributors
# Lead Import: scrape partner directories and extract lead data via Mistral AI.

import base64
import html as html_lib
import json
import os
import re
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from urllib.parse import parse_qs, quote_plus, unquote, urljoin, urlparse

import frappe
import requests
from frappe import _
from frappe.model.document import Document
from frappe.utils import cint, get_files_path, validate_email_address

from phamos.phamos.doctype.accounting_receipt.mistral_pdf import _get_phamos_settings

MISTRAL_CHAT_MODEL_DEFAULT = "mistral-small-latest"
SCRAPE_TIMEOUT = 6
MAX_COMPANIES_PER_IMPORT = 0
FAST_REEXTRACT_CRAWL_LIMIT = 5
ENRICHMENT_WORKERS = 6
ENRICHMENT_SLUG_LIMIT = 12
BATCH_SIZE = 50
LEAD_DATA_IMPORT_DOCTYPE = "Lead Data Import"
LEAD_DATA_DOCTYPE = "Lead Data"
LEAD_DATA_IMPORT_FIELD = "lead_data_import"
LEAD_LIST_FIELDS = ("emails", "phones", "contact_persons", "addresses")
FREE_EMAIL_DOMAINS = {
    "gmail.com", "googlemail.com", "yahoo.com", "outlook.com", "hotmail.com",
    "live.com", "icloud.com", "me.com", "aol.com", "gmx.de", "web.de",
    "proton.me", "protonmail.com",
}
TECHNICAL_EMAIL_DOMAINS = {
    "sentry.io",
    "sentry.wixpress.com",
    "sentry-next.wixpress.com",
    "wixpress.com",
}
TECHNICAL_EMAIL_LOCAL_PARTS = {
    "sentry", "noreply", "no-reply", "donotreply", "do-not-reply",
    "mailer-daemon", "postmaster", "webmaster",
}


def _ensure_lead_data_import_schema():
    if frappe.db.has_column(LEAD_DATA_DOCTYPE, LEAD_DATA_IMPORT_FIELD):
        return

    old_field = "lead_import"
    if frappe.db.has_column(LEAD_DATA_DOCTYPE, old_field):
        frappe.throw(_(
            "Lead Data table still has the old field '{0}' and is missing the renamed field '{1}'. "
            "Please run: bench --site <site-name> migrate, then bench --site <site-name> clear-cache."
        ).format(old_field, LEAD_DATA_IMPORT_FIELD))

    frappe.throw(_(
        "Lead Data table is missing field '{0}'. Please run: bench --site <site-name> migrate, "
        "then bench --site <site-name> clear-cache."
    ).format(LEAD_DATA_IMPORT_FIELD))

LEAD_FIELD_EXTRACTION_PROMPT = """Extract contact details for this company from the text.
Company: {company_name}

Return only this JSON object:
{{"emails":[],"phones":[],"contact_persons":[],"addresses":[],"website":"","job_title":""}}

Use these field-specific instructions when deciding what belongs in each field:
{field_guidance}

Use only values explicitly present in the text. Keep list fields as arrays of strings.
Phones must be real telephone/mobile numbers. Exclude fax numbers, dates, IDs,
prices, percentages, coordinates, and list numbering.
Addresses must be clean postal addresses only. Do not include VAT IDs, tax text,
commercial register text, legal paragraphs, labels, navigation text, or cookie text.
If a role/designation appears next to a contact person, put the role in job_title.
When there are multiple contact persons, keep job_title values in the same order,
separated by commas.

Text:
---
{text}
---"""


class LeadDataImport(Document):
    def on_update(self):
        self.auto_extract()

    def auto_extract(self):
        
        if self.status == "Processing":
            return

        if frappe.flags.in_import or frappe.flags.in_patch or frappe.flags.in_migrate:
            return

        if not self.can_extract():
            return

        signature = _current_source_signature(self)
        previous_signature = frappe.db.get_value(
            LEAD_DATA_IMPORT_DOCTYPE, self.name, "last_extract_signature"
        )

        if signature == (previous_signature or ""):
            return

        frappe.db.set_value(
            LEAD_DATA_IMPORT_DOCTYPE,
            self.name,
            "last_extract_signature",
            signature,
            update_modified=False,
        )

        try:
            extract_leads(self.name)
            frappe.msgprint(_("Auto-extraction started in the background."))
        except Exception:
            frappe.log_error(
                title=_("Auto-extract on save failed"),
                message=frappe.get_traceback(),
            )

    def can_extract(self):
        if self.input_type == "URL":
            return bool(self.source_url)
        elif self.input_type == "Screenshot":
            return bool(self.upload_files)
        elif self.input_type == "PDF":
            return bool(self.upload_file)
        return False


def _current_source_signature(doc):
    """A fingerprint of whatever the user currently has as input."""
    if doc.input_type == "URL":
        return f"URL::{(doc.source_url or '').strip()}"
    if doc.input_type == "PDF":
        return f"PDF::{(doc.upload_file or '').strip()}"
    if doc.input_type == "Screenshot":
        return "Screenshot::" + "|".join(sorted(_screenshot_file_urls(doc)))
    return ""



def _screenshot_file_urls(doc):
    """Return card images from the multi-file table plus the legacy upload field."""
    file_urls = []
    for row in doc.get("upload_files") or []:
        file_url = (row.get("lead_data_attachment") or "").strip()
        if file_url and file_url not in file_urls:
            file_urls.append(file_url)
    if doc.upload_file and doc.upload_file not in file_urls:
        file_urls.append(doc.upload_file)
    return file_urls


def sync_email_attachment_and_extract(lead_data_import_name):
    """Use an emailed business-card attachment as input and start extraction.

    Communication can be updated more than once while an incoming email is
    processed. An existing ``upload_file`` therefore acts as the idempotency
    guard and prevents the same attachment from starting extraction twice.
    """
    doc = frappe.get_doc(LEAD_DATA_IMPORT_DOCTYPE, lead_data_import_name)
    if doc.upload_file:
        return False

    files = frappe.get_all(
        "File",
        filters={
            "attached_to_doctype": LEAD_DATA_IMPORT_DOCTYPE,
            "attached_to_name": lead_data_import_name,
        },
        fields=["file_name", "file_url"],
        order_by="creation asc",
    )

    selected_file = None
    input_type = None
    for file_row in files:
        filename = (file_row.file_name or file_row.file_url or "").lower()
        if re.search(r"\.pdf(?:$|[?#])", filename):
            selected_file = file_row.file_url
            input_type = "PDF"
            break
        if re.search(r"\.(?:png|jpe?g|webp)(?:$|[?#])", filename):
            selected_file = file_row.file_url
            input_type = "Screenshot"
            break

    if not selected_file:
        return False

    frappe.db.set_value(
        LEAD_DATA_IMPORT_DOCTYPE,
        lead_data_import_name,
        {
            "input_type": input_type,
            "upload_file": selected_file,
        },
        update_modified=False,
    )
    extract_leads(lead_data_import_name)
    return True


def _get_lead_data_mapping_prompt():
    if not frappe.db.exists("DocType", "Lead Data Mapping"):
        return ""

    mapping = frappe.get_single("Lead Data Mapping")
    lines = []
    for row in mapping.lead_data_field_mapping or []:
        field = (row.lead_data_field or "").strip()
        conditions = (row.conditions or "").strip()
        if field and conditions:
            lines.append(f"- {field}: {conditions}")

    return "\n".join(lines)


COUNTRY_ALIASES = {
    "deutschland": "Germany",
    "germany": "Germany",
    "de": "Germany",
    "osterreich": "Austria",
    "oesterreich": "Austria",
    "austria": "Austria",
    "schweiz": "Switzerland",
    "switzerland": "Switzerland",
    "france": "France",
    "italy": "Italy",
    "spain": "Spain",
    "netherlands": "Netherlands",
    "belgium": "Belgium",
    "poland": "Poland",
    "unitedkingdom": "United Kingdom",
    "uk": "United Kingdom",
    "usa": "United States",
    "unitedstates": "United States",
}


def _parse_address_components(address):
    from .services.normalization import _parse_address_components as implementation

    return implementation(address)
def _first_address_components(addresses):
    from .services.normalization import _first_address_components as implementation

    return implementation(addresses)
def _clean_address_values(values):
    from .services.normalization import _clean_address_values as implementation

    return implementation(values)
def _address_line_for_child(address):
    from .services.normalization import _address_line_for_child as implementation

    return implementation(address)
def _street_line_from_address(address):
    from .services.normalization import _street_line_from_address as implementation

    return implementation(address)
def _normalize_address_candidate(address):
    from .services.normalization import _normalize_address_candidate as implementation

    return implementation(address)
def _trim_address_after_postal_city(text):
    from .services.normalization import _trim_address_after_postal_city as implementation

    return implementation(text)
def _repair_compact_german_address_spacing(text):
    from .services.normalization import _repair_compact_german_address_spacing as implementation

    return implementation(text)
def _compact_street_name(street):
    from .services.normalization import _compact_street_name as implementation

    return implementation(street)
def _strip_address_company_prefix(text):
    from .services.normalization import _strip_address_company_prefix as implementation

    return implementation(text)
def _looks_like_postal_address(address):
    from .services.normalization import _looks_like_postal_address as implementation

    return implementation(address)
def _append_country_from_text(address):
    from .services.normalization import _append_country_from_text as implementation

    return implementation(address)
def _address_dedupe_key(address):
    from .services.normalization import _address_dedupe_key as implementation

    return implementation(address)
def _normalize_country(value):
    from .services.normalization import _normalize_country as implementation

    return implementation(value)
def _is_country_value(value):
    from .services.normalization import _is_country_value as implementation

    return implementation(value)
def _clean_city_name(value):
    from .services.normalization import _clean_city_name as implementation

    return implementation(value)
def _clean_contact_person_values(values, company_name=None):
    from .services.normalization import _clean_contact_person_values as implementation

    return implementation(values, company_name)
def _looks_like_organization_name(value):
    from .services.normalization import _looks_like_organization_name as implementation

    return implementation(value)
def _normalize_compare_text(value):
    from .services.normalization import _normalize_compare_text as implementation

    return implementation(value)
def _designation_values(value, count=0):
    from .services.normalization import _designation_values as implementation

    return implementation(value, count)
def _clean_job_title_text(value):
    from .services.normalization import _clean_job_title_text as implementation

    return implementation(value)
def _clean_job_title_value(value):
    from .services.normalization import _clean_job_title_value as implementation

    return implementation(value)
def _split_person_name(person):
    from .services.normalization import _split_person_name as implementation

    return implementation(person)
def _populate_lead_data_child_tables(lead_data_doc, company, extracted=None):
    from .services.normalization import _populate_lead_data_child_tables as implementation

    return implementation(lead_data_doc, company, extracted)
@frappe.whitelist()
def extract_leads(lead_data_import_name):
    _ensure_lead_data_import_schema()

    doc = frappe.get_doc(LEAD_DATA_IMPORT_DOCTYPE, lead_data_import_name)
    if doc.status == "Processing":
        frappe.throw(_("Extraction is already running for this document."))

    frappe.db.set_value(LEAD_DATA_IMPORT_DOCTYPE, lead_data_import_name, {
        "status": "Processing",
        "status_log": "Starting extraction...",
    })
    frappe.db.delete(LEAD_DATA_DOCTYPE, {LEAD_DATA_IMPORT_FIELD: lead_data_import_name})
    frappe.db.commit()

    frappe.enqueue(
        _run_extraction,
        queue="default",
        timeout=600,
        lead_data_import_name=lead_data_import_name,
        enqueue_after_commit=True,
    )
    return {"ok": True, "message": "Extraction started. Refresh the page in a moment to see results."}


@frappe.whitelist()
def preview_screenshot_leads(lead_data_import_name):
    from .pipelines.screenshot import preview

    return preview(lead_data_import_name)
@frappe.whitelist()
def create_leads_from_preview(lead_data_import_name, leads_json, replace_existing=True):
    from .pipelines.screenshot import create_from_preview

    return create_from_preview(lead_data_import_name, leads_json, replace_existing)


# Background job

def _run_extraction(lead_data_import_name):
    try:
        doc = frappe.get_doc(LEAD_DATA_IMPORT_DOCTYPE, lead_data_import_name)
        input_type = doc.input_type

        _log(lead_data_import_name, f"Input type: {input_type}")

        if input_type == "URL":
            companies = _pipeline_url(lead_data_import_name, doc.source_url)
        elif input_type == "Screenshot":
            companies = _pipeline_screenshot(lead_data_import_name, _screenshot_file_urls(doc))
        elif input_type == "PDF":
            companies = _pipeline_pdf(lead_data_import_name, doc.upload_file)
        else:
            _finish(lead_data_import_name, "Error: Unknown input type.")
            return

        if not companies and input_type == "URL":
            _log(lead_data_import_name, "No companies detected. Treating source URL as one company website.")
            companies = [_company_from_website_html(None, doc.source_url)]

        if not companies:
            _finish(lead_data_import_name, "No companies found. Check the URL or file and try again.")
            return

        _log(
            lead_data_import_name,
            f"Found {len(companies)} companies. Processing in batches of {BATCH_SIZE}..."
        )

        total_saved = 0

        for i in range(0, len(companies), BATCH_SIZE):
            batch = companies[i:i + BATCH_SIZE]

            _log(
                lead_data_import_name,
                f"Processing batch {i // BATCH_SIZE + 1} "
                f"({len(batch)} companies)"
            )

            # Enrich + save each company immediately (incremental)
            saved_in_batch = _enrich_and_save_companies(
                lead_data_import_name, batch, ai_fallback=True
            )
            total_saved += saved_in_batch

            _log(
                lead_data_import_name,
                f"Processed {total_saved}/{len(companies)} companies"
            )

        _finish(
            lead_data_import_name,
            f"Ready. {total_saved} leads extracted. Review and create."
        )

    except Exception:
        tb = frappe.get_traceback()
        frappe.log_error(title=_("Lead Import extraction failed"), message=tb)
        _finish(lead_data_import_name, _format_error_for_status("Error during extraction.", tb))


# Pipeline: URL

def _pipeline_url(lead_data_import_name, url):
    from .pipelines.url import extract

    return extract(lead_data_import_name, url)
def _extract_companies_from_partner_html(html, page_url, ai_fallback=True):
    from .services.directory_extraction import _extract_companies_from_partner_html as implementation

    return implementation(html, page_url, ai_fallback)
def _extract_companies_from_links_and_logos(html, page_url):
    from .services.directory_extraction import _extract_companies_from_links_and_logos as implementation

    return implementation(html, page_url)
def _should_treat_as_directory(html, companies):
    from .services.directory_extraction import _should_treat_as_directory as implementation

    return implementation(html, companies)
def _filter_company_candidates(companies, page_url=None):
    from .services.directory_extraction import _filter_company_candidates as implementation

    return implementation(companies, page_url)
def _has_directory_page_signals(html):
    from .services.directory_extraction import _has_directory_page_signals as implementation

    return implementation(html)
def _company_from_website_html(html, page_url):
    from .services.directory_extraction import _company_from_website_html as implementation

    return implementation(html, page_url)
def _company_name_from_anchor(body, website):
    from .services.directory_extraction import _company_name_from_anchor as implementation

    return implementation(body, website)
def _extract_companies_from_images(html):
    from .services.directory_extraction import _extract_companies_from_images as implementation

    return implementation(html)
def _clean_asset_filename(value):
    from .services.directory_extraction import _clean_asset_filename as implementation

    return implementation(value)
def _clean_company_candidate_text(value):
    from .services.directory_extraction import _clean_company_candidate_text as implementation

    return implementation(value)
def _is_probable_company_name(value):
    from .services.directory_extraction import _is_probable_company_name as implementation

    return implementation(value)
def _domain_to_company_name(url):
    from .services.directory_extraction import _domain_to_company_name as implementation

    return implementation(url)
def _normalized_domain(url):
    from .services.directory_extraction import _normalized_domain as implementation

    return implementation(url)
def _skip_company_candidate_href(href):
    from .services.directory_extraction import _skip_company_candidate_href as implementation

    return implementation(href)
def _is_noise_domain(domain):
    from .services.directory_extraction import _is_noise_domain as implementation

    return implementation(domain)


# Pipeline: Screenshot

def _pipeline_screenshot(lead_data_import_name, file_url):
    from .pipelines.screenshot import extract

    return extract(lead_data_import_name, file_url)

# Pipeline: PDF

def _pipeline_pdf(lead_data_import_name, file_url):
    from .pipelines.pdf import extract

    return extract(lead_data_import_name, file_url)
def _enrich_and_save_companies(lead_data_import_name, companies, ai_fallback=False):
    from .services.enrichment import _enrich_and_save_companies as implementation

    return implementation(lead_data_import_name, companies, ai_fallback)
def _enrich_single_company(settings, slugs, company, lead_data_import_name=None, ai_fallback=True, field_guidance=""):
    from .services.enrichment import _enrich_single_company as implementation

    return implementation(settings, slugs, company, lead_data_import_name, ai_fallback, field_guidance)

# Mistral API calls
def _mistral_chat_model(settings):
    from .services.mistral import _mistral_chat_model as implementation

    return implementation(settings)
def _call_mistral_vision_json_list(settings, prompt, image_b64, mime, error_title):
    from .services.mistral import _call_mistral_vision_json_list as implementation

    return implementation(settings, prompt, image_b64, mime, error_title)
def _mistral_extract_companies_from_html(html, page_url):
    from .services.mistral import _mistral_extract_companies_from_html as implementation

    return implementation(html, page_url)
def _mistral_extract_companies_from_image(image_b64, mime, qr_urls=None):
    from .services.mistral import _mistral_extract_companies_from_image as implementation

    return implementation(image_b64, mime, qr_urls)
def _mistral_extract_logo_companies_from_image(image_b64, mime):
    from .services.mistral import _mistral_extract_logo_companies_from_image as implementation

    return implementation(image_b64, mime)
def _repair_business_card_company_person_mixup(company):
    from .services.mistral import _repair_business_card_company_person_mixup as implementation

    return implementation(company)
def _infer_business_card_emails(company, contacts):
    from .services.mistral import _infer_business_card_emails as implementation

    return implementation(company, contacts)
def _prioritize_business_card_emails(company):
    from .services.mistral import _prioritize_business_card_emails as implementation

    return implementation(company)
def _domain_from_url(url):
    from .services.mistral import _domain_from_url as implementation

    return implementation(url)
def _email_local_part_from_person(person):
    from .services.mistral import _email_local_part_from_person as implementation

    return implementation(person)
def _ascii_email_token(value):
    from .services.mistral import _ascii_email_token as implementation

    return implementation(value)
def _looks_like_person_name(value):
    from .services.mistral import _looks_like_person_name as implementation

    return implementation(value)
def _infer_company_name_from_business_card(company, email_domains):
    from .services.mistral import _infer_company_name_from_business_card as implementation

    return implementation(company, email_domains)
def _mistral_extract_companies_from_text(text):
    from .services.mistral import _mistral_extract_companies_from_text as implementation

    return implementation(text)
def _mistral_extract_lead_fields(settings, text, company_name, field_guidance=None):
    from .services.mistral import _mistral_extract_lead_fields as implementation

    return implementation(settings, text, company_name, field_guidance)
def _call_mistral_json_list(settings, prompt):
    from .services.mistral import _call_mistral_json_list as implementation

    return implementation(settings, prompt)
def _filter_extracted_to_source_text(result, source_text):
    from .services.mistral import _filter_extracted_to_source_text as implementation

    return implementation(result, source_text)


# Web scraping helpers

def _fetch_html(url, js_render=False):
    from .services.web import _fetch_html as implementation

    return implementation(url, js_render)
def _clean_html(html):
 from .services.web import _clean_html as implementation

 return implementation(html)
def _decode_cf_email(encoded_hex):
    from .services.web import _decode_cf_email as implementation

    return implementation(encoded_hex)
def _extract_contact_fields_from_html(html):
    from .services.web import _extract_contact_fields_from_html as implementation

    return implementation(html)
def _extract_addresses_from_text(text):
    from .services.web import _extract_addresses_from_text as implementation

    return implementation(text)
def _get_domain_root(url):
    from .services.web import _get_domain_root as implementation

    return implementation(url)
def _sanitize_phone(phone):
    from .services.web import _sanitize_phone as implementation

    return implementation(phone)
def _sanitize_phone_list(value):
    from .services.web import _sanitize_phone_list as implementation

    return implementation(value)
def _phone_dedupe_key(phone):
    from .services.web import _phone_dedupe_key as implementation

    return implementation(phone)
def _load_file_as_base64(file_url):
    from .services.web import _load_file_as_base64 as implementation

    return implementation(file_url)
def _load_card_crop_as_base64(file_url):
    from .services.web import _load_card_crop_as_base64 as implementation

    return implementation(file_url)
def _get_file_path_from_url(file_url):
    from .services.web import _get_file_path_from_url as implementation

    return implementation(file_url)
def _decode_qr_urls_from_file(file_url):
    from .services.web import _decode_qr_urls_from_file as implementation

    return implementation(file_url)
def _normalize_url(value):
    from .services.web import _normalize_url as implementation

    return implementation(value)
def _infer_or_search_website(company):
    from .services.web import _infer_or_search_website as implementation

    return implementation(company)
def _search_company_website(company):
    from .services.web import _search_company_website as implementation

    return implementation(company)
def _has_desired_lead_data(data):
    from .services.web import _has_desired_lead_data as implementation

    return implementation(data)
def _has_contact_lead_data(data):
    from .services.web import _has_contact_lead_data as implementation

    return implementation(data)
def _has_direct_contact_lead_data(data):
    from .services.web import _has_direct_contact_lead_data as implementation

    return implementation(data)
def _is_preferred_legal_slug(slug):
    from .services.web import _is_preferred_legal_slug as implementation

    return implementation(slug)
def _ordered_reference_slugs(slugs):
    from .services.web import _ordered_reference_slugs as implementation

    return implementation(slugs)
def _reference_urls_for_company(base, website, slugs):
    from .services.web import _reference_urls_for_company as implementation

    return implementation(base, website, slugs)
def _is_broad_contact_directory(data):
    from .services.web import _is_broad_contact_directory as implementation

    return implementation(data)
def _extract_lead_fields_from_page(
    settings,
    html,
    company_name,
    source_label,
    ai_fallback=True,
    force_ai=False,
    field_guidance=None,
):
    from .services.web import _extract_lead_fields_from_page as implementation

    return implementation(settings, html, company_name, source_label, ai_fallback, force_ai, field_guidance)
def _merge_extracted_lead_fields(target, source):
    from .services.web import _merge_extracted_lead_fields as implementation

    return implementation(target, source)
def _as_unique_list(value):
    from .services.persistence import _as_unique_list as implementation

    return implementation(value)
def _normalize_company_dict(company):
    from .services.persistence import _normalize_company_dict as implementation

    return implementation(company)
def _is_noise_email(email):
    from .services.persistence import _is_noise_email as implementation

    return implementation(email)
def _split_email_values(value):
    from .services.persistence import _split_email_values as implementation

    return implementation(value)
def _lead_data_doc_to_company(lead_data_doc):
    from .services.persistence import _lead_data_doc_to_company as implementation

    return implementation(lead_data_doc)
def _merge_company_lead_data(existing, incoming):
    from .services.persistence import _merge_company_lead_data as implementation

    return implementation(existing, incoming)
def _save_single_company_once(lead_data_import_name, company, saved_keys):
    from .services.persistence import _save_single_company_once as implementation

    return implementation(lead_data_import_name, company, saved_keys)
def _company_dedupe_key(company):
    from .services.persistence import _company_dedupe_key as implementation

    return implementation(company)
def _save_single_company(lead_data_import_name, company):
    from .services.persistence import _save_single_company as implementation

    return implementation(lead_data_import_name, company)
def _truncate(value, max_len=140):
    from .services.persistence import _truncate as implementation

    return implementation(value, max_len)
def _build_import_info(company):
    from .services.persistence import _build_import_info as implementation

    return implementation(company)
def _log(lead_data_import_name, message):
    if not lead_data_import_name:
        return
    doc = frappe.get_doc(LEAD_DATA_IMPORT_DOCTYPE, lead_data_import_name)
    existing = doc.status_log or ""
    new_log = f"{existing}\n{message}".strip()
    frappe.db.set_value(LEAD_DATA_IMPORT_DOCTYPE, lead_data_import_name, "status_log", new_log)
    frappe.db.commit()


def _format_error_for_status(message, traceback_text=None, max_len=6000):
    details = str(traceback_text or "").strip()
    if not details:
        return message

    if len(details) > max_len:
        details = "...\n" + details[-max_len:]

    return f"{message}\n\nDetails:\n{details}"


def _finish(lead_data_import_name, message):
    doc = frappe.get_doc(LEAD_DATA_IMPORT_DOCTYPE, lead_data_import_name)
    existing = (doc.status_log or "").strip()
    status_log = f"{existing}\n{message}".strip() if existing else message
    frappe.db.set_value(LEAD_DATA_IMPORT_DOCTYPE, lead_data_import_name, {
        "status": "Ready",
        "status_log": status_log,
    })
    frappe.db.commit()


def _parse_json_list(text):
    if not text:
        return []
    text = text.strip()
    text = re.sub(r"^```[a-z]*\n?", "", text)
    text = re.sub(r"\n?```$", "", text)
    text = text.strip()
    try:
        result = json.loads(text)
        if isinstance(result, list):
            return [item for item in result if isinstance(item, dict)]
        if isinstance(result, dict):
            if result.get("company_name") or result.get("website"):
                return [result]
            for v in result.values():
                if isinstance(v, list):
                    return [item for item in v if isinstance(item, dict)]
    except Exception:
        pass
    return []


def _sanitize_email(email):
    if not email:
        return ""

    email = str(email).strip().strip("<>.,;:)")

    # Common protected emails
    if "protected email" in email.lower():
        return ""

    lowered = email.lower()
    local_part, _, domain = lowered.partition("@")
    if not local_part or not domain:
        return ""

    if domain in TECHNICAL_EMAIL_DOMAINS or any(domain.endswith(f".{d}") for d in TECHNICAL_EMAIL_DOMAINS):
        return ""

    if local_part in TECHNICAL_EMAIL_LOCAL_PARTS:
        return ""

    if re.fullmatch(r"[a-f0-9]{24,}", local_part):
        return ""

    try:
        validate_email_address(email, throw=True)
        return email
    except Exception:
        return ""
    
@frappe.whitelist()
def re_enrich_incomplete(lead_data_import_name):
    from .services.reenrichment import re_enrich_incomplete as implementation

    return implementation(lead_data_import_name)
def _re_enrich_import_rows(lead_data_import_name, only_incomplete=False):
    from .services.reenrichment import _re_enrich_import_rows as implementation

    return implementation(lead_data_import_name, only_incomplete)
def _get_reference_slugs(lead_data_import_name=None):
    from .services.reenrichment import _get_reference_slugs as implementation

    return implementation(lead_data_import_name)
def _reenrich_single_row(settings, slugs, row, field_guidance=""):
    from .services.reenrichment import _reenrich_single_row as implementation

    return implementation(settings, slugs, row, field_guidance)
def _save_refined_lead_data_doc(lead_data_doc, company, extracted):
    from .services.reenrichment import _save_refined_lead_data_doc as implementation

    return implementation(lead_data_doc, company, extracted)
def _run_re_enrichment(lead_data_import_name, rows_to_refine):
    from .services.reenrichment import _run_re_enrichment as implementation

    return implementation(lead_data_import_name, rows_to_refine)
def _discover_internal_links(base_url, html, limit=8):
    from .services.reenrichment import _discover_internal_links as implementation

    return implementation(base_url, html, limit)
def _discover_legal_links(base_url, html, limit=6):
    from .services.reenrichment import _discover_legal_links as implementation

    return implementation(base_url, html, limit)
