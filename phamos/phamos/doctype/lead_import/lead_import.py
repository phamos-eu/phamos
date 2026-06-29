# Copyright (c) 2026, phamos.eu and contributors
# Lead Import: scrape partner directories and extract lead data via Mistral AI.

import base64
import json
import os
import re
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from urllib.parse import urlparse

import frappe
import requests
from frappe import _
from frappe.model.document import Document
from frappe.utils import get_files_path, validate_email_address

from phamos.phamos.doctype.accounting_receipt.mistral_pdf import _get_phamos_settings

MISTRAL_CHAT_MODEL_DEFAULT = "mistral-small-latest"
SCRAPE_TIMEOUT = 6
MAX_COMPANIES_PER_IMPORT = 0
FAST_REEXTRACT_CRAWL_LIMIT = 5
ENRICHMENT_WORKERS = 6
ENRICHMENT_SLUG_LIMIT = 12
BATCH_SIZE = 50
LEAD_LIST_FIELDS = ("emails", "phones", "contact_persons", "addresses")

LEAD_FIELD_EXTRACTION_PROMPT = """Extract contact details for this company from the text.
Company: {company_name}

Return only this JSON object:
{{"emails":[],"phones":[],"contact_persons":[],"addresses":[],"website":""}}

Use only values explicitly present in the text. Keep list fields as arrays of strings.
Phones must be real telephone/mobile numbers. Exclude fax numbers, dates, IDs,
prices, percentages, coordinates, and list numbering.

Text:
---
{text}
---"""


class LeadImport(Document):
    pass


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
    """Best-effort parsing for compact postal addresses."""
    text = str(address or "").strip()
    if not text:
        return {}

    parts = [part.strip() for part in re.split(r",|\n", text) if part.strip()]
    country = _normalize_country(parts[-1]) if parts else ""
    search_text = ", ".join(parts[:-1]) if country and len(parts) > 1 else text

    postal_code = ""
    city = ""
    state = ""

    postal_match = re.search(r"\b(?:[A-Z]{1,3}-)?(\d{4,6})\s+([^,]+)", search_text)
    if postal_match:
        postal_code = postal_match.group(1).strip()
        city = _clean_city_name(postal_match.group(2))

    if not city:
        in_city_match = re.search(
            r"\bin\s+([A-ZÄÖÜ][A-Za-zÀ-ÖØ-öø-ÿ .'-]+?)(?:,|$)",
            search_text,
        )
        if in_city_match:
            city = _clean_city_name(in_city_match.group(1))

    if not city and len(parts) >= 2:
        city = _clean_city_name(parts[-2] if country else parts[-1])

    return {
        "city": city,
        "state": state,
        "country": country,
        "postal_code": postal_code,
    }


def _first_address_components(addresses):
    for address in addresses or []:
        parsed = _parse_address_components(address)
        if any(parsed.values()):
            return parsed
    return {}


def _normalize_country(value):
    raw = str(value or "").strip()
    clean = re.sub(r"[^A-Za-zÀ-ÖØ-öø-ÿ]", "", raw).lower()
    if clean in COUNTRY_ALIASES:
        return COUNTRY_ALIASES[clean]

    lowered = raw.lower()
    for alias, country in COUNTRY_ALIASES.items():
        if re.search(rf"\b{re.escape(alias)}\b", lowered):
            return country

    return raw if raw and len(raw.split()) <= 3 else ""


def _clean_city_name(value):
    city = str(value or "").strip()
    city = re.sub(r"\b(?:Germany|Deutschland|Austria|Osterreich|Österreich|Switzerland|Schweiz)\b", "", city, flags=re.I)
    city = re.sub(r"\s+", " ", city).strip(" ,.;")
    return city

def _populate_lead_data_child_tables(lead_data_doc, company, extracted=None):
    """Fill lead_data_website / lead_data_address / lead_data_contact from
    a company dict (and optional extracted dict with emails/phones/contact_persons/addresses lists)."""

    extracted = extracted or {}

    lead_data_doc.set("lead_data_website", [])
    lead_data_doc.set("lead_data_address", [])
    lead_data_doc.set("lead_data_contact", [])

    main_site = company.get("website")
    if main_site:
        lead_data_doc.append("lead_data_website", {
            "website": _truncate(main_site),
            "comment": "main",
        })

    emails = extracted.get("emails") or ([company["email"]] if company.get("email") else [])
    phones = _sanitize_phone_list(extracted.get("phones") or company.get("phone"))
    addresses = extracted.get("addresses") or ([company["address"]] if company.get("address") else [])

    clean_emails = []
    for e in emails:
        ce = _sanitize_email(e)
        if ce and ce not in clean_emails:
            clean_emails.append(ce)

    if addresses:
        for idx, addr in enumerate(addresses):
            address_parts = _parse_address_components(addr)
            lead_data_doc.append("lead_data_address", {
                "address_title": company.get("company_name"),
                "address_line_1": _truncate(addr, max_len=1000),
                "citytown": _truncate(address_parts.get("city")),
                "stateprovince": _truncate(address_parts.get("state")),
                "country": _truncate(address_parts.get("country")),
                "postal_code": _truncate(address_parts.get("postal_code")),
                "email_address": _truncate(clean_emails[idx]) if idx < len(clean_emails) else (_truncate(clean_emails[0]) if clean_emails else ""),
                "phone": _truncate(phones[idx]) if idx < len(phones) else "",
            })
    elif clean_emails or phones:
        lead_data_doc.append("lead_data_address", {
            "address_title": company.get("company_name"),
            "email_address": _truncate(clean_emails[0]) if clean_emails else "",
            "phone": _truncate(phones[0]) if phones else "",
        })

    contacts = extracted.get("contact_persons") or ([company["contact_person"]] if company.get("contact_person") else [])
    for idx, person in enumerate(contacts):
        if not person:
            continue
        parts = str(person).strip().split(" ", 1)
        first_name = parts[0]
        last_name = parts[1] if len(parts) > 1 else ""
        lead_data_doc.append("lead_data_contact", {
            "first_name": _truncate(first_name),
            "last_name": _truncate(last_name),
            "email_address": _truncate(clean_emails[idx]) if idx < len(clean_emails) else "",
            "phone": _truncate(phones[idx]) if idx < len(phones) else "",
        })

    lead_data_doc.organization_name = _truncate(company.get("company_name"))
    lead_data_doc.website = _truncate(main_site)
    lead_data_doc.email = _format_email_field(", ".join(clean_emails)) if clean_emails else ""
    lead_data_doc.phone = _truncate(", ".join(phones)) if phones else ""
    primary_address = _first_address_components(addresses)
    lead_data_doc.city = _truncate(primary_address.get("city"))
    lead_data_doc.stateprovince = _truncate(primary_address.get("state"))
    lead_data_doc.country = _truncate(primary_address.get("country"))

    return lead_data_doc 

