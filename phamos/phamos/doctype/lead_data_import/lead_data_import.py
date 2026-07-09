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
    pass
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

    if not country and postal_code and re.fullmatch(r"\d{5}", postal_code):
        country = "Germany"

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

    seen = {}
    for value in values or []:
        text = str(value or "").strip()
        if not text:
            continue

        compact_addresses = _extract_addresses_from_text(text) if len(text) > 140 else []
        candidates = compact_addresses or [text]
        for candidate in candidates:
            clean = _normalize_address_candidate(candidate)
            key = _address_dedupe_key(clean)
            if clean and key and key not in seen:
                seen[key] = len(addresses)
                addresses.append(clean)
            elif clean and key:
                existing_idx = seen[key]
                existing = addresses[existing_idx]
                if not _parse_address_components(existing).get("country") and _parse_address_components(clean).get("country"):
                    addresses[existing_idx] = clean

    return addresses
def _address_line_for_child(address):
    """Return a Data-field-safe address line without surrounding legal prose."""
    text = str(address or "").strip()
    if not text:
        return ""

    extracted = _extract_addresses_from_text(text)
    if extracted:
        text = extracted[0]

    text = _street_line_from_address(text)
    return _truncate(text)
def _street_line_from_address(address):
    text = str(address or "").strip()
    if not text:
        return ""

    text = re.split(r",?\s+(?:[A-Z]{1,3}-)?\d{4,6}\s+[A-ZÄÖÜ]", text, maxsplit=1)[0]
    return re.sub(r"\s+", " ", text).strip(" ,.;")
def _normalize_address_candidate(address):
    text = str(address or "").strip()
    if not text:
        return ""

    text = html_lib.unescape(text)
    text = re.sub(r"\s+", " ", text).strip(" ,.;")

    # Some Impressum pages concatenate company/legal text with the street
    # address, e.g. "KGWiderholdstraße 2072336 Balingen".
    text = _repair_compact_german_address_spacing(text)
    extracted = _extract_addresses_from_text(text)
    if extracted:
        text = extracted[0]

    text = _repair_compact_german_address_spacing(text)
    text = _strip_address_company_prefix(text)
    text = re.sub(r"\s+", " ", text).strip(" ,.;")
    text = _trim_address_after_postal_city(text)
    text = re.sub(
        r"\s+(?:anfahrt(?:\s+mit\s+google\s+maps)?|google\s+maps|social\s+media|"
        r"route|directions|karte|map|tel|telefon|phone|fax|e-?mail|mail|"
        r"kontakt|contact|poststelle|vat(?:\s+id)?|ust-?id|ust\.?-?idnr|"
        r"sales\s+tax|tax\s+identification|commercial\s+register|registergericht|"
        r"handelsregister|managing\s+director|geschaftsfuhrer|geschäftsführer)\b.*$",
        "",
        text,
        flags=re.I,
    ).strip(" ,.;")
    text = _trim_address_after_postal_city(text)

    if not _looks_like_postal_address(text):
        return ""

    text = _append_country_from_text(text)
    return text if _looks_like_postal_address(text) else ""
def _trim_address_after_postal_city(text):
    text = str(text or "").strip(" ,.;")
    if not text:
        return ""

    match = re.search(
        r"^(?P<prefix>.*?\b(?:[A-Z]{1,3}-)?\d{4,6}\s+"
        r"[A-ZÄÖÜ][A-Za-zÀ-ÖØ-öø-ÿ .'-]+?)"
        r"(?=\s+(?:der|die|das|website|impressum|datenschutz|erklarung|erklärung|"
        r"recht|barrierefreiheit|kontakt|anfahrt|route|vat(?:\s+id)?|ust-?id|ust\.?-?idnr|sales\s+tax|tax\s+identification|"
        r"commercial\s+register|registergericht|handelsregister|managing\s+director|"
        r"geschaftsfuhrer|geschäftsführer|phone|telefon|tel|fax|email|e-?mail)\b|$)",
        text,
        flags=re.I,
    )
    if match:
        return re.sub(r"\s+", " ", match.group("prefix")).strip(" ,.;")

    return text
def _repair_compact_german_address_spacing(text):
    street_words = (
        r"str(?:aße|asse|\.?)|weg|platz|allee|gasse|ring|damm|ufer|"
        r"chaussee|markt|hof|steig|pfad|bogen|zeile"
    )

    text = re.sub(
        rf"\b(gmbh|kg|ag|ohg|ug|se|co)(?=[A-ZÄÖÜ][A-Za-zÄÖÜäöüß.'\-]*(?:{street_words})\b)",
        r"\1 ",
        str(text or ""),
        flags=re.I,
    )

    # Insert a missing separator between a street number and a 5 digit German ZIP.
    def split_number_zip(match):
        digits = match.group("digits")
        return f"{match.group('prefix')}{digits[:-5]} {digits[-5:]} "

    text = re.sub(
        rf"(?P<prefix>\b[A-Za-zÄÖÜäöüß .'\-]*?(?:{street_words})\s+)(?P<digits>\d{{6,9}})\s+",
        split_number_zip,
        text,
        flags=re.I,
    )

    # Drop legal/company prose before the last visible street token.
    street_matches = list(re.finditer(rf"\b[A-Za-zÄÖÜäöüß .'\-]*?(?:{street_words})\s+\d+", text, flags=re.I))
    if street_matches:
        match = street_matches[-1]
        text = f"{_compact_street_name(match.group(0))}{text[match.end():]}"

    return text
