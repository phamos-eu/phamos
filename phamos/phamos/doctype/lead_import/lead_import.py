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
    country = _normalize_country(parts[-1]) if parts and _is_country_value(parts[-1]) else ""
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


def _clean_address_values(values):
    addresses = []
    if isinstance(values, str):
        values = re.split(r"\s*(?:\||\n)\s*", values)

    for value in values or []:
        text = str(value or "").strip()
        if not text:
            continue

        compact_addresses = _extract_addresses_from_text(text) if len(text) > 140 else []
        candidates = compact_addresses or [text]
        for candidate in candidates:
            clean = re.sub(r"\s+", " ", str(candidate or "")).strip(" ,.;")
            if clean and clean not in addresses:
                addresses.append(clean)

    return addresses


def _address_line_for_child(address):
    """Return a Data-field-safe address line without surrounding legal prose."""
    text = str(address or "").strip()
    if not text:
        return ""

    extracted = _extract_addresses_from_text(text)
    if extracted:
        text = extracted[0]

    return _truncate(text)


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


def _is_country_value(value):
    raw = str(value or "").strip()
    clean = re.sub(r"[^A-Za-zÀ-ÖØ-öø-ÿ]", "", raw).lower()
    if clean in COUNTRY_ALIASES:
        return True

    lowered = raw.lower()
    return any(re.search(rf"\b{re.escape(alias)}\b", lowered) for alias in COUNTRY_ALIASES)


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

    attachments = _as_unique_list(company.get("source_attachments") or company.get("source_attachment"))
    if attachments:
        lead_data_doc.set("lead_data_attachment", [])
        for attachment in attachments:
            lead_data_doc.append("lead_data_attachment", {
                "lead_data_attachment": attachment,
            })

    emails = extracted.get("emails") or ([company["email"]] if company.get("email") else [])
    phones = _sanitize_phone_list(extracted.get("phones") or company.get("phone"))
    addresses = _clean_address_values(
        extracted.get("addresses") or ([company["address"]] if company.get("address") else [])
    )

    clean_emails = []
    for e in emails:
        ce = _sanitize_email(e)
        if ce and ce not in clean_emails:
            clean_emails.append(ce)

    if addresses:
        for idx, addr in enumerate(addresses):
            address_parts = _parse_address_components(addr)
            lead_data_doc.append("lead_data_address", {
                "address_title": _truncate(company.get("company_name")),
                "address_line_1": _address_line_for_child(addr),
                "citytown": _truncate(address_parts.get("city")),
                "stateprovince": _truncate(address_parts.get("state")),
                "country": _truncate(address_parts.get("country")),
                "postal_code": _truncate(address_parts.get("postal_code")),
                "email_address": _truncate(clean_emails[idx]) if idx < len(clean_emails) else (_truncate(clean_emails[0]) if clean_emails else ""),
                "phone": _truncate(phones[idx]) if idx < len(phones) else "",
            })
    elif clean_emails or phones:
        lead_data_doc.append("lead_data_address", {
            "address_title": _truncate(company.get("company_name")),
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
            "designation": _truncate(company.get("job_title")),
        })

    if contacts:
        parts = str(contacts[0]).strip().split(" ", 1)
        lead_data_doc.first_name = _truncate(parts[0])
        lead_data_doc.last_name = _truncate(parts[1] if len(parts) > 1 else "")
    lead_data_doc.job_title = _truncate(company.get("job_title"))
    lead_data_doc.organization_name = _truncate(company.get("company_name"))
    lead_data_doc.website = _truncate(main_site)
    lead_data_doc.email = _truncate(clean_emails[0]) if clean_emails else ""
    lead_data_doc.phone = _truncate(phones[0]) if phones else ""
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

        if not companies and input_type == "URL":
            _log(lead_import_name, "No companies detected. Treating source URL as one company website.")
            companies = [_company_from_website_html(None, doc.source_url)]

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
        _finish(lead_import_name, _format_error_for_status("Error during extraction.", tb))


# Pipeline: URL