@frappe.whitelist()
def extract_leads(lead_import_name):
    doc = frappe.get_doc("Lead Import", lead_import_name)
    if doc.status == "Processing":
        frappe.throw(_("Extraction is already running for this document."))

    frappe.db.set_value("Lead Import", lead_import_name, {
        "status": "Processing",
        "status_log": "Starting extraction...",
    })
    frappe.db.delete("Lead Import Item", {"parent": lead_import_name})
    frappe.db.commit()

    frappe.enqueue(
        _run_extraction,
        queue="default",
        timeout=600,
        lead_import_name=lead_import_name,
        enqueue_after_commit=True,
    )
    return {"ok": True, "message": "Extraction started. Refresh the page in a moment to see results."}


# Background job

def _run_extraction(lead_import_name):
    try:
        doc = frappe.get_doc("Lead Import", lead_import_name)
        input_type = doc.input_type

        _log(lead_import_name, f"Input type: {input_type}")

        if input_type == "URL":
            companies = _pipeline_url(lead_import_name, doc.source_url)
        elif input_type == "Screenshot":
            companies = _pipeline_screenshot(lead_import_name, doc.upload_file)
        elif input_type == "PDF":
            companies = _pipeline_pdf(lead_import_name, doc.upload_file)
        else:
            _finish(lead_import_name, "Error: Unknown input type.")
            return

        if not companies:
            _finish(lead_import_name, "No companies found. Check the URL or file and try again.")
            return

        _log(
            lead_import_name,
            f"Found {len(companies)} companies. Processing in batches of {BATCH_SIZE}..."
        )

        total_saved = 0

        for i in range(0, len(companies), BATCH_SIZE):
            batch = companies[i:i + BATCH_SIZE]

            _log(
                lead_import_name,
                f"Processing batch {i // BATCH_SIZE + 1} "
                f"({len(batch)} companies)"
            )

            # Enrich + save each company immediately (incremental)
            saved_in_batch = _enrich_and_save_companies(
                lead_import_name, batch, ai_fallback=True
            )
            total_saved += saved_in_batch

            _log(
                lead_import_name,
                f"Processed {total_saved}/{len(companies)} companies"
            )

        _finish(
            lead_import_name,
            f"Ready. {total_saved} leads extracted. Review and create."
        )

    except Exception:
        tb = frappe.get_traceback()
        frappe.log_error(title=_("Lead Import extraction failed"), message=tb)
        _finish(lead_import_name, "Error during extraction. Check Error Log for details.")


# Pipeline: URL

def _pipeline_url(lead_import_name, url):
    if not url:
        frappe.throw(_("Source URL is required for URL input type."))

    _log(lead_import_name, f"Scraping: {url}")
    html = _fetch_html(url)
    if not html:
        _log(lead_import_name, "Could not fetch the page. Check the URL.")
        return []

    companies = _extract_companies_from_partner_html(html, url, ai_fallback=False)

    if not companies:
        _log(lead_import_name, "No companies in static HTML. Trying JS render...")
        html = _fetch_html(url, js_render=True)
        if html:
            companies = _extract_companies_from_partner_html(html, url, ai_fallback=True)

    _log(lead_import_name, f"Found {len(companies)} companies on the page.")
    return companies if not MAX_COMPANIES_PER_IMPORT else companies[:MAX_COMPANIES_PER_IMPORT]


def _extract_companies_from_partner_html(html, page_url, ai_fallback=True):
    """
    Extract company names and website URLs from a JS-rendered
    partner/directory page by parsing gallery-item-partner blocks.
    Falls back to Mistral if no structured blocks found.
    """
    blocks = re.split(r'(?=<div class="gallery-item-partner)', html)
    companies = []

    for block in blocks:
        if 'gallery-item-partner' not in block:
            continue

        href_match = re.search(r'<a href="([^"]+)"', block)
        img_match = re.search(r'<img[^>]+src="([^"]+)"', block)

        if not href_match:
            continue

        href = href_match.group(1)

        # Skip mailto and relative links
        if href.startswith("mailto:"):
            continue
        if not href.startswith("http"):
            continue

        # Derive company name from image filename
        img_src = img_match.group(1) if img_match else ""
        filename = img_src.split("/")[-1]
        filename = re.sub(r'^csm_logo_', '', filename)
        filename = re.sub(r'_[a-f0-9]{8,}.*$', '', filename)
        company_name = filename.replace("_", " ").title().strip()

        if company_name and href:
            companies.append({"company_name": company_name, "website": href})

    # Fallback to Mistral if regex found nothing
    if ai_fallback and not companies:
        companies = _mistral_extract_companies_from_html(html, page_url)

    return companies


# Pipeline: Screenshot

def _pipeline_screenshot(lead_import_name, file_url):
    if not file_url:
        frappe.throw(_("Please upload a screenshot file."))

    _log(lead_import_name, "Reading screenshot via Mistral vision...")
    image_b64, mime = _load_file_as_base64(file_url)
    if not image_b64:
        _log(lead_import_name, "Could not read uploaded file.")
        return []

    companies = _mistral_extract_companies_from_image(image_b64, mime)
    _log(lead_import_name, f"Mistral identified {len(companies)} companies in the screenshot.")
    return companies if not MAX_COMPANIES_PER_IMPORT else companies[:MAX_COMPANIES_PER_IMPORT]

# Pipeline: PDF