def _compact_street_name(street):
    text = re.sub(r"\s+", " ", str(street or "")).strip(" ,.;")
    if not text:
        return ""

    match = re.search(r"^(?P<name>.+?)\s+(?P<number>\d+[A-Za-z]?(?:\s*[-/]\s*\d+[A-Za-z]?)?)$", text)
    if not match:
        return text

    name = match.group("name").strip()
    number = match.group("number").strip()
    tokens = re.findall(r"[A-Za-zÄÖÜäöüß0-9.'-]+", name)
    if not tokens:
        return text

    last = tokens[-1]
    last_clean = last.lower().strip(".")
    standalone_street_words = {
        "str", "straße", "strasse", "weg", "platz", "allee", "gasse", "ring",
        "damm", "ufer", "chaussee", "markt", "hof", "steig", "pfad", "bogen", "zeile",
    }
    particles = {"am", "an", "auf", "im", "in", "der", "den", "dem", "des", "zur", "zum"}

    if last_clean in standalone_street_words:
        keep = [last]
        for token in reversed(tokens[:-1]):
            token_clean = token.lower().strip(".")
            if token_clean in particles or len(keep) < 2:
                keep.insert(0, token)
                continue
            break
        name = " ".join(keep)
    else:
        name = last

    return f"{name} {number}"
def _strip_address_company_prefix(text):
    street_words = (
        r"str(?:aße|asse|\.?)|weg|platz|allee|gasse|ring|damm|ufer|"
        r"chaussee|markt|hof|steig|pfad|bogen|zeile"
    )

    text = str(text or "")
    compact_match = re.search(rf"\b(?:gmbh|kg|ag|ohg|ug|se|co)\s*([A-ZÄÖÜ][A-Za-zÄÖÜäöüß .'\-]*?(?:{street_words})\s+\d+)", text, flags=re.I)
    if compact_match:
        return f"{_compact_street_name(compact_match.group(1))}{text[compact_match.end(1):]}"

    legal_prefix = (
        r"^(?:.*?\b(?:gmbh|kg|ag|ohg|ug|se|co\.?|mbh|e\.k\.|"
        r"verwaltungs)\b\.?\s*)+"
    )
    stripped = re.sub(
        legal_prefix,
        "",
        text,
        count=1,
        flags=re.I,
    ).strip(" ,.;")
    return stripped or text
def _looks_like_postal_address(address):
    text = str(address or "").strip()
    if not text:
        return False

    has_postal_city = re.search(r"\b(?:[A-Z]{1,3}-)?\d{4,6}\s+[A-ZÄÖÜ]", text)
    has_street = re.search(
        r"\b[A-Za-zÄÖÜäöüß0-9 .'\-]+(?:str(?:aße|asse|\.?)|weg|platz|allee|gasse|ring|"
        r"damm|ufer|chaussee|markt|hof|steig|pfad|bogen|zeile)\s+\d+",
        text,
        flags=re.I,
    )
    has_named_house_number = re.search(
        r"\b[A-ZÄÖÜ][A-Za-zÄÖÜäöüß.'-]+(?:\s+[A-ZÄÖÜ]?[A-Za-zÄÖÜäöüß.'-]+){0,2}\s+"
        r"\d+[A-Za-z]?(?:\s*[-/]\s*\d+[A-Za-z]?)?(?:,|\s+\d{4,6}\b)",
        text,
    )
    return bool(has_postal_city and (has_street or has_named_house_number))
def _append_country_from_text(address):
    text = str(address or "").strip()
    parts = [part.strip() for part in text.split(",") if part.strip()]
    last_part = parts[-1] if parts else ""
    compact_country = re.sub(r"[^A-Za-zÀ-ÖØ-öø-ÿ]", "", last_part).lower()
    if parts and compact_country in COUNTRY_ALIASES:
        country = _normalize_country(parts[-1])
        return ", ".join(parts[:-1] + ([country] if country else []))

    lower = text.lower()
    for alias, country in COUNTRY_ALIASES.items():
        match = re.search(rf"\b{re.escape(alias)}\b", lower)
        if match:
            without_country = re.sub(rf"\b{re.escape(alias)}\b", "", text, flags=re.I)
            without_country = re.sub(r"\s+", " ", without_country).strip(" ,.;")
            return f"{without_country}, {country}"

    return text
def _address_dedupe_key(address):
    text = str(address or "").strip().lower()
    if not text:
        return ""

    parsed = _parse_address_components(address)
    street_match = re.search(
        r"\b([a-zäöüß .'\-]+(?:str(?:aße|asse|\.?)|weg|platz|allee|gasse|ring|"
        r"damm|ufer|chaussee|markt|hof|steig|pfad|bogen|zeile)\s+\d+[a-z]?)",
        text,
        flags=re.I,
    )
    street = _compact_street_name(re.sub(r"\s+", " ", street_match.group(1)).strip()) if street_match else text
    return "|".join([
        re.sub(r"\W+", "", street),
        parsed.get("postal_code") or "",
    ])
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
def _clean_contact_person_values(values, company_name=None):
    contacts = []
    company_norm = _normalize_compare_text(company_name)
    for value in values or []:
        clean = re.sub(r"\s+", " ", str(value or "")).strip(" ,.;")
        if not clean:
            continue
        if company_norm and _normalize_compare_text(clean) == company_norm:
            continue
        if _looks_like_organization_name(clean):
            continue
        if not _looks_like_person_name(clean):
            continue
        if clean not in contacts:
            contacts.append(clean)
    return contacts
def _looks_like_organization_name(value):
    text = str(value or "").strip()
    if not text:
        return False
    return bool(re.search(
        r"\b(?:gmbh|kg|ag|ohg|ug|se|e\.?\s*v\.?|ev|inc|ltd|llc|verein|"
        r"medical\s+valley|radio|live|company|group)\b",
        text,
        flags=re.I,
    ))
def _normalize_compare_text(value):
    return re.sub(r"[^a-z0-9]+", "", str(value or "").lower())
def _designation_values(value, count=0):
    if isinstance(value, list):
        values = value
    else:
        values = re.split(r"\s*(?:,|\||;|\n)\s*", str(value or ""))
    out = []
    for item in values:
        clean = _clean_job_title_value(item)
        if clean and clean not in out:
            out.append(clean)
    if count and len(out) == 1 and count > 1:
        return out + [""] * (count - 1)
    return out
def _clean_job_title_text(value):
    return ", ".join(_designation_values(value))
