"""Normalization services for Lead Data Import."""

from ..lead_data_import import (
    COUNTRY_ALIASES,
    _as_unique_list,
    _extract_addresses_from_text,
    _looks_like_person_name,
    _sanitize_email,
    _sanitize_phone_list,
    _truncate,
    html_lib,
    re,
)


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