def _pipeline_pdf(lead_import_name, file_url):
    if not file_url:
        frappe.throw(_("Please upload a PDF file."))

    _log(lead_import_name, "Running OCR on PDF via Mistral...")

    settings = _get_phamos_settings()
    if not settings:
        frappe.throw(_("Mistral API key is not configured in phamos Settings."))

    url = file_url.strip().lstrip("/")
    if url.startswith("private/files/"):
        path = get_files_path(*url.replace("private/files/", "", 1).split("/"), is_private=1)
    else:
        path = get_files_path(*url.replace("files/", "", 1).split("/"))

    if not path or not os.path.isfile(path):
        _log(lead_import_name, "PDF file not found on disk.")
        return []

    with open(path, "rb") as f:
        pdf_b64 = base64.b64encode(f.read()).decode("utf-8")

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
    resp = requests.post(ocr_url, json=payload, headers=headers, timeout=120)
    if not resp.ok:
        _log(lead_import_name, f"OCR failed: {resp.status_code}")
        return []

    markdown = "\n\n".join(p.get("markdown", "") for p in resp.json().get("pages", []))
    if not markdown.strip():
        _log(lead_import_name, "OCR returned empty text.")
        return []

    companies = _mistral_extract_companies_from_text(markdown)
    _log(lead_import_name, f"Mistral identified {len(companies)} companies in the PDF.")
    return companies if not MAX_COMPANIES_PER_IMPORT else companies[:MAX_COMPANIES_PER_IMPORT]


def _enrich_and_save_companies(lead_import_name, companies, ai_fallback=False):
    """Enrich each company and immediately save it to the child table."""
    settings = _get_phamos_settings()
    if ai_fallback and not settings:
        frappe.throw(_("Mistral API key is not configured in phamos Settings."))

    doc = frappe.get_doc("Lead Import", lead_import_name)
    raw_refs = doc.reference_urls or ""
    slugs = [
        s.strip().strip("/")
        for s in raw_refs.splitlines()
        if s.strip() and not s.strip().startswith("#")
    ]

    total = len(companies)

    if ai_fallback and total > 1:
        workers = min(ENRICHMENT_WORKERS, total)
        _log(lead_import_name, f"Fast enrichment running with {workers} workers.")

        with ThreadPoolExecutor(max_workers=workers) as executor:
            future_map = {
                executor.submit(
                    _enrich_single_company,
                    settings,
                    slugs,
                    company,
                    None,
                    ai_fallback,
                ): (idx, company)
                for idx, company in enumerate(companies, start=1)
            }

            for future in as_completed(future_map):
                idx, company = future_map[future]
                name = company.get("company_name", "Unknown")
                try:
                    enriched = future.result()
                except Exception:
                    frappe.log_error(
                        title=_("Lead Import company enrichment failed"),
                        message=frappe.get_traceback(),
                    )
                    enriched = company

                _save_single_company(lead_import_name, enriched)
                _log(lead_import_name, f"[{idx}/{total}] Saved: {name}")

        return total

    for idx, company in enumerate(companies, start=1):
        name = company.get("company_name", "Unknown")
        action = "Enriching" if ai_fallback else "Saving"
        _log(lead_import_name, f"[{idx}/{total}] {action}: {name}")

        enriched = _enrich_single_company(
            settings, slugs, company, lead_import_name, ai_fallback=ai_fallback
        )
        _save_single_company(lead_import_name, enriched)

    return total

def _enrich_single_company(settings, slugs, company, lead_import_name=None, ai_fallback=True):
    name    = company.get("company_name", "Unknown")
    website = company.get("website", "")

    sources_found = []
    extracted     = {}
    found_preferred_source = False

    if not website:
        return company

    base = _get_domain_root(website)

    # Prefer legal/imprint pages before contact pages. Contact pages are often
    # global office directories and can flood one lead with every branch.
    for slug_url in _reference_urls_for_company(base, website, slugs)[:ENRICHMENT_SLUG_LIMIT]:
        slug_html = _fetch_html(slug_url)
        if not slug_html:
            continue

        page_extracted = _extract_lead_fields_from_page(
            settings,
            slug_html,
            name,
            f"Reference page: {slug_url}",
            ai_fallback=ai_fallback,
            force_ai=_is_preferred_legal_slug(slug_url),
        )
        if not _has_contact_lead_data(page_extracted):
            continue

        if _is_broad_contact_directory(page_extracted) and not _is_preferred_legal_slug(slug_url):
            continue

        if _is_preferred_legal_slug(slug_url):
            _merge_extracted_lead_fields(extracted, page_extracted)
            found_preferred_source = True
        else:
            _merge_extracted_lead_fields(extracted, page_extracted)

        sources_found.append(slug_url)
        if "impressum" in slug_url.lower() and not company.get("impressum_url"):
            company["impressum_url"] = slug_url
        if found_preferred_source and not _has_direct_contact_lead_data(extracted):
            continue
        break

    if (
        website.rstrip("/") != base.rstrip("/")
        and (not found_preferred_source or not _has_direct_contact_lead_data(extracted))
    ):
        orig_html = _fetch_html(website)
        if orig_html:
            page_extracted = _extract_lead_fields_from_page(
                settings,
                orig_html,
                name,
                f"Original page: {website}",
                ai_fallback=ai_fallback,
            )
            if _has_contact_lead_data(page_extracted) and not _is_broad_contact_directory(page_extracted):
                _merge_extracted_lead_fields(extracted, page_extracted)
                sources_found.append("original")

    if not _has_direct_contact_lead_data(extracted):
        main_html = _fetch_html(base)
        page_extracted = _extract_lead_fields_from_page(
            settings,
            main_html,
            name,
            f"Main page: {base}",
            ai_fallback=ai_fallback,
        )
        if _has_contact_lead_data(page_extracted) and not _is_broad_contact_directory(page_extracted):
            _merge_extracted_lead_fields(extracted, page_extracted)
            sources_found.append("main")

    if extracted:
        if lead_import_name:
            _log(lead_import_name, f"  → [{name}] Data found via: {', '.join(sources_found)}")
    else:
        if lead_import_name:
            _log(lead_import_name, f"  → [{name}] No data extracted")

    merged = {**company, **{k: v for k, v in extracted.items() if v and k != "website"}}
    return merged

# Mistral API calls

def _mistral_extract_companies_from_html(html, page_url):
    settings = _get_phamos_settings()
    if not settings:
        frappe.throw(_("Mistral API key is not configured."))

    clean = _clean_html(html)[:12000]
    prompt = f"""You are parsing a company directory or partner listing webpage.

Extract all company/organisation names and their website URLs from the text below.
The page URL is: {page_url}

Rules:
- Each entry must have a company_name and a website (full URL including https://)
- If a URL is relative (e.g. /partner/acone), convert it to absolute using the page URL domain
- Ignore navigation links, social media links, and footer links
- Return ONLY a valid JSON array, no explanation, no markdown

Format:
[
  {{"company_name": "Acone Consulting", "website": "https://acone.de"}},
  {{"company_name": "Atmos GmbH", "website": "https://atmos.de"}}
]

Page text:
---
{clean}
---"""

    return _call_mistral_json_list(settings, prompt)


