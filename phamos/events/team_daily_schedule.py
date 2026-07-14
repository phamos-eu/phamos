from __future__ import annotations

from email.utils import getaddresses
from datetime import datetime
from functools import lru_cache

import requests

import frappe
from frappe.utils import get_url_to_form

from phamos.mailcow_integration.caldav.client import (
    calendar_item_url,
    dav_password,
    settings,
)
from phamos.mailcow_integration.caldav.ics import vevent


SCHEDULE_TABLE_FIELD = "custom_team_daily_schedule"
SCHEDULE_ROW_DOCTYPE = "Team Daily Schedule"
AUTO_GENERATED_MARKER = "***** Auto Generated *****"


def _normalize_csv_emails(raw_value: str | None) -> str:
    """Parse and deduplicate comma-separated emails while preserving order."""
    emails: list[str] = []
    seen: set[str] = set()

    for _, addr in getaddresses([raw_value or ""]):
        if not addr:
            continue
        key = addr.lower()
        if key in seen:
            continue
        seen.add(key)
        emails.append(addr)

    return ", ".join(emails)


def _row_is_complete(row) -> bool:
    return bool((row.get("subject") or "").strip() and row.get("start") and row.get("end"))


def _row_uid(row_name: str) -> str:
    return f"phamos-team-daily-{row_name}"


def _truncate_error(error_text: str, limit: int = 1400) -> str:
    txt = (error_text or "").strip()
    return txt[:limit]


def _update_row_sync_fields(row_name: str, values: dict):
    if not row_name:
        return
    frappe.db.set_value(SCHEDULE_ROW_DOCTYPE, row_name, values, update_modified=False)


def _mark_row_synced(row_name: str, uid: str, seq: int, mailbox_email: str):
    _update_row_sync_fields(
        row_name,
        {
            "mailcow_uid": uid,
            "mailcow_seq": seq,
            "mailcow_synced": 1,
            "mailcow_last_sync_at": frappe.utils.now_datetime(),
            "mailcow_mailbox": mailbox_email or "",
            "mailcow_last_error": "",
        },
    )


def _mark_row_error(row_name: str, message: str, mailbox_email: str | None = None):
    payload = {
        "mailcow_synced": 0,
        "mailcow_last_error": _truncate_error(message),
    }
    if mailbox_email is not None:
        payload["mailcow_mailbox"] = mailbox_email
    _update_row_sync_fields(row_name, payload)


def _mark_row_deleted_or_skipped(row_name: str):
    _update_row_sync_fields(
        row_name,
        {
            "mailcow_synced": 0,
            "mailcow_last_sync_at": frappe.utils.now_datetime(),
            "mailcow_last_error": "",
        },
    )


@lru_cache(maxsize=256)
def _email_for_account(account_name: str) -> str | None:
    return frappe.db.get_value("Email Account", account_name, "email_id")


def _row_mailbox_email(row) -> str | None:
    if not row:
        return None

    account_name = (row.get("email_account") or "").strip()
    if account_name:
        account_email = (_email_for_account(account_name) or "").strip()
        if account_email:
            return account_email

        parsed = getaddresses([account_name])
        if parsed and parsed[0][1]:
            return parsed[0][1]

    return None


def _sequence_from_doc(doc) -> int:
    try:
        ts = datetime.fromisoformat(str(doc.modified)).timestamp()
        return max(1, int(ts))
    except Exception:
        return 1


def _attendee_role_map(required_csv: str, optional_csv: str) -> dict[str, str]:
    role_map: dict[str, str] = {}
    for _, addr in getaddresses([required_csv or ""]):
        if addr:
            role_map[addr.lower()] = "REQ-PARTICIPANT"
    for _, addr in getaddresses([optional_csv or ""]):
        if addr and addr.lower() not in role_map:
            role_map[addr.lower()] = "OPT-PARTICIPANT"
    return role_map