def _pipeline_url(lead_import_name, url):
    if not url:
        frappe.throw(_("Source URL is required for URL input type."))

    _log(lead_import_name, f"Scraping: {url}")
    html = _fetch_html(url)
    if not html:
        _log(lead_import_name, "Could not fetch the page HTML. Treating URL as one company website.")
        return [_company_from_website_html(None, url)]

    companies = _extract_companies_from_partner_html(html, url, ai_fallback=False)

    if not companies:
        companies = _extract_companies_from_links_and_logos(html, url)
        if companies and not _should_treat_as_directory(html, companies):
            companies = []

    if not companies:
        _log(lead_import_name, "No companies in static HTML. Trying JS render...")
        html = _fetch_html(url, js_render=True)
        if html:
            companies = _extract_companies_from_partner_html(html, url, ai_fallback=False)
            if not companies:
                companies = _extract_companies_from_links_and_logos(html, url)
                if companies and not _should_treat_as_directory(html, companies):
                    companies = []
            if not companies and _has_directory_page_signals(html):
                companies = _mistral_extract_companies_from_html(html, url)

    if not companies:
        _log(lead_import_name, "No directory companies found. Treating URL as one company website.")
        companies = [_company_from_website_html(html, url)]

    for company in companies:
        if not company.get("website"):
            company["website"] = _infer_or_search_website(company)

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
    partner_blocks = []

    for block in blocks:
        if 'gallery-item-partner' not in block:
            continue

        partner_blocks.append(block)
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
        filename = _clean_asset_filename(img_src)
        filename = re.sub(r'^logo[-_ ]*', '', filename, flags=re.I)
        company_name = filename.replace("_", " ").title().strip()

        if company_name and href:
            companies.append({"company_name": company_name, "website": href})

    # Fallback to Mistral if regex found nothing
    if ai_fallback and not companies:
        companies = _mistral_extract_companies_from_html(html, page_url)

    if not companies and partner_blocks:
        for company in _extract_companies_from_images("\n".join(partner_blocks)):
            key = (company.get("company_name") or "").lower()
            if key and key not in {c.get("company_name", "").lower() for c in companies}:
                companies.append(company)

    return _filter_company_candidates(companies, page_url)


def _extract_companies_from_links_and_logos(html, page_url):
    """Generic directory fallback for pages that list partners as plain links/logos."""
    if not html:
        return []

    page_domain = _normalized_domain(page_url)
    companies = []
    seen_domains = set()

    for match in re.finditer(r"<a\b(?P<attrs>[^>]*)>(?P<body>.*?)</a>", html, flags=re.I | re.S):
        attrs = match.group("attrs") or ""
        body = match.group("body") or ""
        href_match = re.search(r'href=["\']([^"\']+)["\']', attrs, flags=re.I)
        if not href_match:
            continue

        href = html_lib.unescape(href_match.group(1).strip())
        if _skip_company_candidate_href(href):
            continue

        full_url = urljoin(page_url, href)
        website = _normalize_url(full_url)
        parsed = urlparse(website)
        domain = _normalized_domain(website)
        if not parsed.scheme or not parsed.netloc or not domain:
            continue
        if domain == page_domain or _is_noise_domain(domain):
            continue
        if domain in seen_domains:
            continue

        company_name = _company_name_from_anchor(body, website)
        if not company_name:
            continue

        seen_domains.add(domain)
        companies.append({
            "company_name": company_name,
            "website": _get_domain_root(website) or website,
        })

    return companies


def _should_treat_as_directory(html, companies):
    """Decide whether generic external links are directory entries or just outbound site links."""
    if not companies:
        return False

    return _has_directory_page_signals(html)


def _filter_company_candidates(companies, page_url=None):
    filtered = []
    seen = set()

    for company in companies or []:
        website = _normalize_url(company.get("website"))
        domain = _normalized_domain(website)
        name = _clean_company_candidate_text(company.get("company_name"))
        if domain and _is_noise_domain(domain):
            continue
        if name and not _is_probable_company_name(name):
            continue
        if not website and not name:
            continue

        key = domain or name.lower()
        if key in seen:
            continue
        seen.add(key)

        clean_company = dict(company)
        clean_company["company_name"] = name or _domain_to_company_name(website)
        clean_company["website"] = (_get_domain_root(website) or website) if website else ""
        filtered.append(clean_company)

    return filtered