def _mistral_extract_companies_from_image(image_b64, mime):
    settings = _get_phamos_settings()
    if not settings:
        frappe.throw(_("Mistral API key is not configured."))

    model = settings["model"]
    if "ocr" in model.lower():
        model = MISTRAL_CHAT_MODEL_DEFAULT

    prompt = """You are analyzing a screenshot of a company directory or partner listing page.

Extract all visible company/organisation names and any website URLs you can see or infer from the logos/text.

Return ONLY a valid JSON array, no explanation, no markdown.
Format:
[
  {"company_name": "Acone Consulting", "website": "https://acone.de"},
  {"company_name": "Atmos GmbH", "website": ""}
]

If you cannot find a website for a company, leave website as empty string."""

    url = f"{settings['base_url'].rstrip('/')}/chat/completions"
    headers = {
        "Authorization": f"Bearer {settings['api_key']}",
        "Content-Type": "application/json",
    }
    payload = {
        "model": model,
        "messages": [
            {
                "role": "user",
                "content": [
                    {"type": "image_url", "image_url": f"data:{mime};base64,{image_b64}"},
                    {"type": "text", "text": prompt},
                ],
            }
        ],
    }
    resp = requests.post(url, json=payload, headers=headers, timeout=60)
    if not resp.ok:
        frappe.log_error(title=_("Lead Import: Mistral vision failed"), message=resp.text[:500])
        return []

    content = (resp.json().get("choices") or [{}])[0].get("message", {}).get("content", "[]")
    return _parse_json_list(content)


def _mistral_extract_companies_from_text(text):
    settings = _get_phamos_settings()
    if not settings:
        frappe.throw(_("Mistral API key is not configured."))

    prompt = f"""You are parsing text extracted from a company directory or partner listing PDF.

Extract all company/organisation names and their website URLs.

Return ONLY a valid JSON array, no explanation, no markdown.
Format:
[
  {{"company_name": "Acone Consulting", "website": "https://acone.de"}},
  {{"company_name": "Atmos GmbH", "website": ""}}
]

Text:
---
{text[:10000]}
---"""

    return _call_mistral_json_list(settings, prompt)


def _mistral_extract_lead_fields(settings, text, company_name):
    model = settings["model"]
    if "ocr" in model.lower():
        model = MISTRAL_CHAT_MODEL_DEFAULT

    prompt = LEAD_FIELD_EXTRACTION_PROMPT.format(
        company_name=company_name,
        text=text,
    )

    url = f"{settings['base_url'].rstrip('/')}/chat/completions"
    headers = {
        "Authorization": f"Bearer {settings['api_key']}",
        "Content-Type": "application/json",
    }
    payload = {
        "model": model,
        "messages": [{"role": "user", "content": prompt}],
        "response_format": {"type": "json_object"},
    }
    try:
        resp = requests.post(url, json=payload, headers=headers, timeout=60)
        if not resp.ok:
            return {}
        content = (resp.json().get("choices") or [{}])[0].get("message", {}).get("content", "{}")
        result = json.loads(content)

        # Normalize: ensure list fields are actually lists
        for key in ("emails", "phones", "contact_persons", "addresses"):
            val = result.get(key, [])
            if isinstance(val, str):
                result[key] = [val] if val.strip() else []
            elif not isinstance(val, list):
                result[key] = []

        result = _filter_extracted_to_source_text(result, text)

        # Backward-compat flat fields (first/primary value) for child doctype single fields
        emails = [e for e in result.get("emails", []) if e]
        phones = _sanitize_phone_list(result.get("phones", []))
        contacts = [c for c in result.get("contact_persons", []) if c]
        addresses = [a for a in result.get("addresses", []) if a]

        result["email"] = ", ".join(_sanitize_email(e) for e in emails if _sanitize_email(e))
        result["phones"] = phones
        result["phone"] = ", ".join(phones)
        result["contact_person"] = ", ".join(contacts)
        result["address"] = " | ".join(addresses)

        return result
    except Exception:
        return {}


def _call_mistral_json_list(settings, prompt):
    model = settings["model"]
    if "ocr" in model.lower():
        model = MISTRAL_CHAT_MODEL_DEFAULT

    url = f"{settings['base_url'].rstrip('/')}/chat/completions"
    headers = {
        "Authorization": f"Bearer {settings['api_key']}",
        "Content-Type": "application/json",
    }
    payload = {
        "model": model,
        "messages": [{"role": "user", "content": prompt}],
    }
    try:
        resp = requests.post(url, json=payload, headers=headers, timeout=60)
        if not resp.ok:
            frappe.log_error(title=_("Lead Import: Mistral call failed"), message=resp.text[:500])
            return []
        content = (resp.json().get("choices") or [{}])[0].get("message", {}).get("content", "[]")
        return _parse_json_list(content)
    except Exception:
        tb = frappe.get_traceback()
        frappe.log_error(title=_("Lead Import: Mistral call exception"), message=tb)
        return []


def _filter_extracted_to_source_text(result, source_text):
    source = source_text or ""
    source_lower = source.lower()
    source_digits = re.sub(r"\D", "", source)
    filtered = dict(result or {})

    emails = []
    for email in filtered.get("emails") or []:
        clean = _sanitize_email(email)
        if clean and clean.lower() in source_lower and clean not in emails:
            emails.append(clean)
    filtered["emails"] = emails

    source_phone_digits = [
        re.sub(r"\D", "", phone)
        for phone in (_extract_contact_fields_from_html(source).get("phones") or [])
    ]
    phones = []
    for phone in _sanitize_phone_list(filtered.get("phones") or []):
        digits = re.sub(r"\D", "", phone)
        if digits and digits in source_phone_digits and phone not in phones:
            phones.append(phone)
    filtered["phones"] = phones

    contacts = []
    for contact in filtered.get("contact_persons") or []:
        clean = str(contact or "").strip()
        if not clean:
            continue
        tokens = [token for token in re.split(r"\s+", clean) if len(token) > 2]
        if clean.lower() in source_lower or (tokens and tokens[-1].lower() in source_lower):
            if clean not in contacts:
                contacts.append(clean)
    filtered["contact_persons"] = contacts

    addresses = []
    for address in filtered.get("addresses") or []:
        clean = str(address or "").strip()
        if not clean:
            continue
        parsed = _parse_address_components(clean)
        if parsed.get("postal_code") and parsed["postal_code"] not in source_digits:
            continue
        evidence = [
            parsed.get("postal_code"),
            parsed.get("city"),
            parsed.get("country"),
        ]
        has_evidence = any(
            value and str(value).lower() in source_lower
            for value in evidence
        )
        if clean.lower() in source_lower or has_evidence:
            if clean not in addresses:
                addresses.append(clean)
    filtered["addresses"] = addresses

    return filtered