def _ensure_description_has_source_url(doc, row) -> str:
    source_url = get_url_to_form(doc.doctype, doc.name)
    current_description = (row.get("description") or "").strip()

    if not source_url:
        return current_description

    auto_block = f"{AUTO_GENERATED_MARKER}\n{source_url}"
    if auto_block in current_description:
        return current_description

    if AUTO_GENERATED_MARKER in current_description:
        prefix = current_description.split(AUTO_GENERATED_MARKER, 1)[0].strip()
        new_description = f"{prefix}\n\n{auto_block}" if prefix else auto_block
    else:
        new_description = f"{current_description}\n\n{auto_block}" if current_description else auto_block

    if row.name and new_description != current_description:
        _update_row_sync_fields(row.name, {"description": new_description})
        row.description = new_description

    return new_description


def _attach_source_url_on_row_create(doc, row, previous_row):
    # Only auto-append the source URL when the child row is newly created.
    if previous_row:
        return
    _ensure_description_has_source_url(doc, row)


def _build_ics(row, uid: str, seq: int, organizer: str) -> str:
    required_csv = _normalize_csv_emails(row.get("required_attendees"))
    optional_csv = _normalize_csv_emails(row.get("optional_attendees"))
    return vevent(
        uid=uid,
        seq=seq,
        subject=(row.get("subject") or "").strip(),
        starts_on=row.get("start"),
        ends_on=row.get("end"),
        description=(row.get("description") or "").strip(),
        location=(row.get("location") or "").strip(),
        attendees_to=required_csv,
        attendees_cc=optional_csv,
        attendees_bcc="",
        attendee_role_map=_attendee_role_map(required_csv, optional_csv),
        organizer_email=organizer,
    )


def _put_ics_upsert(uid: str, ics: str, mailbox_email: str) -> tuple[bool, str | None]:
    """Direct upsert in Mailcow (without If-None-Match: * so updates work)."""
    s = settings()
    if not mailbox_email:
        return False, "No mailbox email resolved"

    pw = dav_password(mailbox_email)
    if not pw:
        return False, f"No DAV app password for {mailbox_email}"

    url = calendar_item_url(s.base_url, mailbox_email, uid)
    r = requests.put(
        url,
        data=ics.encode("utf-8"),
        headers={"Content-Type": "text/calendar"},
        auth=(mailbox_email, pw),
        timeout=30,
    )
    if r.status_code not in (200, 201, 204):
        return False, f"Mailcow PUT failed ({r.status_code}): {r.text}"

    return True, None


def _delete_uid_for_mailbox(uid: str, mailbox_email: str) -> tuple[bool, str | None]:
    if not mailbox_email:
        return False, "No mailbox email resolved"

    s = settings()
    pw = dav_password(mailbox_email)
    if not pw:
        return False, f"No DAV app password for {mailbox_email}"

    url = calendar_item_url(s.base_url, mailbox_email, uid)
    r = requests.delete(url, auth=(mailbox_email, pw), timeout=15)
    if r.status_code not in (200, 204, 404):
        return False, f"Mailcow DELETE failed ({r.status_code}): {r.text}"

    return True, None


def _sync_row_to_mailcow(doc, row, mailbox_email: str):
    uid = (row.get("mailcow_uid") or "").strip() or _row_uid(row.name)
    seq = int(row.get("mailcow_seq") or 0) + 1
    ics = _build_ics(row, uid, seq, organizer=mailbox_email)
    ok, error = _put_ics_upsert(uid, ics, mailbox_email=mailbox_email)
    if not ok:
        raise frappe.ValidationError(error or "Unknown Mailcow PUT error")

    _mark_row_synced(row.name, uid=uid, seq=seq, mailbox_email=mailbox_email)