def _has_directory_page_signals(html):
    text = _clean_html(html).lower()
    signals = (
        "partner", "partners", "sponsor", "sponsoren", "aussteller",
        "exhibitor", "exhibitors", "mitglieder", "members", "member directory",
        "partnernetzwerk", "kooperationspartner", "referenzen",
    )
    return any(re.search(rf"\b{re.escape(signal)}\b", text) for signal in signals)


def _company_from_website_html(html, page_url):
    name = ""
    if html:
        title = re.search(r"<title[^>]*>(.*?)</title>", html, flags=re.I | re.S)
        h1 = re.search(r"<h1[^>]*>(.*?)</h1>", html, flags=re.I | re.S)
        source = h1.group(1) if h1 else (title.group(1) if title else "")
        name = _clean_company_candidate_text(source)

    if not name:
        name = _domain_to_company_name(page_url)

    return {
        "company_name": name,
        "website": _normalize_url(page_url),
    }


def _company_name_from_anchor(body, website):
    candidates = []

    text = _clean_company_candidate_text(body)
    if text:
        candidates.append(text)

    for pattern in (r'alt=["\']([^"\']+)["\']', r'title=["\']([^"\']+)["\']', r'aria-label=["\']([^"\']+)["\']'):
        for value in re.findall(pattern, body, flags=re.I):
            clean = _clean_company_candidate_text(value)
            if clean:
                candidates.append(clean)

    for candidate in candidates:
        if _is_probable_company_name(candidate):
            return candidate

    if candidates:
        return ""

    return _domain_to_company_name(website)


def _extract_companies_from_images(html):
    companies = []
    seen = set()

    for img_match in re.finditer(r"<img\b(?P<attrs>[^>]*)>", html or "", flags=re.I | re.S):
        attrs = img_match.group("attrs") or ""
        candidates = []
        for pattern in (r'alt=["\']([^"\']+)["\']', r'title=["\']([^"\']+)["\']'):
            candidates.extend(re.findall(pattern, attrs, flags=re.I))

        src_match = re.search(r'src=["\']([^"\']+)["\']', attrs, flags=re.I)
        if src_match:
            filename = _clean_asset_filename(src_match.group(1))
            filename = re.sub(r"^(?:logo|partner|sponsor)[-_ ]*", "", filename, flags=re.I)
            filename = re.sub(r"[_-]+", " ", filename)
            candidates.append(filename)

        for candidate in candidates:
            company_name = _clean_company_candidate_text(candidate)
            if not _is_probable_company_name(company_name):
                continue
            key = company_name.lower()
            if key in seen:
                continue
            seen.add(key)
            companies.append({"company_name": company_name, "website": ""})
            break

    return companies


def _clean_asset_filename(value):
    filename = os.path.basename(urlparse(str(value or "")).path)
    filename = re.sub(r"\.[a-z0-9]{2,5}$", "", filename, flags=re.I)
    filename = re.sub(r"^csm_", "", filename, flags=re.I)
    filename = re.sub(r"[_-][a-f0-9]{8,}$", "", filename, flags=re.I)
    return filename


def _clean_company_candidate_text(value):
    text = html_lib.unescape(str(value or ""))
    text = re.sub(r"<(script|style)[^>]*>.*?</(script|style)>", " ", text, flags=re.I | re.S)
    text = re.sub(r"<[^>]+>", " ", text)
    text = re.sub(r"https?://\S+|www\.\S+", " ", text, flags=re.I)
    text = re.sub(r"\s+", " ", text).strip(" \t\r\n-|:;.,")
    return text[:140]


