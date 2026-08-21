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


def _save_companies_without_enrichment(lead_data_import_name, companies):
    """Persist OCR/card companies immediately so the UI can show contacts."""
    saved_keys = set()
    saved_count = 0
    total = len(companies or [])
    for idx, company in enumerate(companies or [], start=1):
        prepared = _prioritize_business_card_emails(dict(company or {}))
        name = prepared.get("company_name", "Unknown")
        if _save_single_company_once(lead_data_import_name, prepared, saved_keys):
            saved_count += 1
            _log(lead_data_import_name, f"[{idx}/{total}] Card saved: {name}")
        else:
            _log(lead_data_import_name, f"[{idx}/{total}] Skipped duplicate: {name}")
    frappe.db.commit()
    return saved_count


def _enrich_existing_lead_data_for_import(lead_data_import_name):
    """Website-enrich already-saved Lead Data rows in place (card-safe)."""
    from ..lead_data_import import (
        LEAD_DATA_DOCTYPE,
        LEAD_DATA_IMPORT_FIELD,
        _build_import_info,
        _lead_data_doc_to_company,
        _normalize_company_dict,
        _populate_lead_data_child_tables,
    )

    settings = _get_phamos_settings()
    if not settings:
        _log(lead_data_import_name, "Skipping website enrichment: Mistral API key not configured.")
        return 0

    doc = frappe.get_doc(LEAD_DATA_IMPORT_DOCTYPE, lead_data_import_name)
    raw_refs = doc.reference_urls or ""
    slugs = [
        s.strip().strip("/")
        for s in raw_refs.splitlines()
        if s.strip() and not s.strip().startswith("#")
    ]
    field_guidance = _get_lead_data_mapping_prompt()

    rows = frappe.get_all(
        LEAD_DATA_DOCTYPE,
        filters={LEAD_DATA_IMPORT_FIELD: lead_data_import_name},
        fields=["name", "organization_name", "website"],
        order_by="creation asc",
    )
    updated = 0
    total = len(rows)
    for idx, row in enumerate(rows, start=1):
        lead_doc = frappe.get_doc(LEAD_DATA_DOCTYPE, row.name)
        company = _lead_data_doc_to_company(lead_doc)
        if not company.get("website"):
            _log(
                lead_data_import_name,
                f"[{idx}/{total}] No website for {row.organization_name or row.name}; skip enrich.",
            )
            continue

        _log(
            lead_data_import_name,
            f"[{idx}/{total}] Enriching from website: {row.organization_name or row.name}",
        )
        try:
            enriched = _enrich_single_company(
                settings,
                slugs,
                company,
                lead_data_import_name,
                ai_fallback=True,
                field_guidance=field_guidance,
            )
        except Exception:
            tb = frappe.get_traceback()
            frappe.log_error(
                title=_("Lead Import progressive enrichment failed"),
                message=tb,
            )
            _log(
                lead_data_import_name,
                _format_error_for_status(
                    f"[{idx}/{total}] Enrichment error for {row.organization_name or row.name}.",
                    tb,
                ),
            )
            continue

        _populate_lead_data_child_tables(lead_doc, enriched, extracted=enriched)
        lead_doc.lead_data = _build_import_info(_normalize_company_dict(enriched))
        lead_doc.save(ignore_permissions=True)
        frappe.db.commit()
        updated += 1
        _log(lead_data_import_name, f"[{idx}/{total}] Updated: {row.organization_name or row.name}")

    return updated


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
            # Prefer the most complete matching address (postal/city), not the shortest.
            def _address_completeness(value):
                parts = _parse_address_components(value)
                return (
                    1 if parts.get("postal_code") else 0,
                    1 if parts.get("city") else 0,
                    1 if parts.get("country") else 0,
                    len(str(value or "")),
                )

            card_addresses[index] = max(matches, key=_address_completeness)
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
    """Use website values only where the business card supplied no value.

    Emails are never filled from the website onto the card person — that would
    invent a person↔mailbox link (e.g. info@). Website people become secondary
    contacts instead.

    Phones: keep card landlines/mobiles authoritative, but if the card only has
    a landline, still accept a website mobile (and vice versa).
    """
    from ..lead_data_import import (
        _partition_phones_and_mobiles,
        _sanitize_phone_list,
    )

    company = dict(company or {})
    extracted = extracted or {}

    list_fields = (
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

    card_phones = _sanitize_phone_list(
        company.get("card_phones") or company.get("phones") or company.get("phone")
    )
    card_mobiles = _sanitize_phone_list(
        company.get("card_mobile_numbers")
        or company.get("mobile_numbers")
        or company.get("mobile_no")
    )
    website_phones = _sanitize_phone_list(
        extracted.get("phones") or extracted.get("phone")
    )
    website_mobiles = _sanitize_phone_list(
        extracted.get("mobile_numbers") or extracted.get("mobile_no")
    )
    website_landlines, website_mobile_only = _partition_phones_and_mobiles(
        website_phones, website_mobiles
    )
    card_landlines, card_mobile_only = _partition_phones_and_mobiles(
        card_phones, card_mobiles
    )

    landlines = list(card_landlines)
    mobiles = list(card_mobile_only)
    if not landlines:
        for phone in website_landlines:
            if phone not in landlines and phone not in mobiles:
                landlines.append(phone)
    if not mobiles:
        for phone in website_mobile_only:
            if phone not in mobiles and phone not in landlines:
                mobiles.append(phone)

    company["phones"] = landlines
    company["phone"] = landlines[0] if landlines else ""
    company["mobile_numbers"] = mobiles
    company["mobile_no"] = mobiles[0] if mobiles else ""
    if company.get("card_phones") is not None or company.get("card_mobile_numbers") is not None:
        # Preserve printed stamps; only extend missing side from website.
        if company.get("card_phones") is None and landlines:
            company["card_phones"] = landlines
        if company.get("card_mobile_numbers") is None and mobiles:
            company["card_mobile_numbers"] = mobiles

    return company


def _build_secondary_contacts_and_addresses(card_company, extracted):
    """Promote impressum/website people and HQ addresses as secondary lists.

    Never merges website emails onto the card person. Conservative person match
    (exact normalized name) skips duplicates of the primary card contact.
    """
    from ..lead_data_import import (
        _addresses_match,
        _clean_contact_person_values,
        _designation_values,
        _persons_are_same,
        _sanitize_email,
        _sanitize_phone_list,
    )

    extracted = extracted or {}
    company_name = (card_company or {}).get("company_name")
    primary_contacts = _clean_contact_person_values(
        (card_company or {}).get("card_contact_persons")
        or (card_company or {}).get("contact_persons")
        or [],
        company_name,
    )

    website_contacts = _clean_contact_person_values(
        extracted.get("contact_persons") or [],
        company_name,
    )
    website_emails = []
    for value in extracted.get("emails") or (
        [extracted.get("email")] if extracted.get("email") else []
    ):
        clean = _sanitize_email(value)
        if clean and clean not in website_emails:
            website_emails.append(clean)
    website_phones = _sanitize_phone_list(extracted.get("phones") or extracted.get("phone"))
    website_mobiles = _sanitize_phone_list(
        extracted.get("mobile_numbers") or extracted.get("mobile_no")
    )
    designations = _designation_values(extracted.get("job_title"), len(website_contacts))

    secondary_contacts = []
    for idx, person in enumerate(website_contacts):
        if any(_persons_are_same(person, primary) for primary in primary_contacts):
            continue
        secondary_contacts.append({
            "name": person,
            "email": website_emails[idx] if idx < len(website_emails) else "",
            "phone": website_phones[idx] if idx < len(website_phones) else "",
            "mobile_no": website_mobiles[idx] if idx < len(website_mobiles) else "",
            "designation": designations[idx] if idx < len(designations) else "",
        })

    card_addresses = list((card_company or {}).get("addresses") or [])
    if (card_company or {}).get("address") and not card_addresses:
        card_addresses = [card_company.get("address")]

    secondary_addresses = []
    for addr in extracted.get("addresses") or []:
        if not addr:
            continue
        if any(_addresses_match(addr, existing) for existing in card_addresses):
            continue
        if any(_addresses_match(addr, existing) for existing in secondary_addresses):
            continue
        secondary_addresses.append(addr)

    return secondary_contacts, secondary_addresses


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
    # card data is authoritative; website people become secondary contacts.
    if card_company is not None:
        card_company = _reconcile_card_with_matching_website_research(
            card_company,
            extracted,
        )
        card_company = _fill_missing_card_fields_from_website(
            card_company,
            extracted,
        )
        secondary_contacts, secondary_addresses = _build_secondary_contacts_and_addresses(
            card_company,
            extracted,
        )
        if secondary_contacts:
            card_company["secondary_contacts"] = secondary_contacts
        if secondary_addresses:
            card_company["secondary_addresses"] = secondary_addresses
        return _prioritize_business_card_emails(
            _attach_business_card_research(card_company, extracted, sources_found)
        )

    merged = _merge_business_card_safe(company, extracted)
    return _prioritize_business_card_emails(merged)
