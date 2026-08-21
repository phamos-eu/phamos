"""Web services for Lead Data Import."""

from ..lead_data_import import (
    FREE_EMAIL_DOMAINS,
    LEAD_LIST_FIELDS,
    SCRAPE_TIMEOUT,
    _,
    _append_country_from_text,
    _compact_street_name,
    _discover_legal_links,
    _looks_like_postal_address,
    _mistral_extract_lead_fields,
    _parse_address_components,
    _repair_compact_german_address_spacing,
    _sanitize_email,
    _split_email_values,
    _strip_address_company_prefix,
    base64,
    frappe,
    get_files_path,
    os,
    parse_qs,
    quote_plus,
    re,
    requests,
    time,
    unquote,
    urlparse,
)


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
    """Validate and normalize to compact E.164 (e.g. +4917655591059).

    Default region is DE for national numbers starting with 0.
    Strips spaces/parentheses/hyphens and removes the national trunk 0 after
    a country code (+49(0)176… → +49176…).
    """
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

    # Digits only for length checks (before E.164 rewrite).
    digits = re.sub(r"\D", "", phone)
    if not 7 <= len(digits) <= 16:
        return ""

    if len(set(digits)) <= 2:
        return ""

    e164 = _to_e164_phone(phone)
    if not e164:
        return ""

    e164_digits = re.sub(r"\D", "", e164)
    if not 8 <= len(e164_digits) <= 15:
        return ""

    return e164


def _is_mobile_phone(phone):
    """Heuristic: German mobile prefixes 15/16/17 (E.164 or national)."""
    clean = _sanitize_phone(phone) if phone else ""
    digits = re.sub(r"\D", "", clean or str(phone or ""))
    if not digits:
        return False
    if digits.startswith("49"):
        national = digits[2:]
        if national.startswith("0"):
            national = national[1:]
        return national.startswith(("15", "16", "17"))
    if digits.startswith("0"):
        return digits.startswith(("015", "016", "017"))
    return False


def _partition_phones_and_mobiles(phones=None, mobile_numbers=None):
    """Split mixed phone lists into landlines vs mobiles; prefer explicit mobiles."""
    landlines = []
    mobiles = []

    for value in mobile_numbers or []:
        clean = _sanitize_phone(value)
        if clean and clean not in mobiles:
            mobiles.append(clean)

    for value in phones or []:
        clean = _sanitize_phone(value)
        if not clean:
            continue
        if _is_mobile_phone(clean):
            if clean not in mobiles:
                mobiles.append(clean)
        elif clean not in landlines:
            landlines.append(clean)

    # Drop mobiles that were also listed as landlines after mis-classification.
    landlines = [phone for phone in landlines if phone not in mobiles]
    return landlines, mobiles


def _to_e164_phone(phone, default_region="DE"):
    """Convert a validated phone string to compact +CC… E.164."""
    raw = str(phone or "").strip()
    if not raw:
        return ""

    # Keep leading +; treat 00 as international prefix.
    has_plus = raw.startswith("+")
    if raw.startswith("00"):
        has_plus = True
        raw = raw[2:]

    digits = re.sub(r"\D", "", raw)
    if not digits:
        return ""

    if has_plus or (not digits.startswith("0") and len(digits) >= 10):
        # International form. Strip trunk 0 that often appears after country code
        # in German print: +49 (0) 176… → digits 490176… → 49176…
        # Common EU CCs used on cards we see in demos.
        for cc in ("49", "43", "41", "31", "33", "32", "39", "44", "1"):
            if digits.startswith(cc) and len(digits) > len(cc) + 1:
                national = digits[len(cc):]
                if national.startswith("0"):
                    national = national[1:]
                digits = cc + national
                break
        return f"+{digits}"

    # National number (leading 0…) — default to DE.
    if digits.startswith("0"):
        national = digits[1:]
        if default_region == "DE":
            return f"+49{national}"
        return f"+{digits}"

    return f"+{digits}"


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


def _load_card_crop_as_base64(file_url):
    """Crop a small card/photo out of a large dark screenshot and enlarge it."""
    path = _get_file_path_from_url(file_url)
    if not path or not os.path.isfile(path):
        return None, None

    try:
        from io import BytesIO

        import numpy
        from PIL import Image

        image = Image.open(path).convert("RGB")
        width, height = image.size

        # Component detection is done on a small grayscale copy so it remains
        # inexpensive even for large screenshots.
        detection = image.copy()
        detection.thumbnail((500, 500))
        gray = numpy.asarray(detection.convert("L"))
        mask = gray > 35
        visited = numpy.zeros(mask.shape, dtype=bool)
        best = None
        rows, columns = mask.shape

        for start_y, start_x in zip(*numpy.nonzero(mask & ~visited)):
            if visited[start_y, start_x]:
                continue
            stack = [(int(start_y), int(start_x))]
            visited[start_y, start_x] = True
            count = 0
            min_x = max_x = int(start_x)
            min_y = max_y = int(start_y)

            while stack:
                current_y, current_x = stack.pop()
                count += 1
                min_x = min(min_x, current_x)
                max_x = max(max_x, current_x)
                min_y = min(min_y, current_y)
                max_y = max(max_y, current_y)
                for next_y, next_x in (
                    (current_y - 1, current_x),
                    (current_y + 1, current_x),
                    (current_y, current_x - 1),
                    (current_y, current_x + 1),
                ):
                    if (
                        0 <= next_y < rows
                        and 0 <= next_x < columns
                        and mask[next_y, next_x]
                        and not visited[next_y, next_x]
                    ):
                        visited[next_y, next_x] = True
                        stack.append((next_y, next_x))

            if best is None or count > best[0]:
                best = (count, min_x, min_y, max_x + 1, max_y + 1)

        if not best:
            return None, None

        count, min_x, min_y, max_x, max_y = best
        component_ratio = count / mask.size if mask.size else 0
        if not (0.02 <= component_ratio <= 0.60):
            return None, None

        scale_x = width / columns
        scale_y = height / rows
        left = int(min_x * scale_x)
        top = int(min_y * scale_y)
        right = int(max_x * scale_x)
        bottom = int(max_y * scale_y)
        crop_width = right - left
        crop_height = bottom - top
        if crop_width < 100 or crop_height < 100:
            return None, None

        padding = max(12, int(max(crop_width, crop_height) * 0.04))
        cropped = image.crop((
            max(0, left - padding),
            max(0, top - padding),
            min(width, right + padding),
            min(height, bottom + padding),
        ))

        if cropped.width < 1000:
            scale = min(5.0, 1000 / cropped.width)
            cropped = cropped.resize(
                (int(cropped.width * scale), int(cropped.height * scale)),
                Image.Resampling.LANCZOS,
            )

        output = BytesIO()
        cropped.save(output, format="PNG")
        return base64.b64encode(output.getvalue()).decode("utf-8"), "image/png"
    except Exception:
        return None, None


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
