"""Enrichment services for Lead Data Import."""

from ..lead_data_import import (
    ENRICHMENT_SLUG_LIMIT,
    ENRICHMENT_WORKERS,
    FAST_REEXTRACT_CRAWL_LIMIT,
    LEAD_DATA_IMPORT_DOCTYPE,
    ThreadPoolExecutor,
    _,
    _discover_internal_links,
    _extract_lead_fields_from_page,
    _fetch_html,
    _format_error_for_status,
    _get_domain_root,
    _get_lead_data_mapping_prompt,
    _get_phamos_settings,
    _has_contact_lead_data,
    _has_direct_contact_lead_data,
    _is_broad_contact_directory,
    _is_preferred_legal_slug,
    _log,
    _merge_extracted_lead_fields,
    _normalize_compare_text,
    _sanitize_phone_list,
    _prioritize_business_card_emails,
    _reference_urls_for_company,
    _save_single_company_once,
    as_completed,
    frappe,
)


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


def _merge_business_card_safe(company, extracted):
    """Merge website data except when the original source is a business card."""
    company = dict(company or {})
    if "business_card" in str(company.get("source_type") or "").lower():
        return company
    return {**company, **{k: v for k, v in (extracted or {}).items() if v and k != "website"}}


def _attach_business_card_research(company, extracted, sources=None):
    """Keep website findings as unstructured research, never as card fields."""
    company = dict(company or {})
    research = {
        key: value for key, value in (extracted or {}).items()
        if value and key != "website"
    }
    if sources:
        research["sources"] = list(sources)
    if research:
        company["website_research"] = research
    return company


def _reconcile_card_with_matching_website_research(company, extracted):
    """Correct OCR typos only when website data matches the same printed value."""
    company = dict(company or {})
    extracted = extracted or {}

    card_addresses = list(company.get("addresses") or [])
    website_addresses = list(extracted.get("addresses") or [])
    for index, card_address in enumerate(card_addresses):
        card_street = _normalize_compare_text(str(card_address).split(",", 1)[0])
        matches = [
            address for address in website_addresses
            if card_street
            and _normalize_compare_text(str(address).split(",", 1)[0]) == card_street
        ]
        if matches:
            # Prefer the concise address over a duplicate carrying a country suffix.
            card_addresses[index] = min(matches, key=lambda value: len(str(value)))
    if card_addresses:
        company["addresses"] = card_addresses
        company["address"] = card_addresses[0]

    card_phones = _sanitize_phone_list(company.get("card_phones") or company.get("phones"))
    website_phones = _sanitize_phone_list(extracted.get("phones"))
    for index, card_phone in enumerate(card_phones):
        card_digits = "".join(character for character in card_phone if character.isdigit())
        matches = []
        for website_phone in website_phones:
            website_digits = "".join(character for character in website_phone if character.isdigit())
            if len(card_digits) >= 7 and card_digits[-7:] == website_digits[-7:]:
                matches.append(website_phone)
        if matches:
            card_phones[index] = matches[0]
    if card_phones:
        company["card_phones"] = card_phones
        company["phones"] = card_phones
        company["phone"] = card_phones[0]

    return company


def _fill_missing_card_fields_from_website(company, extracted):
    """Use website values only where the business card supplied no value."""
    company = dict(company or {})
    extracted = extracted or {}

    list_fields = (
        ("emails", "email"),
        ("phones", "phone"),
        ("mobile_numbers", "mobile_no"),
        ("contact_persons", "contact_person"),
        ("addresses", "address"),
    )
    for list_field, single_field in list_fields:
        current = company.get(list_field) or (
            [company.get(single_field)] if company.get(single_field) else []
        )
        if current:
            continue
        website_values = extracted.get(list_field) or (
            [extracted.get(single_field)] if extracted.get(single_field) else []
        )
        website_values = [value for value in website_values if value]
        if website_values:
            company[list_field] = website_values
            company[single_field] = website_values[0]

    for fieldname in ("company_name", "job_title"):
        if not company.get(fieldname) and extracted.get(fieldname):
            company[fieldname] = extracted[fieldname]

    return company


def _enrich_single_company(settings, slugs, company, lead_data_import_name=None, ai_fallback=True, field_guidance=""):
    name    = company.get("company_name", "Unknown")
    website = company.get("website", "")
    is_business_card = "business_card" in str(company.get("source_type") or "").lower()
    card_company = dict(company) if is_business_card else None

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

    # A website is only a research source for business-card imports. Printed
    # card data is authoritative and website contacts/legal details must not be
    # written into any Lead Data field.
    if card_company is not None:
        card_company = _reconcile_card_with_matching_website_research(
            card_company,
            extracted,
        )
        card_company = _fill_missing_card_fields_from_website(
            card_company,
            extracted,
        )
        return _prioritize_business_card_emails(
            _attach_business_card_research(card_company, extracted, sources_found)
        )

    merged = _merge_business_card_safe(company, extracted)
    return _prioritize_business_card_emails(merged)
