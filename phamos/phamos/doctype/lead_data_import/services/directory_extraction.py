"""Directory Extraction services for Lead Data Import."""

from ..lead_data_import import (
    _clean_html,
    _get_domain_root,
    _mistral_extract_companies_from_html,
    _normalize_url,
    html_lib,
    os,
    re,
    urljoin,
    urlparse,
)


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