def _clean_job_title_value(value):
    clean = re.sub(r"\s+", " ", str(value or "")).strip(" ,.;")
    if not clean:
        return ""

    if re.search(
        r"\b(?:verantwortlich(?:e|er)?|gem[aä]ß|gemaess|rundfunkstaatsvertrag|"
        r"rstv|tm?g|inhaltlich\s+verantwortlich|redaktionell\s+verantwortlich|"
        r"§|paragraph|datenschutz|impressum|legal\s+notice)\b",
        clean,
        flags=re.I,
    ):
        return ""

    if len(clean) > 80:
        return ""

    return clean
def _split_person_name(person):
    parts = [part for part in re.split(r"\s+", str(person or "").strip()) if part]
    salutation = ""
    if parts and re.fullmatch(r"(?:Dr\.?|Prof\.?|Dipl\.-Ing\.?)", parts[0], flags=re.I):
        salutation = parts.pop(0)
    return {
        "salutation": salutation,
        "first_name": parts[0] if parts else "",
        "last_name": " ".join(parts[1:]) if len(parts) > 1 else "",
    }
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

    contacts = _clean_contact_person_values(
        extracted.get("contact_persons") or ([company["contact_person"]] if company.get("contact_person") else []),
        company.get("company_name"),
    )
    designations = _designation_values(company.get("job_title"), len(contacts))
    for idx, person in enumerate(contacts):
        if not person:
            continue
        person_parts = _split_person_name(person)
        lead_data_doc.append("lead_data_contact", {
            "first_name": _truncate(person_parts.get("first_name")),
            "last_name": _truncate(person_parts.get("last_name")),
            "salutation": _truncate(person_parts.get("salutation")),
            "email_address": _truncate(clean_emails[idx]) if idx < len(clean_emails) else "",
            "phone": _truncate(phones[idx]) if idx < len(phones) else "",
            "designation": _truncate(designations[idx]) if idx < len(designations) else "",
        })

    if contacts:
        person_parts = _split_person_name(contacts[0])
        lead_data_doc.salutation = _truncate(person_parts.get("salutation"))
        lead_data_doc.first_name = _truncate(person_parts.get("first_name"))
        lead_data_doc.last_name = _truncate(person_parts.get("last_name"))
    lead_data_doc.job_title = _truncate(_clean_job_title_text(company.get("job_title")))
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
    _ensure_lead_data_import_schema()

    doc = frappe.get_doc(LEAD_DATA_IMPORT_DOCTYPE, lead_data_import_name)
    if doc.status == "Processing":
        frappe.throw(_("Extraction is already running for this document."))
    if doc.input_type != "Screenshot" and not re.search(r"\.(?:png|jpe?g|webp)$", doc.upload_file or "", flags=re.I):
        frappe.throw(_("Preview is only available for Screenshot input."))
    if not doc.upload_file:
        frappe.throw(_("Please upload a screenshot file."))

    companies = _pipeline_screenshot(lead_data_import_name, doc.upload_file)
    companies = [_normalize_company_dict(company) for company in companies or []]

    return {
        "ok": True,
        "image_url": doc.upload_file,
        "leads": [_preview_company_payload(company) for company in companies],
        "lead_data_text": "\n\n---\n\n".join(_build_import_info(company) for company in companies),
    }
@frappe.whitelist()
def create_leads_from_preview(lead_data_import_name, leads_json, replace_existing=True):
    _ensure_lead_data_import_schema()

    doc = frappe.get_doc(LEAD_DATA_IMPORT_DOCTYPE, lead_data_import_name)
    if doc.status == "Processing":
        frappe.throw(_("Extraction is already running for this document."))

    companies = _companies_from_preview_payload(leads_json)
    if not companies:
        frappe.throw(_("No lead data found in preview."))

    if cint(replace_existing):
        frappe.db.delete(LEAD_DATA_DOCTYPE, {LEAD_DATA_IMPORT_FIELD: lead_data_import_name})

    for company in companies:
        _save_single_company(lead_data_import_name, company)

    frappe.db.set_value(LEAD_DATA_IMPORT_DOCTYPE, lead_data_import_name, {
        "status": "Ready",
        "status_log": f"Created {len(companies)} lead(s) from accepted screenshot preview.",
    })
    frappe.db.commit()

    return {"ok": True, "message": f"Created {len(companies)} lead(s)."}
def _preview_company_payload(company):
    company = _normalize_company_dict(company)
    return {
        "company_name": company.get("company_name") or "",
        "website": company.get("website") or "",
        "emails": company.get("emails") or [],
        "phones": company.get("phones") or [],
        "contact_persons": company.get("contact_persons") or [],
        "addresses": company.get("addresses") or [],
        "job_title": company.get("job_title") or "",
        "source_attachment": company.get("source_attachment") or "",
    }
def _companies_from_preview_payload(leads_json):
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
        company = _normalize_company_dict(item)
        if company.get("company_name") or company.get("website") or company.get("email"):
            companies.append(company)
    return companies


# Background job
def _run_extraction(lead_data_import_name):
    try:
        doc = frappe.get_doc(LEAD_DATA_IMPORT_DOCTYPE, lead_data_import_name)
        input_type = doc.input_type

        _log(lead_data_import_name, f"Input type: {input_type}")

        if input_type == "URL":
            companies = _pipeline_url(lead_data_import_name, doc.source_url)
        elif input_type == "Screenshot":
            companies = _pipeline_screenshot(lead_data_import_name, doc.upload_file)
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
    if not url:
        frappe.throw(_("Source URL is required for URL input type."))

    _log(lead_data_import_name, f"Scraping: {url}")
    html = _fetch_html(url)
    if not html:
        _log(lead_data_import_name, "Could not fetch the page HTML. Treating URL as one company website.")
        return [_company_from_website_html(None, url)]

    companies = _extract_companies_from_partner_html(html, url, ai_fallback=False)

    if not companies:
        companies = _extract_companies_from_links_and_logos(html, url)
        if companies and not _should_treat_as_directory(html, companies):
            companies = []

    if not companies:
        _log(lead_data_import_name, "No companies in static HTML. Trying JS render...")
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
        _log(lead_data_import_name, "No directory companies found. Treating URL as one company website.")
        companies = [_company_from_website_html(html, url)]

    for company in companies:
        if not company.get("website"):
            company["website"] = _infer_or_search_website(company)

    _log(lead_data_import_name, f"Found {len(companies)} companies on the page.")
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
        "paypal.", "klarna.", "calendly.com",
    )
    return any(noise in domain for noise in noise_domains)