def _cleanup_removed_row_events(doc):
    previous_doc = doc.get_doc_before_save()
    if not previous_doc:
        return

    previous_rows = {
        row.name
        for row in (previous_doc.get(SCHEDULE_TABLE_FIELD) or [])
        if row.name
    }
    current_rows = {
        row.name
        for row in (doc.get(SCHEDULE_TABLE_FIELD) or [])
        if row.name
    }

    previous_rows_by_name = {
        row.name: row
        for row in (previous_doc.get(SCHEDULE_TABLE_FIELD) or [])
        if row.name
    }

    for removed_row_name in previous_rows - current_rows:
        try:
            removed_row = previous_rows_by_name.get(removed_row_name)
            mailbox_email = _row_mailbox_email(removed_row)
            if mailbox_email:
                uid = (removed_row.get("mailcow_uid") or "").strip() or _row_uid(removed_row_name)
                ok, error = _delete_uid_for_mailbox(uid, mailbox_email)
                if not ok:
                    frappe.log_error(error or "Unknown delete error", "Team Daily Schedule Mailcow DELETE")
        except Exception:
            frappe.log_error(frappe.get_traceback(), "Team Daily Schedule Mailcow DELETE")



def _has_schedule_table(doc) -> bool:
    return frappe.get_meta(doc.doctype).has_field(SCHEDULE_TABLE_FIELD)



def sync_events_from_parent(doc, method=None):
    """Sync schedule child rows directly to Mailcow for any parent doctype."""
    if not _has_schedule_table(doc):
        return

    _cleanup_removed_row_events(doc)

    previous_doc = doc.get_doc_before_save()
    previous_rows = (previous_doc.get(SCHEDULE_TABLE_FIELD) or []) if previous_doc else []
    previous_rows_by_name = {
        row.name: row
        for row in previous_rows
        if row.name
    }

    for row in (doc.get(SCHEDULE_TABLE_FIELD) or []):
        if not row.name:
            continue

        mailbox_email = None
        try:
            previous_row = previous_rows_by_name.get(row.name)
            _attach_source_url_on_row_create(doc, row, previous_row)

            mailbox_email = _row_mailbox_email(row)
            previous_mailbox = _row_mailbox_email(previous_row) if previous_row else None

            if not _row_is_complete(row):
                delete_mailbox = mailbox_email or previous_mailbox
                if delete_mailbox:
                    uid = (row.get("mailcow_uid") or "").strip() or _row_uid(row.name)
                    ok, error = _delete_uid_for_mailbox(uid, delete_mailbox)
                    if not ok:
                        _mark_row_error(row.name, error or "Unknown delete error", mailbox_email=delete_mailbox)
                    else:
                        _mark_row_deleted_or_skipped(row.name)
                continue

            if previous_mailbox and mailbox_email and previous_mailbox.lower() != mailbox_email.lower():
                uid = (row.get("mailcow_uid") or "").strip() or _row_uid(row.name)
                ok, error = _delete_uid_for_mailbox(uid, previous_mailbox)
                if not ok:
                    _mark_row_error(row.name, error or "Unknown mailbox move delete error", mailbox_email=previous_mailbox)
                    continue

            if not mailbox_email:
                _mark_row_error(
                    row.name,
                    f"No mailbox resolved for {doc.doctype} {doc.name} row {row.name}",
                )
                continue

            _sync_row_to_mailcow(doc, row, mailbox_email=mailbox_email)
        except Exception:
            _mark_row_error(row.name, frappe.get_traceback(), mailbox_email=mailbox_email)
            frappe.log_error(frappe.get_traceback(), "Team Daily Schedule Mailcow Sync")



def cleanup_events_on_parent_trash(doc, method=None):
    """Delete linked schedule events in Mailcow when parent document is deleted."""
    if not _has_schedule_table(doc):
        return

    for row in (doc.get(SCHEDULE_TABLE_FIELD) or []):
        if not row.name:
            continue
        try:
            mailbox_email = _row_mailbox_email(row)
            if mailbox_email:
                uid = (row.get("mailcow_uid") or "").strip() or _row_uid(row.name)
                ok, error = _delete_uid_for_mailbox(uid, mailbox_email)
                if not ok:
                    frappe.log_error(error or "Unknown delete error", "Team Daily Schedule Mailcow DELETE")
        except Exception:
            frappe.log_error(frappe.get_traceback(), "Team Daily Schedule Mailcow DELETE")