def _is_probable_company_name(value):
    text = str(value or "").strip()
    if len(text) < 2 or len(text) > 140:
        return False
    if not re.search(r"[A-Za-zÀ-ÖØ-öø-ÿ]", text):
        return False

    lowered = text.lower()
    noise = (
        "mehr erfahren", "learn more", "read more", "weiter", "kontakt",
        "contact", "impressum", "privacy", "datenschutz", "linkedin",
        "facebook", "instagram", "youtube", "anmelden", "login",
        "logo", "image", "bild", "partner", "sponsor", "shop",
        "handler", "haendler", "händler", "handler shop", "haendler shop",
        "händler shop", "dealer shop", "online shop", "store", "portal",
        "whatsapp", "link zu whatsapp", "review", "reviews", "bewertung",
        "bewertungen",
    )
    return not any(item == lowered or item in lowered for item in noise)


def _domain_to_company_name(url):
    domain = _normalized_domain(url)
    if not domain:
        return "Unknown"

    label = domain.split(".")[0]
    return re.sub(r"[-_]+", " ", label).title()


def _normalized_domain(url):
    parsed = urlparse(_normalize_url(url) or url)
    return (parsed.netloc or "").lower().replace("www.", "").strip()


def _skip_company_candidate_href(href):
    low = (href or "").strip().lower()
    return (
        not low
        or low.startswith(("mailto:", "tel:", "#", "javascript:"))
        or low.endswith((".jpg", ".jpeg", ".png", ".gif", ".svg", ".webp", ".pdf", ".zip", ".css", ".js"))
    )


def _is_noise_domain(domain):
    noise_domains = (
        "facebook.com", "instagram.com", "linkedin.com", "youtube.com",
        "youtu.be", "twitter.com", "x.com", "tiktok.com", "eventbrite.",
        "pretix.", "google.", "maps.google.", "apple.com", "microsoft.com",
        "whatsapp.com", "wa.me", "ekomi.", "trustpilot.", "trustedshops.",
        "paypal.", "klarna.",
    )
    return any(noise in domain for noise in noise_domains)


# Pipeline: Screenshot

def _pipeline_screenshot(lead_import_name, file_url):
    if not file_url:
        frappe.throw(_("Please upload a screenshot file."))

    _log(lead_import_name, "Reading screenshot/business card via Mistral vision...")
    image_b64, mime = _load_file_as_base64(file_url)
    if not image_b64:
        _log(lead_import_name, "Could not read uploaded file.")
        return []

    qr_urls = _decode_qr_urls_from_file(file_url)
    if qr_urls:
        _log(lead_import_name, f"QR website found: {qr_urls[0]}")

    companies = _mistral_extract_companies_from_image(image_b64, mime, qr_urls=qr_urls)
    for company in companies:
        if not company.get("website") and qr_urls:
            company["website"] = qr_urls[0]
        if not company.get("website"):
            company["website"] = _infer_or_search_website(company)
        company["source_attachment"] = file_url

    _log(lead_import_name, f"Mistral identified {len(companies)} lead(s) in the screenshot.")
    return companies if not MAX_COMPANIES_PER_IMPORT else companies[:MAX_COMPANIES_PER_IMPORT]

# Pipeline: PDF

def _pipeline_pdf(lead_import_name, file_url):
    if not file_url:
        frappe.throw(_("Please upload a PDF file."))

    _log(lead_import_name, "Running OCR on PDF via Mistral...")

    settings = _get_phamos_settings()
    if not settings:
        frappe.throw(_("Mistral API key is not configured in phamos Settings."))

    path = _get_file_path_from_url(file_url)

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
                    tb = frappe.get_traceback()
                    frappe.log_error(
                        title=_("Lead Import company enrichment failed"),
                        message=tb,
                    )
                    _log(
                        lead_import_name,
                        _format_error_for_status(f"[{idx}/{total}] {name} enrichment error.", tb),
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
                ai_fallback=ai_fallback,
                force_ai=_is_preferred_legal_slug(link),
            )
            if _is_broad_contact_directory(page_extracted) and not _is_preferred_legal_slug(link):
                continue
            if _has_contact_lead_data(page_extracted):
                _merge_extracted_lead_fields(extracted, page_extracted)
                sources_found.append(link)
            if _has_direct_contact_lead_data(extracted):
                break

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

    return _filter_company_candidates(_call_mistral_json_list(settings, prompt), page_url)


