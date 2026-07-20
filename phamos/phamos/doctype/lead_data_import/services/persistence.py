"""Persistence services for Lead Data Import."""

from ..lead_data_import import (
    LEAD_DATA_IMPORT_FIELD,
    _clean_address_values,
    _clean_contact_person_values,
    _clean_job_title_text,
    _is_noise_domain,
    _merge_extracted_lead_fields,
    _normalize_compare_text,
    _normalize_url,
    _normalized_domain,
    _populate_lead_data_child_tables,
    _sanitize_email,
    _sanitize_phone_list,
    frappe,
    re,
)


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
    if lead_data_doc.get("card_email"):
        company["card_emails"] = [lead_data_doc.card_email]

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