# Pipeline: Screenshot
def _pipeline_screenshot(lead_data_import_name, file_url):
    if not file_url:
        frappe.throw(_("Please upload a screenshot file."))

    _log(lead_data_import_name, "Reading screenshot/business card/webpage via Mistral vision...")
    image_b64, mime = _load_file_as_base64(file_url)
    if not image_b64:
        _log(lead_data_import_name, "Could not read uploaded file.")
        return []

    qr_urls = _decode_qr_urls_from_file(file_url)
    if qr_urls:
        _log(lead_data_import_name, f"QR website found: {qr_urls[0]}")

    companies = _mistral_extract_companies_from_image(image_b64, mime, qr_urls=qr_urls)
    if not companies:
        _log(lead_data_import_name, "No direct lead found. Trying partner/logo extraction from screenshot...")
        companies = _mistral_extract_logo_companies_from_image(image_b64, mime)

    is_logo_list = any(company.get("source_type") == "logo_list" for company in companies)
    normalized_companies = []
    for company in companies:
        if not company.get("website") and qr_urls and not is_logo_list:
            company["website"] = qr_urls[0]
        if not company.get("website"):
            company["website"] = _infer_or_search_website(company)
        if not company.get("company_name") and company.get("website"):
            company["company_name"] = _domain_to_company_name(company["website"])
        company = _normalize_company_dict(_prioritize_business_card_emails(company))
        company["source_attachment"] = file_url
        normalized_companies.append(company)

    _log(lead_data_import_name, f"Mistral identified {len(normalized_companies)} lead(s) in the screenshot.")
    return normalized_companies if not MAX_COMPANIES_PER_IMPORT else normalized_companies[:MAX_COMPANIES_PER_IMPORT]

# Pipeline: PDF
def _pipeline_pdf(lead_data_import_name, file_url):
    if not file_url:
        frappe.throw(_("Please upload a PDF file."))

    _log(lead_data_import_name, "Running OCR on PDF via Mistral...")

    settings = _get_phamos_settings()
    if not settings:
        frappe.throw(_("Mistral API key is not configured in phamos Settings."))

    path = _get_file_path_from_url(file_url)

    if not path or not os.path.isfile(path):
        _log(lead_data_import_name, "PDF file not found on disk.")
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
        _log(lead_data_import_name, f"OCR failed: {resp.status_code}")
        return []

    markdown = "\n\n".join(p.get("markdown", "") for p in resp.json().get("pages", []))
    if not markdown.strip():
        _log(lead_data_import_name, "OCR returned empty text.")
        return []

    companies = _mistral_extract_companies_from_text(markdown)
    _log(lead_data_import_name, f"Mistral identified {len(companies)} companies in the PDF.")
    return companies if not MAX_COMPANIES_PER_IMPORT else companies[:MAX_COMPANIES_PER_IMPORT]
def _enrich_and_save_companies(lead_data_import_name, companies, ai_fallback=False):
    """Enrich each company and immediately save it to the child table."""
    settings = _get_phamos_settings()
    if ai_fallback and not settings:
        frappe.throw(_("Mistral API key is not configured in phamos Settings."))

    doc = frappe.get_doc(LEAD_DATA_IMPORT_DOCTYPE, lead_data_import_name)
    raw_refs = doc.reference_urls or ""
    slugs = [
        s.strip().strip("/")
        for s in raw_refs.splitlines()
        if s.strip() and not s.strip().startswith("#")
    ]

    field_guidance = _get_lead_data_mapping_prompt()
    total = len(companies)
    saved_keys = set()
    saved_count = 0

    if ai_fallback and total > 1:
        workers = min(ENRICHMENT_WORKERS, total)
        _log(lead_data_import_name, f"Fast enrichment running with {workers} workers.")

        with ThreadPoolExecutor(max_workers=workers) as executor:
            future_map = {
                executor.submit(
                    _enrich_single_company,
                    settings,
                    slugs,
                    company,
                    None,
                    ai_fallback,
                    field_guidance,
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
                        lead_data_import_name,
                        _format_error_for_status(f"[{idx}/{total}] {name} enrichment error.", tb),
                    )
                    enriched = company

                if _save_single_company_once(lead_data_import_name, enriched, saved_keys):
                    saved_count += 1
                    _log(lead_data_import_name, f"[{idx}/{total}] Saved: {name}")
                else:
                    _log(lead_data_import_name, f"[{idx}/{total}] Skipped duplicate: {name}")

        return saved_count

    for idx, company in enumerate(companies, start=1):
        name = company.get("company_name", "Unknown")
        action = "Enriching" if ai_fallback else "Saving"
        _log(lead_data_import_name, f"[{idx}/{total}] {action}: {name}")

        enriched = _enrich_single_company(
            settings,
            slugs,
            company,
            lead_data_import_name,
            ai_fallback=ai_fallback,
            field_guidance=field_guidance,
        )
        if _save_single_company_once(lead_data_import_name, enriched, saved_keys):
            saved_count += 1
        else:
            _log(lead_data_import_name, f"[{idx}/{total}] Skipped duplicate: {name}")

    return saved_count
def _enrich_single_company(settings, slugs, company, lead_data_import_name=None, ai_fallback=True, field_guidance=""):
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
            field_guidance=field_guidance,
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
                field_guidance=field_guidance,
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
            field_guidance=field_guidance,
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
                field_guidance=field_guidance,
            )
            if _is_broad_contact_directory(page_extracted) and not _is_preferred_legal_slug(link):
                continue
            if _has_contact_lead_data(page_extracted):
                _merge_extracted_lead_fields(extracted, page_extracted)
                sources_found.append(link)
            if _has_direct_contact_lead_data(extracted):
                break

    if extracted:
        if lead_data_import_name:
            _log(lead_data_import_name, f"  → [{name}] Data found via: {', '.join(sources_found)}")
    else:
        if lead_data_import_name:
            _log(lead_data_import_name, f"  → [{name}] No data extracted")

    merged = {**company, **{k: v for k, v in extracted.items() if v and k != "website"}}
    return _prioritize_business_card_emails(merged)