def _mistral_extract_companies_from_image(image_b64, mime, qr_urls=None):
    settings = _get_phamos_settings()
    if not settings:
        frappe.throw(_("Mistral API key is not configured."))

    model = settings["model"]
    if "ocr" in model.lower():
        model = MISTRAL_CHAT_MODEL_DEFAULT

    qr_hint = "\n".join(qr_urls or [])
    prompt = f"""You are analyzing a screenshot. It may be a single business card, or it may be a company directory/partner listing page.

If it is a business card, return exactly ONE object for the card.
If it is a directory/listing screenshot, return one object per visible company.

Extract only details visible in the image, plus QR URL hints provided below.
Use a QR URL as website when it is present.

Return ONLY a valid JSON array, no explanation, no markdown.
Format:
[
  {{
    "company_name": "Radio Neckaralb Live GmbH & Co. KG",
    "website": "https://example.com",
    "emails": ["name@example.com"],
    "phones": ["+49 7121 9458900"],
    "contact_persons": ["Bianca Rösch"],
    "addresses": ["Obere Wässere 6-8, 72764 Reutlingen"],
    "job_title": "Mediaberaterin",
    "source_type": "business_card"
  }}
]

If a field is not visible, use an empty string or empty array.
Never invent phone numbers, emails, people, or addresses.

QR URL hints:
---
{qr_hint}
---"""

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
    companies = _parse_json_list(content)
    return [
        _normalize_company_dict(company)
        for company in companies
        if company.get("company_name") or company.get("website")
    ]


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

        clean_emails = [_sanitize_email(e) for e in emails if _sanitize_email(e)]
        result["email"] = clean_emails[0] if clean_emails else ""
        result["phones"] = phones
        result["phone"] = phones[0] if phones else ""
        result["contact_person"] = contacts[0] if contacts else ""
        result["address"] = addresses[0] if addresses else ""

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
    for match in re.finditer(r"(?:\+|00)?\d[\d\s()./\-–—]{6,}\d", text):
        context = text[max(0, match.start() - 40):match.start()].lower()
        if "fax" in context:
            continue
        phone = _sanitize_phone(match.group(0))
        if phone and phone not in phones:
            phones.append(phone)

    addresses = _extract_addresses_from_text(text)

    out = {}
    if emails:
        out["emails"] = emails
        out["email"] = emails[0]
    if phones:
        out["phones"] = phones
        out["phone"] = phones[0]
    if addresses:
        out["addresses"] = addresses
        out["address"] = addresses[0]
    return out


def _extract_addresses_from_text(text):
    if not text:
        return []

    street_words = (
        r"(?:str(?:aße|asse|\.?)|weg|platz|allee|gasse|ring|damm|ufer|"
        r"chaussee|markt|hof|steig|pfad|bogen|zeile)"
    )
    pattern = (
        rf"\b([A-ZÄÖÜ][A-Za-zÀ-ÖØ-öø-ÿ0-9 .'\-]+?{street_words}\s+"
        rf"\d+[A-Za-z]?(?:\s*[-/]\s*\d+[A-Za-z]?)?)\s*,?\s+"
        rf"((?:[A-Z]{1,3}-)?\d{{4,6}}\s+[A-ZÄÖÜ][A-Za-zÀ-ÖØ-öø-ÿ .'\-]+)"
    )

    addresses = []
    for match in re.finditer(pattern, text, flags=re.I):
        street = re.sub(r"\s+", " ", match.group(1)).strip(" ,.;")
        street = re.split(r"[.;]\s+", street)[-1].strip(" ,.;")
        city = re.sub(r"\s+", " ", match.group(2)).strip(" ,.;")
        city = re.split(
            r"\s+(?:tel|telefon|phone|fax|e-?mail|mail|kontakt|contact|"
            r"öffnungszeiten|opening|www\.|https?://)\b",
            city,
            maxsplit=1,
            flags=re.I,
        )[0].strip(" ,.;")
        address = f"{street}, {city}"
        if re.search(r"\b(?:[A-Z]{1,3}-)?\d{4,6}\s+[A-ZÄÖÜ]", city) and address not in addresses:
            addresses.append(address)

    return addresses


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
    seen_digits = set()
    for phone in values:
        clean_phone = _sanitize_phone(phone)
        if not clean_phone:
            continue

        digits_key = re.sub(r"\D", "", clean_phone)
        if digits_key in seen_digits:
            continue

        seen_digits.add(digits_key)
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

    path = _get_file_path_from_url(file_url)

    if not path or not os.path.isfile(path):
        return None, None

    ext = os.path.splitext(path)[1].lower()
    mime_map = {".png": "image/png", ".jpg": "image/jpeg", ".jpeg": "image/jpeg", ".webp": "image/webp"}
    mime = mime_map.get(ext, "image/png")

    with open(path, "rb") as f:
        return base64.b64encode(f.read()).decode("utf-8"), mime