# Web scraping helpers

def _fetch_html(url, js_render=False):
    if not url:
        return None

    if js_render:
        try:
            from selenium import webdriver
            from selenium.webdriver.chrome.options import Options
            from selenium.webdriver.chrome.service import Service
            from webdriver_manager.chrome import ChromeDriverManager

            options = Options()
            options.add_argument("--headless")
            options.add_argument("--no-sandbox")
            options.add_argument("--disable-dev-shm-usage")

            driver = webdriver.Chrome(
                service=Service(ChromeDriverManager().install()),
                options=options
            )
            driver.get(url)
            time.sleep(4)
            html = driver.page_source
            driver.quit()
            return html
        except Exception:
            frappe.log_error(
                title=_("Lead Import: Selenium fetch failed"),
                message=frappe.get_traceback()
            )
            return None
    else:
        try:
            headers = {"User-Agent": "Mozilla/5.0 (compatible; PhamosLeadImporter/1.0)"}
            resp = requests.get(url, headers=headers, timeout=SCRAPE_TIMEOUT, allow_redirects=True)
            if resp.ok:
                return resp.text
        except Exception:
            pass
        return None


def _clean_html(html):
	if not html:
		return ""
	html = re.sub(r"<(script|style)[^>]*>.*?</(script|style)>", " ", html, flags=re.DOTALL | re.IGNORECASE)
	html = re.sub(r"<[^>]+>", " ", html)
	html = re.sub(r"\s+", " ", html).strip()
	return html

def _decode_cf_email(encoded_hex):
    """Decode Cloudflare's data-cfemail obfuscated email hex string."""
    try:
        r = int(encoded_hex[:2], 16)
        email = "".join(
            chr(int(encoded_hex[i:i+2], 16) ^ r)
            for i in range(2, len(encoded_hex), 2)
        )
        return email
    except Exception:
        return ""

def _extract_contact_fields_from_html(html):
    if not html:
        return {}

    text = _clean_html(html)
    emails = []

    # Plain emails
    for email in re.findall(r"[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}", html, flags=re.IGNORECASE):
        clean_email = _sanitize_email(email.rstrip(".,;:)"))
        if clean_email and clean_email not in emails:
            emails.append(clean_email)

    # Cloudflare-obfuscated emails (data-cfemail="...")
    for cf_hex in re.findall(r'data-cfemail="([a-f0-9]+)"', html, flags=re.IGNORECASE):
        decoded = _decode_cf_email(cf_hex)
        clean_email = _sanitize_email(decoded)
        if clean_email and clean_email not in emails:
            emails.append(clean_email)

    phones = []
    for match in re.finditer(r"(?:\+|00)?\d[\d\s()./-]{6,}\d", text):
        context = text[max(0, match.start() - 40):match.start()].lower()
        if "fax" in context:
            continue
        phone = _sanitize_phone(match.group(0))
        if phone and phone not in phones:
            phones.append(phone)

    out = {}
    if emails:
        out["emails"] = emails
        out["email"] = ", ".join(emails)
    if phones:
        out["phones"] = phones
        out["phone"] = ", ".join(phones)
    return out


def _get_domain_root(url):
    """Strip path/query from a URL, keep scheme+netloc only."""
    if not url:
        return ""
    parsed = urlparse(url)
    if not parsed.scheme or not parsed.netloc:
        return url.rstrip("/")
    return f"{parsed.scheme}://{parsed.netloc}"


def _sanitize_phone(phone):
    if not phone:
        return ""

    phone = str(phone).strip()
    phone = re.sub(r"\s+", " ", phone).strip(" .,/;-")

    if not phone:
        return ""

    if re.search(r"\b\d{1,2}[./-]\d{1,2}[./-](?:19|20)?\d{2}\b", phone):
        return ""

    if re.search(r"\b\d{1,2}[.:]\d{2}\s*[-–]\s*\d{1,2}[.:]\d{2}\b", phone):
        return ""

    if re.fullmatch(r"\d+\)\s*.*", phone):
        return ""

    if re.fullmatch(r"(?:19|20)\d{2}\s*[-/]\s*(?:19|20)\d{2}", phone):
        return ""

    if re.fullmatch(r"\d{1,2}[./-]\d{1,2}[./-]\d{2,4}", phone):
        return ""

    if re.fullmatch(r"\d+[.,]\d+", phone):
        return ""

    if not phone.startswith(("+", "00", "0")):
        return ""

    phone = re.sub(r"(?<=\d)\s*[.]\s*(?=\d)", " ", phone)
    phone = re.sub(r"\s+", " ", phone).strip()

    digits = re.sub(r"\D", "", phone)
    if not 7 <= len(digits) <= 16:
        return ""

    if re.fullmatch(r"\d{11,16}", phone) and not phone.startswith(("+", "00", "0")):
        return ""

    if len(set(digits)) <= 2:
        return ""

    if not any(sep in phone for sep in ("+", " ", "-", "/", "(", ")")) and not phone.startswith("0"):
        return ""

    return phone


def _sanitize_phone_list(value):
    if not value:
        return []

    if isinstance(value, str):
        values = re.split(r"\s*(?:,|\||;|\n)\s*", value)
    else:
        values = value

    phones = []
    for phone in values:
        clean_phone = _sanitize_phone(phone)
        if clean_phone and clean_phone not in phones:
            phones.append(clean_phone)

    return phones


def _format_phone_field(value, max_len=140):
    phones = _sanitize_phone_list(value)
    if not phones:
        return ""

    out = []
    for phone in phones:
        candidate = ", ".join(out + [phone])
        if len(candidate) > max_len:
            break
        out.append(phone)

    return ", ".join(out)


def _load_file_as_base64(file_url):
    if not file_url:
        return None, None

    url = file_url.strip().lstrip("/")
    if url.startswith("private/files/"):
        path = get_files_path(*url.replace("private/files/", "", 1).split("/"), is_private=1)
    else:
        path = get_files_path(*url.replace("files/", "", 1).split("/"))

    if not path or not os.path.isfile(path):
        return None, None

    ext = os.path.splitext(path)[1].lower()
    mime_map = {".png": "image/png", ".jpg": "image/jpeg", ".jpeg": "image/jpeg", ".webp": "image/webp"}
    mime = mime_map.get(ext, "image/png")

    with open(path, "rb") as f:
        return base64.b64encode(f.read()).decode("utf-8"), mime


