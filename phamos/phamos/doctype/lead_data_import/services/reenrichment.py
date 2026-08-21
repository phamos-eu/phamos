"""Reenrichment services for Lead Data Import."""

from ..lead_data_import import (
    ENRICHMENT_WORKERS,
    FAST_REEXTRACT_CRAWL_LIMIT,
    LEAD_DATA_IMPORT_DOCTYPE,
    LEAD_DATA_IMPORT_FIELD,
    ThreadPoolExecutor,
    _,
    _build_import_info,
    _ensure_lead_data_import_schema,
    _extract_lead_fields_from_page,
    _fetch_html,
    _finish,
    _format_error_for_status,
    _get_domain_root,
    _get_lead_data_mapping_prompt,
    _get_phamos_settings,
    _has_contact_lead_data,
    _has_direct_contact_lead_data,
    _is_broad_contact_directory,
    _is_preferred_legal_slug,
    _lead_data_doc_to_company,
    _log,
    _merge_company_lead_data,
    _merge_extracted_lead_fields,
    _normalize_company_dict,
    _populate_lead_data_child_tables,
    _prioritize_business_card_emails,
    _reference_urls_for_company,
    as_completed,
    cint,
    frappe,
    re,
)


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

    # Dotted method path so RQ workers resolve the job by import, not pickle.
    # Enqueue immediately after the explicit commit — do not use
    # enqueue_after_commit=True here, or the after-commit hook never fires and
    # the job never enters the queue (UI stuck on Processing).
    frappe.enqueue(
        "phamos.phamos.doctype.lead_data_import.services.reenrichment._run_re_enrichment",
        queue="default",
        timeout=600,
        lead_data_import_name=lead_data_import_name,
        rows_to_refine=rows_to_refine,
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
    from .enrichment import (
        _build_secondary_contacts_and_addresses,
        _fill_missing_card_fields_from_website,
        _reconcile_card_with_matching_website_research,
    )

    existing = _lead_data_doc_to_company(lead_data_doc)
    extracted = extracted or {}

    if "business_card" in str(existing.get("source_type") or "").lower() or lead_data_doc.get("card_email"):
        existing["source_type"] = "business_card"
        if lead_data_doc.get("card_email"):
            existing.setdefault("card_emails", [lead_data_doc.card_email])
        existing = _reconcile_card_with_matching_website_research(existing, extracted)
        existing = _fill_missing_card_fields_from_website(existing, extracted)
        secondary_contacts, secondary_addresses = _build_secondary_contacts_and_addresses(
            existing, extracted
        )
        # Preserve previously saved secondary contacts; append new distinct ones.
        prior_secondary = list(existing.get("secondary_contacts") or [])
        prior_names = {
            (c.get("name") or "").strip().lower() for c in prior_secondary if isinstance(c, dict)
        }
        for contact in secondary_contacts:
            name = (contact.get("name") or "").strip().lower()
            if name and name not in prior_names:
                prior_secondary.append(contact)
                prior_names.add(name)
        if prior_secondary:
            existing["secondary_contacts"] = prior_secondary
        if secondary_addresses:
            existing["secondary_addresses"] = secondary_addresses
        merged = _prioritize_business_card_emails(existing)
    else:
        merged = _merge_company_lead_data(existing, {**(company or {}), **(extracted or {})})

    before = {
        "lead_data": lead_data_doc.lead_data,
        "email": lead_data_doc.email,
        "card_email": lead_data_doc.get("card_email"),
        "phone": lead_data_doc.phone,
        "website": lead_data_doc.website,
        "city": lead_data_doc.city,
        "country": lead_data_doc.country,
        "addresses": [row.address_line_1 for row in lead_data_doc.lead_data_address or []],
        "contacts": [
            (row.first_name, row.last_name, row.email_address, cint(getattr(row, "is_primary", 0)))
            for row in lead_data_doc.lead_data_contact or []
        ],
    }

    _populate_lead_data_child_tables(lead_data_doc, merged, extracted=merged)
    lead_data_doc.lead_data = _build_import_info(_normalize_company_dict(merged))

    after = {
        "lead_data": lead_data_doc.lead_data,
        "email": lead_data_doc.email,
        "card_email": lead_data_doc.get("card_email"),
        "phone": lead_data_doc.phone,
        "website": lead_data_doc.website,
        "city": lead_data_doc.city,
        "country": lead_data_doc.country,
        "addresses": [row.address_line_1 for row in lead_data_doc.lead_data_address or []],
        "contacts": [
            (row.first_name, row.last_name, row.email_address, cint(getattr(row, "is_primary", 0)))
            for row in lead_data_doc.lead_data_contact or []
        ],
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
        failure_message = _format_error_for_status("Error during re-enrichment.", tb)
        try:
            _finish(lead_data_import_name, failure_message)
        except Exception:
            frappe.log_error(
                title=_("Lead Import failed to update status after re-enrichment error"),
                message=frappe.get_traceback(),
            )
            try:
                frappe.db.set_value(
                    LEAD_DATA_IMPORT_DOCTYPE,
                    lead_data_import_name,
                    {
                        "status": "Ready",
                        "status_log": failure_message,
                    },
                )
                frappe.db.commit()
            except Exception:
                frappe.log_error(
                    title=_("Lead Import re-enrichment status fallback failed"),
                    message=frappe.get_traceback(),
                )


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