def _get_file_path_from_url(file_url):
    if not file_url:
        return ""

    url = file_url.strip().lstrip("/")
    if url.startswith("private/files/"):
        return get_files_path(*url.replace("private/files/", "", 1).split("/"), is_private=1)
    return get_files_path(*url.replace("files/", "", 1).split("/"))


def _decode_qr_urls_from_file(file_url):
    """Best-effort QR decoding. Works when cv2 or pyzbar is installed."""
    path = _get_file_path_from_url(file_url)
    if not path or not os.path.isfile(path):
        return []

    decoded = []

    try:
        import cv2

        image = cv2.imread(path)
        if image is not None:
            detector = cv2.QRCodeDetector()
            data, _, _ = detector.detectAndDecode(image)
            if data:
                decoded.append(data)
    except Exception:
        pass

    if not decoded:
        try:
            from PIL import Image
            from pyzbar.pyzbar import decode

            for item in decode(Image.open(path)):
                data = item.data.decode("utf-8", errors="ignore")
                if data:
                    decoded.append(data)
        except Exception:
            pass

    urls = []
    for value in decoded:
        url = _normalize_url(value)
        if url and url not in urls:
            urls.append(url)
    return urls


def _normalize_url(value):
    value = str(value or "").strip()
    if not value:
        return ""

    match = re.search(r"https?://[^\s<>\"]+", value, flags=re.I)
    if match:
        return match.group(0).rstrip(".,;)")

    match = re.search(r"\b(?:www\.)?[a-z0-9][a-z0-9.-]+\.[a-z]{2,}(?:/[^\s<>\"]*)?", value, flags=re.I)
    if match:
        url = match.group(0).rstrip(".,;)")
        return url if url.startswith(("http://", "https://")) else f"https://{url}"

    return ""


def _infer_or_search_website(company):
    website = _normalize_url(company.get("website"))
    if website:
        return website

    for email in company.get("emails") or _split_email_values(company.get("email")):
        clean = _sanitize_email(email)
        if not clean or "@" not in clean:
            continue
        domain = clean.split("@", 1)[1].lower()
        if domain not in FREE_EMAIL_DOMAINS:
            return f"https://{domain}"

    return _search_company_website(company)