# ---------------------------------------------------------------------------
# Child table + logging helpers
# ---------------------------------------------------------------------------

def _has_desired_lead_data(data):
    """Email is the primary signal that enrichment succeeded."""
    if not data:
        return False

    email = _sanitize_email(data.get("email"))
    if email:
        return True

    for email in data.get("emails") or []:
        if _sanitize_email(email):
            return True

    return False


def _has_contact_lead_data(data):
    """True when we have any usable contact detail, not just an email."""
    if not data:
        return False

    if _has_desired_lead_data(data):
        return True

    if _sanitize_phone_list(data.get("phones") or data.get("phone")):
        return True

    addresses = data.get("addresses") or ([data.get("address")] if data.get("address") else [])
    return any(str(address).strip() for address in addresses)


def _has_direct_contact_lead_data(data):
    if not data:
        return False

    if _has_desired_lead_data(data):
        return True

    if _sanitize_phone_list(data.get("phones") or data.get("phone")):
        return True

    contacts = data.get("contact_persons") or ([data.get("contact_person")] if data.get("contact_person") else [])
    return any(str(contact).strip() for contact in contacts)


def _is_preferred_legal_slug(slug):
    slug = (slug or "").lower().strip("/")
    return any(keyword in slug for keyword in ("impressum", "imprint", "legal"))


def _ordered_reference_slugs(slugs):
    unique = []
    for slug in slugs or []:
        clean = (slug or "").strip().strip("/")
        if clean and clean not in unique:
            unique.append(clean)

    legal = [slug for slug in unique if _is_preferred_legal_slug(slug)]
    rest = [slug for slug in unique if slug not in legal]
    return legal + rest


def _reference_urls_for_company(base, website, slugs):
    candidates = []

    def add(url):
        if url and url not in candidates:
            candidates.append(url)

    parsed = urlparse(website or "")
    path_parts = [part for part in (parsed.path or "").split("/") if part]
    lang_prefix = path_parts[0] if path_parts and re.fullmatch(r"[a-z]{2}(?:-[a-z]{2})?", path_parts[0], re.I) else ""

    for slug in _ordered_reference_slugs(slugs):
        clean = (slug or "").strip().strip("/")
        if not clean:
            continue
        add(f"{base}/{clean}")
        if lang_prefix and not clean.startswith(f"{lang_prefix}/"):
            add(f"{base}/{lang_prefix}/{clean}")
            if _is_preferred_legal_slug(clean):
                add(f"{base}/{lang_prefix}/meta/{clean}")

    if lang_prefix:
        for slug in ("impressum", "imprint", "legal"):
            add(f"{base}/{lang_prefix}/meta/{slug}")
            add(f"{base}/{lang_prefix}/{slug}")

    for slug in ("meta/impressum", "impressum", "imprint", "legal"):
        add(f"{base}/{slug}")

    for source_url in (website, base):
        html = _fetch_html(source_url)
        for link in _discover_legal_links(source_url, html, limit=6):
            add(link)

    return candidates


def _is_broad_contact_directory(data):
    if not data:
        return False

    emails = data.get("emails")
    if not emails and data.get("email"):
        emails = re.split(r"\s*(?:,|\||;|\n)\s*", data.get("email"))
    emails = emails or []
    phones = _sanitize_phone_list(data.get("phones") or data.get("phone"))
    return len(emails) > 4 or len(phones) > 8


def _extract_lead_fields_from_page(settings, html, company_name, source_label, ai_fallback=True, force_ai=False):
    if not html:
        return {}

    clean = _clean_html(html)
    if not clean.strip():
        return {}

    extracted = _extract_contact_fields_from_html(html)
    if ai_fallback and (force_ai or not _has_contact_lead_data(extracted)):
        ai_extracted = _mistral_extract_lead_fields(
            settings,
            f"\n\n=== {source_label} ===\n{clean}"[:10000],
            company_name,
        )
        _merge_extracted_lead_fields(extracted, ai_extracted)

    return extracted


def _merge_extracted_lead_fields(target, source):
    if not source:
        return target

    for key, value in source.items():
        if not value:
            continue

        if key in LEAD_LIST_FIELDS:
            existing = target.get(key, [])
            if not isinstance(existing, list):
                existing = []

            values = value if isinstance(value, list) else [value]
            for item in values:
                if item and item not in existing:
                    existing.append(item)

            target[key] = existing
        elif not target.get(key):
            target[key] = value

    return target


def _split_email_values(value):
    emails = []
    for email in re.split(r"\s*(?:,|\||;|\n)\s*", value or ""):
        clean = _sanitize_email(email)
        if clean and clean not in emails:
            emails.append(clean)
    return emails


def _lead_data_doc_to_company(lead_data_doc):
    company = {
        "company_name": lead_data_doc.organization_name,
        "website": lead_data_doc.website,
        "email": lead_data_doc.email,
        "phone": lead_data_doc.phone,
    }

    websites = [
        row.website for row in (lead_data_doc.lead_data_website or [])
        if getattr(row, "website", None)
    ]
    if websites and not company.get("website"):
        company["website"] = websites[0]

    emails = _split_email_values(lead_data_doc.email)
    phones = _sanitize_phone_list(lead_data_doc.phone)
    addresses = []
    contacts = []

    for row in lead_data_doc.lead_data_address or []:
        if row.address_line_1 and row.address_line_1 not in addresses:
            addresses.append(row.address_line_1)
        email = _sanitize_email(row.email_address)
        if email and email not in emails:
            emails.append(email)
        for phone in _sanitize_phone_list(row.phone):
            if phone not in phones:
                phones.append(phone)

    for row in lead_data_doc.lead_data_contact or []:
        name = " ".join(
            part for part in (row.first_name, row.middle_name, row.last_name)
            if part
        ).strip()
        if name and name not in contacts:
            contacts.append(name)
        email = _sanitize_email(row.email_address)
        if email and email not in emails:
            emails.append(email)
        for phone in _sanitize_phone_list(row.phone or row.mobile_no):
            if phone not in phones:
                phones.append(phone)

    if emails:
        company["emails"] = emails
        company["email"] = ", ".join(emails)
    if phones:
        company["phones"] = phones
        company["phone"] = ", ".join(phones)
    if addresses:
        company["addresses"] = addresses
        company["address"] = " | ".join(addresses)
    if contacts:
        company["contact_persons"] = contacts
        company["contact_person"] = contacts[0]

    return company


