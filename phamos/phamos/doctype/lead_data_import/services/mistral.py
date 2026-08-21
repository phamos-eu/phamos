"""Mistral services for Lead Data Import."""

from ..lead_data_import import (
    LEAD_FIELD_EXTRACTION_PROMPT,
    MISTRAL_CHAT_MODEL_DEFAULT,
    _,
    _as_unique_list,
    _clean_company_candidate_text,
    _clean_html,
    _designation_values,
    _extract_contact_fields_from_html,
    _filter_company_candidates,
    _get_lead_data_mapping_prompt,
    _get_phamos_settings,
    _normalize_company_dict,
    _normalize_url,
    _parse_address_components,
    _parse_json_list,
    _sanitize_email,
    _sanitize_phone_list,
    _split_email_values,
    _rank_and_keep_person_emails,
    _partition_phones_and_mobiles,
    frappe,
    json,
    re,
    requests,
    urlparse,
)


def _mistral_chat_model(settings):
    model = settings["model"]
    return MISTRAL_CHAT_MODEL_DEFAULT if "ocr" in model.lower() else model


def _call_mistral_vision_json_list(settings, prompt, image_b64, mime, error_title):
    url = f"{settings['base_url'].rstrip('/')}/chat/completions"
    headers = {
        "Authorization": f"Bearer {settings['api_key']}",
        "Content-Type": "application/json",
    }
    images = image_b64 if isinstance(image_b64, (list, tuple)) else [(image_b64, mime)]
    content = [
        {"type": "image_url", "image_url": f"data:{image_mime};base64,{image_data}"}
        for image_data, image_mime in images
    ]
    content.append({"type": "text", "text": prompt})
    payload = {
        "model": _mistral_chat_model(settings),
        "messages": [
            {
                "role": "user",
                "content": content,
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
    prompt = f"""You are analyzing one or more related screenshots. Multiple images may be the front and back of the same business card. It may be:
- a single business card,
- a company directory/partner listing page,
- a partner/supporter/sponsor logo section,
- or a single company website page such as Impressum, Imprint, Legal, Contact, or Customer Service.

If the images are sides of the same business card, combine all visible details and return exactly ONE object for the card.
For a business card:
- company_name must be the organisation/logo/legal entity, not the person's name.
- Put the person's name in contact_persons.
- Put the role/title such as "Mediaberaterin" in job_title.
- Put landline numbers in phones and numbers labelled Mobil/Mobile in mobile_numbers.
- Prefer compact international phone form without spaces or parentheses (e.g. +4917655591059).
- Extract the visible postal address and every visible email address.
- Copy the street, postal code, and city exactly as printed on the card. Never
  replace them with a city/postal code from memory or from the company website.
  If any address part is unreadable, leave that part empty instead of guessing.
- Copy printed email addresses exactly as shown. Never construct, abbreviate, concatenate, or guess an email from the person's name.
- Keep a personally addressed card email (for example first.last@company.com) before generic addresses such as info@, post@, or contact@.
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
    "phones": ["+497475880"],
    "mobile_numbers": [],
    "contact_persons": [],
    "addresses": ["Josef-Mayer-Str. 31-35, D-72393 Burladingen", "Postfach 100, D-72393 Burladingen"],
    "job_title": "",
    "source_type": "website_screenshot"
  }},
  {{
    "company_name": "RADIO NECKARALB LIVE GmbH & Co. KG",
    "website": "",
    "emails": ["b.roesch@neckaralblive.de"],
    "phones": ["+4971219458900"],
    "mobile_numbers": ["+491728243295"],
    "contact_persons": ["Blanca Rösch"],
    "addresses": ["Obere Wässere 6-8, 72764 Reutlingen"],
    "job_title": "Mediaberaterin",
    "source_type": "business_card"
  }},
  {{
    "company_name": "Medical Valley Hechingen e.V.",
    "website": "https://medical-valley-hechingen.de/kontakt/kontakt-und-webmail",
    "emails": ["info@medical-valley-hechingen.de"],
    "phones": ["+4974712180800", "+4974719429970"],
    "mobile_numbers": [],
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
    "mobile_numbers": [],
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
    normalized = []
    for company in companies:
        source_type = str(company.get("source_type") or "").lower()
        card_emails = []
        if "business_card" in source_type:
            for email in company.get("emails") or _split_email_values(company.get("email")):
                clean = _sanitize_email(email)
                if clean and clean not in card_emails:
                    card_emails.append(clean)
            card_phones_raw = _sanitize_phone_list(company.get("phones"))
            card_mobiles_raw = _sanitize_phone_list(company.get("mobile_numbers"))
            card_phones, card_mobile_numbers = _partition_phones_and_mobiles(
                card_phones_raw, card_mobiles_raw
            )
            company["card_phones"] = card_phones
            company["card_mobile_numbers"] = card_mobile_numbers
            company["phones"] = card_phones
            company["phone"] = card_phones[0] if card_phones else ""
            company["mobile_numbers"] = card_mobile_numbers
            company["mobile_no"] = card_mobile_numbers[0] if card_mobile_numbers else ""
            company["card_contact_persons"] = _as_unique_list(company.get("contact_persons"))
            company["card_job_title"] = str(company.get("job_title") or "").strip()
        company = _normalize_company_dict(_repair_business_card_company_person_mixup(company))
        if card_emails:
            company["card_emails"] = card_emails
        if company.get("company_name") or company.get("website") or company.get("email"):
            normalized.append(company)
    return normalized


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

    if (not name or is_person_name) and ("business_card" in source_type or email_domains):
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

    card_emails = []
    for email in company.get("card_emails") or []:
        clean = _sanitize_email(email)
        if clean and clean not in card_emails:
            card_emails.append(clean)

    card_phones = _sanitize_phone_list(company.get("card_phones"))
    card_mobile_numbers = _sanitize_phone_list(company.get("card_mobile_numbers"))
    card_contacts = _as_unique_list(company.get("card_contact_persons"))
    if card_phones:
        company["phones"] = card_phones
        company["phone"] = card_phones[0]
    if card_mobile_numbers:
        company["mobile_numbers"] = card_mobile_numbers
        company["mobile_no"] = card_mobile_numbers[0]
    if card_contacts:
        company["contact_persons"] = card_contacts
        company["contact_person"] = card_contacts[0]
    if company.get("card_job_title"):
        company["job_title"] = company["card_job_title"]

    # Printed card emails are authoritative. Never invent name@domain guesses.
    # Rank personal first; keep relevant generics from the same card as a
    # comma-separated set on email / emails.
    if card_emails:
        company["card_emails"] = card_emails
        ranked, joined = _rank_and_keep_person_emails(
            card_emails,
            job_title=company.get("job_title") or "",
            card_emails=card_emails,
        )
        company["emails"] = ranked
        company["email"] = joined
        return company

    # No printed email on the card: keep whatever non-invented emails remain,
    # but do not synthesize local-parts from contact names.
    current_emails = []
    for email in company.get("emails") or _split_email_values(company.get("email")):
        clean = _sanitize_email(email)
        if clean and clean not in current_emails:
            current_emails.append(clean)
    ranked, joined = _rank_and_keep_person_emails(
        current_emails,
        job_title=company.get("job_title") or "",
        card_emails=None,
    )
    company["emails"] = ranked
    company["email"] = joined
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