def _search_company_website(company):
    name = (company.get("company_name") or "").strip()
    if not name:
        return ""

    location_bits = []
    for address in company.get("addresses") or ([company.get("address")] if company.get("address") else []):
        parsed = _parse_address_components(address)
        if parsed.get("city"):
            location_bits.append(parsed["city"])

    query = " ".join([name] + location_bits + ["official website"])
    search_url = f"https://duckduckgo.com/html/?q={quote_plus(query)}"
    html = _fetch_html(search_url)
    if not html:
        return ""

    candidates = []
    for href in re.findall(r'href=["\']([^"\']+)["\']', html, flags=re.I):
        if "uddg=" in href:
            parsed = urlparse(href)
            uddg = parse_qs(parsed.query).get("uddg")
            if uddg:
                candidates.append(unquote(uddg[0]))
                continue
        if href.startswith("http"):
            candidates.append(href)
    blocked_domains = (
        "duckduckgo.com", "google.", "bing.com", "facebook.com", "instagram.com",
        "linkedin.com", "youtube.com", "twitter.com", "x.com",
    )
    for candidate in candidates:
        url = _normalize_url(candidate)
        parsed = urlparse(url)
        if not parsed.netloc:
            continue
        host = parsed.netloc.lower().replace("www.", "")
        if any(blocked in host for blocked in blocked_domains):
            continue
        return _get_domain_root(url) or url

    return ""

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

    for slug in (
        "meta/impressum", "impressum", "imprint", "legal",
        "kontakt", "contact", "contact-us", "about", "about-us",
        "ueber-uns", "uber-uns", "team",
    ):
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


def _as_unique_list(value):
    if not value:
        return []

    values = value if isinstance(value, list) else [value]
    out = []
    for item in values:
        clean = str(item or "").strip()
        if clean and clean not in out:
            out.append(clean)
    return out


def _normalize_company_dict(company):
    company = dict(company or {})
    company["website"] = _normalize_url(company.get("website"))

    emails = []
    for email in company.get("emails") or _split_email_values(company.get("email")):
        clean = _sanitize_email(email)
        if clean and clean not in emails:
            emails.append(clean)
    company["emails"] = emails
    company["email"] = emails[0] if emails else ""

    phones = _sanitize_phone_list(company.get("phones") or company.get("phone"))
    company["phones"] = phones
    company["phone"] = phones[0] if phones else ""

    contacts = company.get("contact_persons") or ([company.get("contact_person")] if company.get("contact_person") else [])
    company["contact_persons"] = _as_unique_list(contacts)
    if company["contact_persons"]:
        company["contact_person"] = company["contact_persons"][0]

    addresses = company.get("addresses") or ([company.get("address")] if company.get("address") else [])
    company["addresses"] = _clean_address_values(addresses)
    if company["addresses"]:
        company["address"] = company["addresses"][0]

    return company


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
        company["email"] = emails[0]
    if phones:
        company["phones"] = phones
        company["phone"] = phones[0]
    if addresses:
        company["addresses"] = addresses
        company["address"] = addresses[0]
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
    lines = []

    if company.get("company_name"):
        lines.append(f"company_name : {company['company_name']}")

    if company.get("website"):
        lines.append(f"Website : {company['website']}")

    if company.get("job_title"):
        lines.append(f"job_title : {company['job_title']}")

    attachments = _as_unique_list(company.get("source_attachments") or company.get("source_attachment"))
    if attachments:
        lines.append("attachments :")
        for attachment in attachments:
            lines.append(f"  - {attachment}")

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


def _format_error_for_status(message, traceback_text=None, max_len=6000):
    details = str(traceback_text or "").strip()
    if not details:
        return message

    if len(details) > max_len:
        details = "...\n" + details[-max_len:]

    return f"{message}\n\nDetails:\n{details}"


def _finish(lead_import_name, message):
    doc = frappe.get_doc("Lead Import", lead_import_name)
    existing = (doc.status_log or "").strip()
    status_log = f"{existing}\n{message}".strip() if existing else message
    frappe.db.set_value("Lead Import", lead_import_name, {
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
                    tb = frappe.get_traceback()
                    frappe.log_error(title=_("Lead Import re-enrichment row failed"), message=tb)
                    _log(
                        lead_import_name,
                        _format_error_for_status(f"[{idx}/{total}] [{name}] Error", tb),
                    )
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
        _finish(lead_import_name, _format_error_for_status("Error during re-enrichment.", tb))

    except Exception:
        tb = frappe.get_traceback()
        frappe.log_error(title=_("Lead Import re-enrichment failed"), message=tb)
        _finish(lead_import_name, _format_error_for_status("Error during re-enrichment.", tb))

def _discover_internal_links(base_url, html, limit=8):
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
