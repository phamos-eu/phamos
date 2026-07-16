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
