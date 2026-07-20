"""URL input pipeline for Lead Data Import."""

import frappe
from frappe import _


def extract(lead_data_import_name, url):
    """Extract company candidates from a partner-directory or company URL."""
    from .. import lead_data_import as core

    if not url:
        frappe.throw(_("Source URL is required for URL input type."))

    core._log(lead_data_import_name, f"Scraping: {url}")
    html = core._fetch_html(url)
    if not html:
        core._log(
            lead_data_import_name,
            "Could not fetch the page HTML. Treating URL as one company website.",
        )
        return [core._company_from_website_html(None, url)]

    companies = core._extract_companies_from_partner_html(html, url, ai_fallback=False)

    if not companies:
        companies = core._extract_companies_from_links_and_logos(html, url)
        if companies and not core._should_treat_as_directory(html, companies):
            companies = []

    if not companies:
        core._log(lead_data_import_name, "No companies in static HTML. Trying JS render...")
        html = core._fetch_html(url, js_render=True)
        if html:
            companies = core._extract_companies_from_partner_html(html, url, ai_fallback=False)
            if not companies:
                companies = core._extract_companies_from_links_and_logos(html, url)
                if companies and not core._should_treat_as_directory(html, companies):
                    companies = []
            if not companies and core._has_directory_page_signals(html):
                companies = core._mistral_extract_companies_from_html(html, url)

    if not companies:
        core._log(
            lead_data_import_name,
            "No directory companies found. Treating URL as one company website.",
        )
        companies = [core._company_from_website_html(html, url)]

    for company in companies:
        if not company.get("website"):
            company["website"] = core._infer_or_search_website(company)

    core._log(lead_data_import_name, f"Found {len(companies)} companies on the page.")
    if core.MAX_COMPANIES_PER_IMPORT:
        return companies[:core.MAX_COMPANIES_PER_IMPORT]
    return companies