def _merge_company_lead_data(existing, incoming):
    merged = dict(existing or {})
    _merge_extracted_lead_fields(merged, incoming or {})

    if incoming and incoming.get("website") and not merged.get("website"):
        merged["website"] = incoming.get("website")
    if incoming and incoming.get("company_name") and not merged.get("company_name"):
        merged["company_name"] = incoming.get("company_name")

    return merged



def _format_email_field(value, max_len=140):
    """Join valid emails up to max_len without ever cutting one mid-string."""
    if isinstance(value, str):
        emails = [e.strip() for e in value.split(",") if e.strip()]
    else:
        emails = value or []

    out = []
    for email in emails:
        clean = _sanitize_email(email)
        if not clean or clean in out:
            continue
        candidate = ", ".join(out + [clean])
        if len(candidate) > max_len:
            break
        out.append(clean)

    return ", ".join(out)

def _save_single_company(lead_import_name, company):
    doc = frappe.new_doc("Lead Data")
    doc.lead_import = lead_import_name

    _populate_lead_data_child_tables(doc, company, extracted=company)

    doc.lead_data = _build_import_info(company)
    doc.findings_and_improvements = "Status: Pending"

    doc.insert(ignore_permissions=True)
    frappe.db.commit()


def _truncate(value, max_len=140):
    if not value:
        return ""
    value = str(value).strip()
    if len(value) <= max_len:
        return value
    return value[: max_len - 3].rstrip(", |") + "..."


def _first_value(value, sep=","):
    if not value:
        return ""
    value = str(value)
    if sep in value:
        return value.split(sep)[0].strip()
    return value.strip()


def _build_import_info(company):
    """Build a compact summary string for the lead_import_info field — including all found values."""
    lines = []

    if company.get("company_name"):
        lines.append(f"company_name : {company['company_name']}")

    if company.get("website"):
        lines.append(f"Website : {company['website']}")

    # Multiple emails — agar list available hai to use karo, warna single field
    emails = company.get("emails") or ([company["email"]] if company.get("email") else [])
    if emails:
        lines.append(f"emails ({len(emails)}) :")
        for e in emails:
            clean = _sanitize_email(e)
            if clean:
                lines.append(f"  - {clean}")

    phones = _sanitize_phone_list(company.get("phones") or company.get("phone"))
    if phones:
        lines.append(f"phones ({len(phones)}) :")
        for p in phones:
            lines.append(f"  - {p}")

    contacts = company.get("contact_persons") or ([company["contact_person"]] if company.get("contact_person") else [])
    if contacts:
        lines.append(f"contact_persons ({len(contacts)}) :")
        for c in contacts:
            lines.append(f"  - {c}")

    addresses = company.get("addresses") or ([company["address"]] if company.get("address") else [])
    if addresses:
        lines.append(f"addresses ({len(addresses)}) :")
        for a in addresses:
            lines.append(f"  - {a}")

    return "\n".join(lines)


def _log(lead_import_name, message):
    if not lead_import_name:
        return
    doc = frappe.get_doc("Lead Import", lead_import_name)
    existing = doc.status_log or ""
    new_log = f"{existing}\n{message}".strip()
    frappe.db.set_value("Lead Import", lead_import_name, "status_log", new_log)
    frappe.db.commit()