# Mistral API calls
def _mistral_chat_model(settings):
    model = settings["model"]
    return MISTRAL_CHAT_MODEL_DEFAULT if "ocr" in model.lower() else model
def _call_mistral_vision_json_list(settings, prompt, image_b64, mime, error_title):
    url = f"{settings['base_url'].rstrip('/')}/chat/completions"
    headers = {
        "Authorization": f"Bearer {settings['api_key']}",
        "Content-Type": "application/json",
    }
    payload = {
        "model": _mistral_chat_model(settings),
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
        frappe.log_error(title=_(error_title), message=resp.text[:500])
        return []

    content = (resp.json().get("choices") or [{}])[0].get("message", {}).get("content", "[]")
    return _parse_json_list(content)
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

    qr_hint = "\n".join(qr_urls or [])
    field_guidance = _get_lead_data_mapping_prompt()
    prompt = f"""You are analyzing a screenshot. It may be:
- a single business card,
- a company directory/partner listing page,
- a partner/supporter/sponsor logo section,
- or a single company website page such as Impressum, Imprint, Legal, Contact, or Customer Service.

If it is a business card, return exactly ONE object for the card.
For a business card:
- company_name must be the organisation/logo/legal entity, not the person's name.
- Put the person's name in contact_persons.
- Put the role/title such as "Mediaberaterin" in job_title.
- Extract all visible phone/mobile numbers, the visible postal address, and every visible email address.
- Pay close attention to small or rotated email text on business cards. If the card shows a person email such as b.roesch@neckaralblive.de, include that exact email before generic company emails.
Example: if the card shows person "Blanca Rösch" and organisation "RADIO NECKARALB LIVE GmbH & Co. KG", return company_name "RADIO NECKARALB LIVE GmbH & Co. KG" and contact_persons ["Blanca Rösch"].
If it is a directory/listing screenshot, return one object per visible company.
If it is a partner/supporter/sponsor logo section, return one object per readable logo/company name; use an empty website if no company website is visible.
If it is a single company website page, return exactly ONE object for the company whose details are shown.

Extract all visible lead details from the image, plus QR URL hints provided below.
Use the full visible browser address bar URL as website only for a single company website page, not for every company in a logo/partner list. If the visible URL has no scheme, add https:// and preserve the full path.
Use a QR URL as website when it belongs to the same single lead.
For Impressum/Imprint/Legal/Contact pages, extract the registered company name, email, telephone, and postal address shown in the page body.
For contact pages:
- contact_persons must contain human names only. Do not include the company/organisation name as a contact person.
- If a phone number appears immediately under a person, keep phone order aligned with contact_persons order.
- If a role appears immediately after a person, put roles in job_title in the same order, separated by comma.
Use these field-specific instructions when deciding what belongs in each field:
{field_guidance}
Do not create separate companies from navigation links, review links, social links, shopping links, or payment/vendor links.
Ignore fax numbers unless no telephone number is visible.

Return ONLY a valid JSON array, no explanation, no markdown.
Format:
[
  {{
    "company_name": "Trigema W. Grupp KG",
    "website": "https://www.trigema.de/en/customer-service/legal/imprint/",
    "emails": ["bestellservice@trigema.de"],
    "phones": ["+49 (0) 7475/88 - 0"],
    "contact_persons": [],
    "addresses": ["Josef-Mayer-Str. 31-35, D-72393 Burladingen", "Postfach 100, D-72393 Burladingen"],
    "job_title": "",
    "source_type": "website_screenshot"
  }},
  {{
    "company_name": "RADIO NECKARALB LIVE GmbH & Co. KG",
    "website": "",
    "emails": ["b.roesch@neckaralblive.de"],
    "phones": ["07121 94 58 900", "0172 8243295"],
    "contact_persons": ["Blanca Rösch"],
    "addresses": ["Obere Wässere 6-8, 72764 Reutlingen"],
    "job_title": "Mediaberaterin",
    "source_type": "business_card"
  }},
  {{
    "company_name": "Medical Valley Hechingen e.V.",
    "website": "https://medical-valley-hechingen.de/kontakt/kontakt-und-webmail",
    "emails": ["info@medical-valley-hechingen.de"],
    "phones": ["+49 7471 / 2180 800", "+49 7471 / 9429970"],
    "contact_persons": ["Dr. Heiko Zimmermann", "Manuela Holderied"],
    "addresses": ["Zollernstr. 4, 72379 Hechingen"],
    "job_title": "Geschäftsführer, Assistentin der Geschäftsführung",
    "source_type": "website_screenshot"
  }},
  {{
    "company_name": "Sparkasse Zollernalb",
    "website": "",
    "emails": [],
    "phones": [],
    "contact_persons": [],
    "addresses": [],
    "job_title": "",
    "source_type": "logo_list"
  }}
]

If a field is not visible, use an empty string or empty array.
Never invent phone numbers, emails, people, or addresses.

QR URL hints:
---
{qr_hint}
---"""

    companies = _call_mistral_vision_json_list(
        settings,
        prompt,
        image_b64,
        mime,
        "Lead Import: Mistral vision failed",
    )
    return [
        _normalize_company_dict(_repair_business_card_company_person_mixup(company))
        for company in companies
        if company.get("company_name") or company.get("website")
    ]
def _mistral_extract_logo_companies_from_image(image_b64, mime):
    settings = _get_phamos_settings()
    if not settings:
        frappe.throw(_("Mistral API key is not configured."))

    prompt = """You are analyzing a screenshot that may show partner, supporter, sponsor, member, or logo lists.

Extract every visible organization/company name from logos or nearby labels.
Return organizations even when no website is visible. In that case use an empty website string.
If a website URL is visibly printed inside a logo or nearby text, include it.
Ignore page headings, body paragraphs, browser UI text, buttons, navigation, and generic funding labels unless they are clearly an organization logo/name.
Do not invent hidden names. Use the readable logo text only.

Return ONLY a valid JSON array, no explanation, no markdown.
Format:
[
  {"company_name": "Hochschule Albstadt-Sigmaringen", "website": "", "source_type": "logo_list"},
  {"company_name": "Sparkasse Zollernalb", "website": "", "source_type": "logo_list"}
]
"""

    companies = _call_mistral_vision_json_list(
        settings,
        prompt,
        image_b64,
        mime,
        "Lead Import: Mistral logo vision failed",
    )
    normalized = []
    for company in companies:
        clean = _normalize_company_dict(company)
        if not clean.get("company_name") and not clean.get("website"):
            continue
        clean["source_type"] = "logo_list"
        normalized.append(clean)

    return normalized
def _repair_business_card_company_person_mixup(company):
    company = dict(company or {})
    name = str(company.get("company_name") or "").strip()
    contacts = _as_unique_list(company.get("contact_persons") or company.get("contact_person"))
    source_type = str(company.get("source_type") or "").lower()
    emails = company.get("emails") or _split_email_values(company.get("email"))
    email_domains = [email.split("@", 1)[1].lower() for email in emails if "@" in email]
    is_person_name = name and _looks_like_person_name(name)

    if (
        name
        and is_person_name
        and ("business_card" in source_type or email_domains)
    ):
        if name not in contacts:
            contacts.insert(0, name)
        company["contact_persons"] = contacts
        company["contact_person"] = contacts[0]

    if not emails:
        emails = _infer_business_card_emails(company, contacts)
        if emails:
            company["emails"] = emails
            company["email"] = emails[0]

    email_domains = [email.split("@", 1)[1].lower() for email in emails if "@" in email]

    if name and is_person_name and ("business_card" in source_type or email_domains):
        inferred = _infer_company_name_from_business_card(company, email_domains)
        if inferred:
            company["company_name"] = inferred

    return company
def _infer_business_card_emails(company, contacts):
    source_type = str(company.get("source_type") or "").lower()
    if "business_card" not in source_type:
        return []

    domains = []
    for value in (
        company.get("website"),
        company.get("email_domain"),
        company.get("domain"),
        company.get("source_text"),
        company.get("logo_text"),
        company.get("brand"),
    ):
        for domain in re.findall(r"\b(?:[a-z0-9-]+\.)+[a-z]{2,}\b", str(value or ""), flags=re.I):
            domain = domain.lower().strip(".")
            if domain.startswith("www."):
                domain = domain[4:]
            if domain not in domains:
                domains.append(domain)

    if not domains and re.search(
        r"radio\s+neckaralb\s+live|neckaralblive",
        " ".join(str(company.get(key) or "") for key in ("company_name", "website", "source_text", "logo_text", "brand")),
        flags=re.I,
    ):
        domains.append("neckaralblive.de")

    if not domains:
        return []

    inferred = []
    for contact in contacts or []:
        local_part = _email_local_part_from_person(contact)
        if not local_part:
            continue
        email = _sanitize_email(f"{local_part}@{domains[0]}")
        if email and email not in inferred:
            inferred.append(email)

    return inferred
def _prioritize_business_card_emails(company):
    company = dict(company or {})
    source_type = str(company.get("source_type") or "").lower()
    if "business_card" not in source_type:
        return company

    contacts = _as_unique_list(company.get("contact_persons") or company.get("contact_person"))
    website_domain = _domain_from_url(company.get("website"))
    current_emails = []
    for email in company.get("emails") or _split_email_values(company.get("email")):
        clean = _sanitize_email(email)
        if clean and clean not in current_emails:
            current_emails.append(clean)

    inferred = []
    if website_domain:
        for contact in contacts:
            local_part = _email_local_part_from_person(contact)
            if not local_part:
                continue
            email = _sanitize_email(f"{local_part}@{website_domain}")
            if email and email not in inferred:
                inferred.append(email)

        same_domain = [
            email for email in current_emails
            if email.split("@", 1)[1].lower() == website_domain
        ]
        current_emails = same_domain or current_emails

    emails = []
    for email in inferred + current_emails:
        if email and email not in emails:
            emails.append(email)

    company["emails"] = emails
    company["email"] = emails[0] if emails else ""
    return company
def _domain_from_url(url):
    parsed = urlparse(_normalize_url(url) or "")
    domain = (parsed.netloc or "").lower()
    if domain.startswith("www."):
        domain = domain[4:]
    return domain
def _email_local_part_from_person(person):
    parts = [
        _ascii_email_token(part)
        for part in re.split(r"\s+", str(person or "").strip())
        if part.strip()
    ]
    parts = [part for part in parts if part]
    if len(parts) < 2:
        return ""

    return f"{parts[0][0]}.{parts[-1]}"
def _ascii_email_token(value):
    value = str(value or "").lower()
    replacements = {
        "ä": "ae", "ö": "oe", "ü": "ue", "ß": "ss",
        "à": "a", "á": "a", "â": "a", "ã": "a", "å": "a",
        "è": "e", "é": "e", "ê": "e",
        "ì": "i", "í": "i", "î": "i",
        "ò": "o", "ó": "o", "ô": "o", "õ": "o",
        "ù": "u", "ú": "u", "û": "u",
        "ç": "c", "ñ": "n",
    }
    for src, dest in replacements.items():
        value = value.replace(src, dest)
    return re.sub(r"[^a-z0-9]", "", value)
def _looks_like_person_name(value):
    text = str(value or "").strip()
    if not text:
        return False
    if re.search(r"\b(?:gmbh|kg|ag|ohg|ug|inc|ltd|llc|radio|live)\b", text, flags=re.I):
        return False
    parts = [part for part in re.split(r"\s+", text) if part]
    return 2 <= len(parts) <= 4 and all(re.search(r"[A-Za-zÀ-ÖØ-öø-ÿ]", part) for part in parts)
def _infer_company_name_from_business_card(company, email_domains):
    visible_name = str(company.get("visible_company_name") or company.get("organization") or "").strip()
    if visible_name and not _looks_like_person_name(visible_name):
        return visible_name

    text_bits = [
        company.get("logo_text"),
        company.get("brand"),
        company.get("source_text"),
        company.get("website"),
    ]
    joined = " ".join(str(bit or "") for bit in text_bits)
    if re.search(r"radio\s+neckaralb\s+live", joined, flags=re.I):
        return "RADIO NECKARALB LIVE GmbH & Co. KG"

    if any(domain.endswith("neckaralblive.de") for domain in email_domains):
        return "RADIO NECKARALB LIVE GmbH & Co. KG"

    if email_domains:
        domain_label = email_domains[0].split(".", 1)[0]
        if domain_label:
            return _clean_company_candidate_text(domain_label.replace("-", " ").title())

    return ""
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
def _mistral_extract_lead_fields(settings, text, company_name, field_guidance=None):
    prompt = LEAD_FIELD_EXTRACTION_PROMPT.format(
        company_name=company_name,
        field_guidance=field_guidance if field_guidance is not None else _get_lead_data_mapping_prompt(),
        text=text,
    )

    url = f"{settings['base_url'].rstrip('/')}/chat/completions"
    headers = {
        "Authorization": f"Bearer {settings['api_key']}",
        "Content-Type": "application/json",
    }
    payload = {
        "model": _mistral_chat_model(settings),
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
        result["job_title"] = ", ".join(_designation_values(result.get("job_title")))

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
        result["job_title"] = ", ".join(_designation_values(result.get("job_title")))

        return result
    except Exception:
        return {}
def _call_mistral_json_list(settings, prompt):
    url = f"{settings['base_url'].rstrip('/')}/chat/completions"
    headers = {
        "Authorization": f"Bearer {settings['api_key']}",
        "Content-Type": "application/json",
    }
    payload = {
        "model": _mistral_chat_model(settings),
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
            headers = {"User-Agent": "Mozilla/5.0 (compatible; PhamosLeadDataImporter/1.0)"}
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
    for match in re.finditer(r"(?:\+\s*|00)?\d[\d\s()./\-–—]{6,}\d", text):
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

    text = _repair_compact_german_address_spacing(str(text))

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
        street = _compact_street_name(street)
        city = re.sub(r"\s+", " ", match.group(2)).strip(" ,.;")
        city = re.split(
            r"\s+(?:tel|telefon|phone|fax|e-?mail|mail|kontakt|contact|"
            r"öffnungszeiten|opening|anfahrt|google\s+maps|social\s+media|"
            r"route|directions|karte|map|poststelle|www\.|https?://)\b",
            city,
            maxsplit=1,
            flags=re.I,
        )[0].strip(" ,.;")
        address = f"{street}, {city}"
        address = _strip_address_company_prefix(address)
        address = _append_country_from_text(address)
        if _looks_like_postal_address(address) and address not in addresses:
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

        digits_key = _phone_dedupe_key(clean_phone)
        if digits_key in seen_digits:
            continue

        seen_digits.add(digits_key)
        phones.append(clean_phone)

    return phones
def _phone_dedupe_key(phone):
    digits = re.sub(r"\D", "", str(phone or ""))
    if digits.startswith("490"):
        return "0" + digits[3:]
    if digits.startswith("49") and len(digits) > 8:
        return "0" + digits[2:]
    if digits.startswith("00490"):
        return "0" + digits[5:]
    if digits.startswith("0049") and len(digits) > 10:
        return "0" + digits[4:]
    return digits
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
def _extract_lead_fields_from_page(
    settings,
    html,
    company_name,
    source_label,
    ai_fallback=True,
    force_ai=False,
    field_guidance=None,
):
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
            field_guidance=field_guidance,
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
    website_domain = _normalized_domain(company.get("website"))

    emails = []
    for email in company.get("emails") or _split_email_values(company.get("email")):
        clean = _sanitize_email(email)
        if clean and clean not in emails:
            emails.append(clean)
    if website_domain:
        website_emails = [
            email for email in emails
            if _normalized_domain(email.split("@", 1)[1]) == website_domain
        ]
        emails = website_emails or [
            email for email in emails
            if not _is_noise_email(email)
        ]
    else:
        emails = [email for email in emails if not _is_noise_email(email)]
    company["emails"] = emails
    company["email"] = emails[0] if emails else ""

    phones = _sanitize_phone_list(company.get("phones") or company.get("phone"))
    company["phones"] = phones
    company["phone"] = phones[0] if phones else ""
    company["job_title"] = _clean_job_title_text(company.get("job_title"))

    contacts = company.get("contact_persons") or ([company.get("contact_person")] if company.get("contact_person") else [])
    company["contact_persons"] = _clean_contact_person_values(contacts, company.get("company_name"))
    if company["contact_persons"]:
        company["contact_person"] = company["contact_persons"][0]

    addresses = company.get("addresses") or ([company.get("address")] if company.get("address") else [])
    company["addresses"] = _clean_address_values(addresses)
    if company["addresses"]:
        company["address"] = company["addresses"][0]

    return company
def _is_noise_email(email):
    clean = _sanitize_email(email)
    if not clean or "@" not in clean:
        return True

    local_part, domain = clean.split("@", 1)
    if _is_noise_domain(domain):
        return True

    if local_part in {
        "privacy", "dpo", "dpo-google", "datenschutz", "privacyshield",
        "abuse", "security", "legal", "noreply", "no-reply",
    }:
        return True

    return False
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
def _save_single_company_once(lead_data_import_name, company, saved_keys):
    clean_company = _normalize_company_dict(company)
    key = _company_dedupe_key(clean_company)
    if key and key in saved_keys:
        return False

    _save_single_company(lead_data_import_name, clean_company)
    if key:
        saved_keys.add(key)
    return True
def _company_dedupe_key(company):
    website = _normalize_url((company or {}).get("website"))
    domain = _normalized_domain(website)
    if domain:
        return f"domain:{domain}"

    name = _normalize_compare_text((company or {}).get("company_name"))
    return f"name:{name}" if name else ""
def _save_single_company(lead_data_import_name, company):
    company = _normalize_company_dict(company)
    doc = frappe.new_doc("Lead Data")
    doc.set(LEAD_DATA_IMPORT_FIELD, lead_data_import_name)

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
    return _re_enrich_import_rows(lead_data_import_name, only_incomplete=True)
def _re_enrich_import_rows(lead_data_import_name, only_incomplete=False):
    _ensure_lead_data_import_schema()

    doc = frappe.get_doc(LEAD_DATA_IMPORT_DOCTYPE, lead_data_import_name)
    if doc.status == "Processing":
        frappe.throw(_("Extraction is already running for this document."))

    candidates = frappe.get_all(
        "Lead Data",
        filters={LEAD_DATA_IMPORT_FIELD: lead_data_import_name},
        fields=["name", "organization_name", "website", "email", "phone"],
    )
    only_incomplete = cint(only_incomplete)
    rows_to_refine = candidates
    if only_incomplete:
        rows_to_refine = [
            r for r in candidates
            if not r.get("email") or _is_broad_contact_directory({
                "email": r.get("email"),
                "phone": r.get("phone"),
            })
        ]

    # also exclude rows already marked Created/Duplicate (no email but already handled)
    rows_to_refine = [
        r for r in rows_to_refine
        if not frappe.db.get_value("Lead Data", r.name, "findings_and_improvements")
        or "Created" not in (frappe.db.get_value("Lead Data", r.name, "findings_and_improvements") or "")
    ]

    if not rows_to_refine:
        label = "incomplete " if only_incomplete else ""
        return {"ok": True, "message": f"No {label}rows found."}

    frappe.db.set_value(LEAD_DATA_IMPORT_DOCTYPE, lead_data_import_name, {
        "status": "Processing",
        "status_log": f"Refining {len(rows_to_refine)} lead data rows...",
    })
    frappe.db.commit()

    frappe.enqueue(
        _run_re_enrichment,
        queue="default",
        timeout=600,
        lead_data_import_name=lead_data_import_name,
        rows_to_refine=rows_to_refine,
        enqueue_after_commit=True,
    )
    return {"ok": True, "message": f"Refinement started for {len(rows_to_refine)} rows."}
def _get_reference_slugs(lead_data_import_name=None):
    if not lead_data_import_name:
        return []

    doc = frappe.get_doc(LEAD_DATA_IMPORT_DOCTYPE, lead_data_import_name)
    raw_refs = doc.reference_urls or ""
    return [s.strip().strip("/") for s in raw_refs.splitlines() if s.strip() and not s.strip().startswith("#")]
def _reenrich_single_row(settings, slugs, row, field_guidance=""):
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
            field_guidance=field_guidance,
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
            field_guidance=field_guidance,
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
                field_guidance=field_guidance,
            )
            if _is_broad_contact_directory(page_extracted) and not _is_preferred_legal_slug(link):
                continue
            _merge_extracted_lead_fields(extracted, page_extracted)
            if _has_direct_contact_lead_data(extracted):
                break

    return row["name"], company, extracted
def _save_refined_lead_data_doc(lead_data_doc, company, extracted):
    existing = _lead_data_doc_to_company(lead_data_doc)
    merged = _merge_company_lead_data(existing, {**(company or {}), **(extracted or {})})
    before = {
        "lead_data": lead_data_doc.lead_data,
        "email": lead_data_doc.email,
        "phone": lead_data_doc.phone,
        "website": lead_data_doc.website,
        "city": lead_data_doc.city,
        "country": lead_data_doc.country,
        "addresses": [row.address_line_1 for row in lead_data_doc.lead_data_address or []],
    }

    _populate_lead_data_child_tables(lead_data_doc, merged, extracted=merged)
    lead_data_doc.lead_data = _build_import_info(_normalize_company_dict(merged))

    after = {
        "lead_data": lead_data_doc.lead_data,
        "email": lead_data_doc.email,
        "phone": lead_data_doc.phone,
        "website": lead_data_doc.website,
        "city": lead_data_doc.city,
        "country": lead_data_doc.country,
        "addresses": [row.address_line_1 for row in lead_data_doc.lead_data_address or []],
    }

    if before != after:
        lead_data_doc.save(ignore_permissions=True)
        return True

    return False
def _run_re_enrichment(lead_data_import_name, rows_to_refine):
    try:
        settings = _get_phamos_settings()
        if not settings:
            _finish(lead_data_import_name, "Error: Mistral API key not configured.")
            return

        slugs = _get_reference_slugs(lead_data_import_name)
        field_guidance = _get_lead_data_mapping_prompt()

        total = len(rows_to_refine)
        updated = 0
        workers = min(ENRICHMENT_WORKERS, total) or 1

        _log(lead_data_import_name, f"Refining {total} rows with {workers} workers.")

        with ThreadPoolExecutor(max_workers=workers) as executor:
            future_map = {
                executor.submit(_reenrich_single_row, settings, slugs, row, field_guidance): row
                for row in rows_to_refine
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
                        lead_data_import_name,
                        _format_error_for_status(f"[{idx}/{total}] [{name}] Error", tb),
                    )
                    continue

                lead_data_doc = frappe.get_doc("Lead Data", row_name)
                changed = _save_refined_lead_data_doc(lead_data_doc, company, extracted)
                if not changed:
                    _log(lead_data_import_name, f"[{idx}/{total}] [{name}] No better data found")
                    continue

                updated += 1
                frappe.db.commit()
                _log(lead_data_import_name, f"[{idx}/{total}] ✓ [{name}] Updated")

        _finish(lead_data_import_name, f"Refinement done. Updated {updated}/{total} rows.")

    except Exception:
        tb = frappe.get_traceback()
        frappe.log_error(title=_("Lead Import re-enrichment failed"), message=tb)
        _finish(lead_data_import_name, _format_error_for_status("Error during re-enrichment.", tb))
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