def _finish(lead_import_name, message):
    frappe.db.set_value("Lead Import", lead_import_name, {
        "status": "Ready",
        "status_log": message,
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
            return result
        if isinstance(result, dict):
            for v in result.values():
                if isinstance(v, list):
                    return v
    except Exception:
        pass
    return []
def _sanitize_email(email):
    if not email:
        return ""

    email = str(email).strip()

    # Common protected emails
    if "protected email" in email.lower():
        return ""

    try:
        validate_email_address(email, throw=True)
        return email
    except Exception:
        return ""
    
@frappe.whitelist()
def re_enrich_incomplete(lead_import_name):
    doc = frappe.get_doc("Lead Import", lead_import_name)
    if doc.status == "Processing":
        frappe.throw(_("Extraction is already running for this document."))

    candidates = frappe.get_all(
        "Lead Data",
        filters={"lead_import": lead_import_name},
        fields=["name", "organization_name", "website", "email", "phone"],
    )
    incomplete = [
        r for r in candidates
        if not r.get("email") or _is_broad_contact_directory({
            "email": r.get("email"),
            "phone": r.get("phone"),
        })
    ]
    # also exclude rows already marked Created/Duplicate (no email but already handled)
    incomplete = [
        r for r in incomplete
        if not frappe.db.get_value("Lead Data", r.name, "findings_and_improvements")
        or "Created" not in (frappe.db.get_value("Lead Data", r.name, "findings_and_improvements") or "")
    ]

    if not incomplete:
        return {"ok": True, "message": "No incomplete rows found."}

    frappe.db.set_value("Lead Import", lead_import_name, {
        "status": "Processing",
        "status_log": f"Re-enriching {len(incomplete)} incomplete rows...",
    })
    frappe.db.commit()

    frappe.enqueue(
        _run_re_enrichment,
        queue="default",
        timeout=600,
        lead_import_name=lead_import_name,
        incomplete_rows=incomplete,
        enqueue_after_commit=True,
    )
    return {"ok": True, "message": f"Re-enrichment started for {len(incomplete)} rows."}

def _reenrich_single_row(settings, slugs, row):
    name = row.get("organization_name") or "Unknown"
    website = row.get("website") or ""

    company = {"company_name": name, "website": website, "phone": row.get("phone") or ""}

    if not website:
        return row["name"], company, {}

    extracted = {}
    base = _get_domain_root(website)
    found_preferred_source = False

    for slug_url in _reference_urls_for_company(base, website, slugs):
        slug_html = _fetch_html(slug_url)
        page_extracted = _extract_lead_fields_from_page(
            settings,
            slug_html,
            name,
            f"Reference page: {slug_url}",
            ai_fallback=True,
            force_ai=_is_preferred_legal_slug(slug_url),
        )
        if not _has_contact_lead_data(page_extracted):
            continue
        if _is_broad_contact_directory(page_extracted) and not _is_preferred_legal_slug(slug_url):
            continue
        if _is_preferred_legal_slug(slug_url):
            _merge_extracted_lead_fields(extracted, page_extracted)
            found_preferred_source = True
        else:
            _merge_extracted_lead_fields(extracted, page_extracted)
        if found_preferred_source and not _has_direct_contact_lead_data(extracted):
            continue
        break

    if (
        website.rstrip("/") != base.rstrip("/")
        and (not found_preferred_source or not _has_direct_contact_lead_data(extracted))
    ):
        orig_html = _fetch_html(website)
        page_extracted = _extract_lead_fields_from_page(
            settings,
            orig_html,
            name,
            f"Original page: {website}",
            ai_fallback=True,
        )
        if _has_contact_lead_data(page_extracted) and not _is_broad_contact_directory(page_extracted):
            _merge_extracted_lead_fields(extracted, page_extracted)

    if not _has_direct_contact_lead_data(extracted):
        main_html = _fetch_html(base)
        crawl_links = _discover_internal_links(base, main_html, limit=FAST_REEXTRACT_CRAWL_LIMIT)
        for link in crawl_links:
            page_html = _fetch_html(link)
            page_extracted = _extract_lead_fields_from_page(
                settings,
                page_html,
                name,
                f"crawl: {link}",
                ai_fallback=True,
                force_ai=_is_preferred_legal_slug(link),
            )
            if _is_broad_contact_directory(page_extracted) and not _is_preferred_legal_slug(link):
                continue
            _merge_extracted_lead_fields(extracted, page_extracted)
            if _has_direct_contact_lead_data(extracted):
                break

    return row["name"], company, extracted


def _run_re_enrichment(lead_import_name, incomplete_rows):
    try:
        settings = _get_phamos_settings()
        if not settings:
            _finish(lead_import_name, "Error: Mistral API key not configured.")
            return

        doc = frappe.get_doc("Lead Import", lead_import_name)
        raw_refs = doc.reference_urls or ""
        slugs = [s.strip().strip("/") for s in raw_refs.splitlines() if s.strip() and not s.strip().startswith("#")]

        total = len(incomplete_rows)
        updated = 0
        workers = min(ENRICHMENT_WORKERS, total) or 1

        _log(lead_import_name, f"Re-enriching {total} rows with {workers} workers.")

        with ThreadPoolExecutor(max_workers=workers) as executor:
            future_map = {
                executor.submit(_reenrich_single_row, settings, slugs, row): row
                for row in incomplete_rows
            }

            for idx, future in enumerate(as_completed(future_map), start=1):
                row = future_map[future]
                name = row.get("organization_name") or "Unknown"
                try:
                    row_name, company, extracted = future.result()
                except Exception:
                    frappe.log_error(title=_("Lead Import re-enrichment row failed"), message=frappe.get_traceback())
                    _log(lead_import_name, f"[{idx}/{total}] [{name}] Error")
                    continue

                if not extracted:
                    _log(lead_import_name, f"[{idx}/{total}] [{name}] No data found")
                    continue

                lead_data_doc = frappe.get_doc("Lead Data", row_name)
                existing = _lead_data_doc_to_company(lead_data_doc)
                merged = _merge_company_lead_data(existing, {**company, **extracted})
                _populate_lead_data_child_tables(lead_data_doc, merged, extracted=merged)
                lead_data_doc.lead_data = _build_import_info(merged)
                lead_data_doc.save(ignore_permissions=True)
                frappe.db.commit()

                updated += 1
                _log(lead_import_name, f"[{idx}/{total}] ✓ [{name}] Updated")

        _finish(lead_import_name, f"Re-enrichment done. Updated {updated}/{total} rows.")

    except Exception:
        tb = frappe.get_traceback()
        frappe.log_error(title=_("Lead Import re-enrichment failed"), message=tb)
        _finish(lead_import_name, "Error during re-enrichment. Check Error Log.")

    except Exception:
        tb = frappe.get_traceback()
        frappe.log_error(title=_("Lead Import re-enrichment failed"), message=tb)
        _finish(lead_import_name, "Error during re-enrichment. Check Error Log.")

def _discover_internal_links(base_url, html, limit=8):
    """Same-domain links nikaalo jab koi slug data na de — fallback crawl ke liye."""
    if not html:
        return []

    from urllib.parse import urljoin, urlparse

    domain = urlparse(base_url).netloc.replace("www.", "")
    skip_ext = (".jpg", ".jpeg", ".png", ".gif", ".svg", ".pdf", ".zip", ".css", ".js")
    skip_kw = ("facebook.", "twitter.", "instagram.", "linkedin.", "youtube.",
               "mailto:", "tel:", "#", "javascript:")

    links = re.findall(r'<a\s+[^>]*href=["\']([^"\']+)["\']', html, flags=re.IGNORECASE)
    seen, result = set(), []

    priority_kw = (
        "contact", "kontakt", "impressum", "imprint", "legal",
        "about", "ueber", "uber", "team"
    )

    def score_href(href):
        low = href.lower()
        for idx, keyword in enumerate(priority_kw):
            if keyword in low:
                return idx
        return len(priority_kw)

    for href in sorted(links, key=score_href):
        low = href.lower()
        if any(k in low for k in skip_kw) or low.endswith(skip_ext):
            continue

        full = urljoin(base_url, href)
        parsed = urlparse(full)
        if domain not in parsed.netloc.replace("www.", ""):
            continue

        path = parsed.path.rstrip("/")
        if not path or path == "" :
            continue

        if full not in seen:
            seen.add(full)
            result.append(full)

        if limit and len(result) >= limit:
            break

    return result


def _discover_legal_links(base_url, html, limit=6):
    if not html:
        return []

    from urllib.parse import urljoin, urlparse

    domain = urlparse(base_url).netloc.replace("www.", "")
    keywords = ("impressum", "imprint", "legal")
    links = re.findall(r'<a\s+[^>]*href=["\']([^"\']+)["\']', html, flags=re.IGNORECASE)
    seen, result = set(), []

    for href in links:
        low = href.lower()
        if not any(keyword in low for keyword in keywords):
            continue
        if low.startswith(("mailto:", "tel:", "#", "javascript:")):
            continue

        full = urljoin(base_url, href)
        parsed = urlparse(full)
        if domain not in parsed.netloc.replace("www.", ""):
            continue
        if full not in seen:
            seen.add(full)
            result.append(full)
        if limit and len(result) >= limit:
            break

    return result
