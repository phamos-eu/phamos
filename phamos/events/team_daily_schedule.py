from __future__ import annotations

from email.utils import getaddresses
from datetime import datetime
from functools import lru_cache
import re

import requests

import frappe
from frappe.utils import get_datetime, get_url_to_form, getdate

from phamos.mailcow_integration.caldav.client import (
    calendar_item_url,
    dav_password,
    settings,
)
from phamos.mailcow_integration.caldav.ics import vevent


SCHEDULE_TABLE_FIELD = "event_schedule"
SCHEDULE_ROW_DOCTYPE = "Team Daily Schedule"
AUTO_GENERATED_MARKER = "***** Auto Generated *****"
EMAIL_RE = re.compile(r"^[^@\s,;<>]+@[^@\s,;<>]+\.[^@\s,;<>]+$")
EMAIL_IN_TEXT_RE = re.compile(r"[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}")


def _looks_like_email(value: str) -> bool:
    return bool(EMAIL_RE.match((value or "").strip()))


def _parse_attendee_field(raw_value: str | None, field_label: str, row_number: int) -> list[str]:
    """Parse attendee input supporting comma, semicolon, and newline separators.

    Raises a validation error for ambiguous inputs (e.g., missing commas between emails).
    """
    raw = (raw_value or "").strip()
    if not raw:
        return []

    normalized = raw.replace(";", ",").replace("\n", ",")
    parts = [part.strip() for part in normalized.split(",") if part.strip()]

    if len(parts) == 1 and len(EMAIL_IN_TEXT_RE.findall(parts[0])) > 1:
        frappe.throw(
            f"Row #{row_number} ({field_label}): multiple email addresses detected without commas. "
            "Please separate each address with a comma.",
            title="Invalid attendee format",
        )

    parsed: list[str] = []
    seen: set[str] = set()

    for part in parts:
        if len(EMAIL_IN_TEXT_RE.findall(part)) > 1:
            frappe.throw(
                f"Row #{row_number} ({field_label}): '{part}' contains more than one email address. "
                "Please separate each address with a comma.",
                title="Invalid attendee format",
            )

        addresses = [addr.strip() for _, addr in getaddresses([part]) if addr and addr.strip()]
        if len(addresses) != 1:
            frappe.throw(
                f"Row #{row_number} ({field_label}): '{part}' is not a valid email entry. "
                "Use formats like 'name@example.com' or 'Full Name <name@example.com>'.",
                title="Invalid attendee format",
            )

        addr = addresses[0]
        if not _looks_like_email(addr):
            frappe.throw(
                f"Row #{row_number} ({field_label}): '{addr}' is not a valid email address.",
                title="Invalid attendee format",
            )

        key = addr.lower()
        if key in seen:
            continue
        seen.add(key)
        parsed.append(addr)

    return parsed


# The row fields that go into the invite (_build_ics, _row_recurrence_rule) or pick its mailbox.
# A row whose fields here are unchanged since the last save is not sent again: the parent
# (Team, Company) gets saved for unrelated reasons, and every PUT raises SEQUENCE, which can
# send attendees an "updated invitation" for an event nobody touched (phamos/phamos#1814).
INVITE_FIELDS = (
    "subject", "location", "description", "start", "end",
    "required_attendees", "optional_attendees", "email_account",
    "repeat_this_event", "repeat_on", "repeat_till",
    "monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday",
)


DATETIME_INVITE_FIELDS = ("start", "end")
DATE_INVITE_FIELDS = ("repeat_till",)


def _invite_value(row, field):
    # The form sends dates as text, the copy from before the save holds date objects.
    value = row.get(field)
    if not value:
        return None
    if field in DATETIME_INVITE_FIELDS:
        return get_datetime(value)
    if field in DATE_INVITE_FIELDS:
        return getdate(value)
    return str(value).strip()


def _invite_unchanged(row, previous_row) -> bool:
    if not previous_row:
        return False
    return all(_invite_value(row, field) == _invite_value(previous_row, field) for field in INVITE_FIELDS)


def _row_is_complete(row) -> bool:
    return bool((row.get("subject") or "").strip() and row.get("start") and row.get("end"))


def _row_uid(row_name: str) -> str:
    return f"phamos-team-daily-{row_name}"


def _truncate_error(error_text: str, limit: int = 1400) -> str:
    """Fit an error into mailcow_last_error. Keeps the END: for a traceback that is the exception
    line, which the cockpit shows (general_management_spa._sync_error_line). Keeping the start cut
    long tracebacks mid-frame and showed a 'File "env/lib/..."' fragment instead (#1949)."""
    txt = (error_text or "").strip()
    return txt if len(txt) <= limit else "…" + txt[-(limit - 1):]


# (connect, read) seconds for the invite PUT. The read part is long because SOGo answers only after
# delivering to every attendee (15 people timed out at 30 s on production, #1949). The sync runs in
# a background job (SYNC_JOB_TIMEOUT), so nobody waits on it.
PUT_TIMEOUT = (10, 120)
SYNC_JOB_TIMEOUT_PER_ROW = 150


def _stored_version_matches(url: str, ics: str, auth) -> bool:
    """After a timed-out PUT: is the event in the calendar with this PUT's SEQUENCE? Then the save
    went through. Any doubt (no answer, other status, older sequence) counts as not stored."""
    sequence = re.search(r"^SEQUENCE:\d+", ics, re.MULTILINE)
    if not sequence:
        return False
    try:
        r = requests.get(url, auth=auth, timeout=30)
    except requests.RequestException:
        return False
    return r.status_code == 200 and re.search(rf"^{sequence.group(0)}\r?$", r.text or "", re.MULTILINE) is not None


def _request_error_message(action: str, error: Exception) -> str:
    """A network failure towards Mailcow (no connection, SSL, timeout) as one readable line."""
    return f"Mailcow {action} failed, server not reachable: {type(error).__name__}: {error}"[:500]


def _http_error_message(action: str, mailbox_email: str, response) -> str:
    """A refused Mailcow request as one readable line. 401/403 means Mailcow rejected the login:
    the mailbox address with the password of its Mailcow DAV Password record. Other statuses keep
    the server's text, without its HTML (nginx sends a whole error page)."""
    if response.status_code in (401, 403):
        return (
            f"Mailcow refused the login of {mailbox_email} ({response.status_code}). "
            "Check its app password in Mailcow (CalDAV allowed) and in its Mailcow DAV Password record."
        )
    text = " ".join(re.sub(r"<[^>]+>", " ", response.text or "").split())[:300]
    return f"Mailcow {action} failed ({response.status_code})" + (f": {text}" if text else "")


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


def _collect_attendees_for_row(row, row_number: int) -> tuple[list[str], list[str]]:
    """Return required/optional attendees with role-safe dedup across both fields."""
    required = _parse_attendee_field(row.get("required_attendees"), "Required Attendees", row_number)
    optional_raw = _parse_attendee_field(row.get("optional_attendees"), "Optional Attendees", row_number)

    required_keys = {addr.lower() for addr in required}
    optional = [addr for addr in optional_raw if addr.lower() not in required_keys]
    return required, optional


def validate_schedule_rows(doc, method=None):
    """Validate and normalize attendee fields before Team save.

    This gives immediate user feedback for malformed attendee lists.
    """
    if not _has_schedule_table(doc):
        return

    for row_number, row in enumerate(doc.get(SCHEDULE_TABLE_FIELD) or [], start=1):
        required, optional = _collect_attendees_for_row(row, row_number)

        required_csv = ", ".join(required)
        optional_csv = ", ".join(optional)

        if (row.get("required_attendees") or "").strip() != required_csv:
            row.required_attendees = required_csv
        if (row.get("optional_attendees") or "").strip() != optional_csv:
            row.optional_attendees = optional_csv


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


def _ensure_row_description_for_sync(doc, row):
    # Keep description canonical before building ICS so Mailcow always receives latest source URL block.
    return _ensure_description_has_source_url(doc, row)

def _row_recurrence_rule(row) -> str | None:
    """Map Team Daily Schedule repeat fields to RFC5545 RRULE."""
    if not row or not row.get("repeat_this_event"):
        return None

    repeat_on = (row.get("repeat_on") or "").strip().lower()
    
    freq = {
        "daily": "DAILY",
        "weekly": "WEEKLY",
        "monthly": "MONTHLY",
        "yearly": "YEARLY",
    }.get(repeat_on)

    if not freq:
        return None

    parts: list[str] = [f"FREQ={freq}"]

    if freq == "WEEKLY":
        weekday_flags = [
            ("monday", "MO"),
            ("tuesday", "TU"),
            ("wednesday", "WE"),
            ("thursday", "TH"),
            ("friday", "FR"),
            ("saturday", "SA"),
            ("sunday", "SU"),
        ]

        selected_days = [
            abbr
            for fieldname, abbr in weekday_flags
            if row.get(fieldname)
        ]

        # Fallback: if no weekday checkbox is selected,
        # use the weekday of the event start.
        if not selected_days and row.get("start"):
            try:
                weekday = get_datetime(row.get("start")).weekday()

                selected_days = [
                    ["MO", "TU", "WE", "TH", "FR", "SA", "SU"][weekday]
                ]
            except Exception:
                selected_days = []

        if selected_days:
            parts.append(
                f"BYDAY={','.join(selected_days)}"
            )

    if row.get("repeat_till"):
        try:
            until_date = get_datetime(
                row.get("repeat_till")
            )

            parts.append(
                f"UNTIL={until_date.strftime('%Y%m%d')}T235959Z"
            )

        except Exception:
            pass

    return ";".join(parts)



def _build_ics(row, uid: str, seq: int, organizer: str) -> str:
    row_number = row.get("idx") or 0
    required_list, optional_list = _collect_attendees_for_row(row, row_number)
    required_csv = ", ".join(required_list)
    optional_csv = ", ".join(optional_list)
    recurrence_rule = _row_recurrence_rule(row)
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
        recurrence_rule=recurrence_rule,
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
    try:
        r = requests.put(
            url,
            data=ics.encode("utf-8"),
            headers={"Content-Type": "text/calendar"},
            auth=(mailbox_email, pw),
            timeout=PUT_TIMEOUT,
        )
    except requests.Timeout as e:
        # SOGo answers only after it has written the event into every attendee's calendar and
        # mailed their invites; with a whole team that can outlast the wait, while the save
        # itself goes through. Ask whether this version arrived before calling it failed (#1949).
        if _stored_version_matches(url, ics, (mailbox_email, pw)):
            return True, None
        return False, (
            f"Mailcow did not answer within {PUT_TIMEOUT[1]} s, and the invite is not in "
            f"{mailbox_email}'s calendar. ({type(e).__name__})"
        )
    except requests.RequestException as e:
        return False, _request_error_message("PUT", e)
    if r.status_code not in (200, 201, 204):
        return False, _http_error_message("PUT", mailbox_email, r)

    return True, None


def _delete_uid_for_mailbox(uid: str, mailbox_email: str) -> tuple[bool, str | None]:
    if not mailbox_email:
        return False, "No mailbox email resolved"

    s = settings()
    pw = dav_password(mailbox_email)
    if not pw:
        return False, f"No DAV app password for {mailbox_email}"

    url = calendar_item_url(s.base_url, mailbox_email, uid)
    try:
        r = requests.delete(url, auth=(mailbox_email, pw), timeout=15)
    except requests.RequestException as e:
        return False, _request_error_message("DELETE", e)
    if r.status_code not in (200, 204, 404):
        return False, _http_error_message("DELETE", mailbox_email, r)

    return True, None


def _sync_row_to_mailcow(doc, row, mailbox_email: str):
    uid = (row.get("mailcow_uid") or "").strip() or _row_uid(row.name)
    seq = int(row.get("mailcow_seq") or 0) + 1
    ics = _build_ics(row, uid, seq, organizer=mailbox_email)
    ok, error = _put_ics_upsert(uid, ics, mailbox_email=mailbox_email)
    if not ok:
        raise frappe.ValidationError(error or "Unknown Mailcow PUT error")

    _mark_row_synced(row.name, uid=uid, seq=seq, mailbox_email=mailbox_email)


def _has_schedule_table(doc) -> bool:
    return frappe.get_meta(doc.doctype).has_field(SCHEDULE_TABLE_FIELD)


# Background sync (#1949, decision 10): a caller sets this flag on the parent before saving, and
# the Mailcow PUT/DELETE then run in a job after the commit instead of inside the request. The
# General Management Cockpit does so for its appointments; Desk saves stay synchronous (#1558).
BACKGROUND_FLAG = "mailcow_sync_in_background"
# Sent to the saving user when a background sync is done, so open pages can reload.
SYNC_DONE_EVENT = "mailcow_schedule_synced"


def _removed_row_deletes(doc) -> list[dict]:
    """UID and mailbox of each row removed since the last save (their invites get cancelled)."""
    previous_doc = doc.get_doc_before_save()
    if not previous_doc:
        return []
    current_rows = {row.name for row in (doc.get(SCHEDULE_TABLE_FIELD) or []) if row.name}
    deletes = []
    for removed_row in previous_doc.get(SCHEDULE_TABLE_FIELD) or []:
        if not removed_row.name or removed_row.name in current_rows:
            continue
        mailbox_email = _row_mailbox_email(removed_row)
        if mailbox_email:
            uid = (removed_row.get("mailcow_uid") or "").strip() or _row_uid(removed_row.name)
            deletes.append({"uid": uid, "mailbox": mailbox_email})
    return deletes


def _sync_plan(doc) -> dict:
    """What Mailcow needs after this save, worked out while the copy from before the save exists.

    Plain data, so a background job can run it. Row steps:
    - {"action": "put", "row", "mailbox", "old_mailbox"}: send the invite (after cancelling it in
      old_mailbox when the sending mailbox changed)
    - {"action": "delete", "row", "uid", "mailbox"}: the row became incomplete; cancel its invite
    Rows without a resolvable mailbox are marked with an error right here (no network involved).
    Unchanged rows are left out: a resend raises SEQUENCE and can mail attendees (#1814).
    """
    previous_doc = doc.get_doc_before_save()
    previous_rows_by_name = {
        row.name: row for row in ((previous_doc.get(SCHEDULE_TABLE_FIELD) or []) if previous_doc else []) if row.name
    }
    steps = []
    for row in doc.get(SCHEDULE_TABLE_FIELD) or []:
        if not row.name:
            continue
        mailbox_email = None
        try:
            previous_row = previous_rows_by_name.get(row.name)
            _ensure_row_description_for_sync(doc, row)

            mailbox_email = _row_mailbox_email(row)
            previous_mailbox = _row_mailbox_email(previous_row) if previous_row else None

            # Handled at an earlier save: synced, or incomplete (then deleted). A row whose
            # last send failed (mailcow_synced 0) is tried again.
            if _invite_unchanged(row, previous_row) and (row.get("mailcow_synced") or not _row_is_complete(row)):
                continue

            if not _row_is_complete(row):
                delete_mailbox = mailbox_email or previous_mailbox
                if delete_mailbox:
                    uid = (row.get("mailcow_uid") or "").strip() or _row_uid(row.name)
                    steps.append({"action": "delete", "row": row.name, "uid": uid, "mailbox": delete_mailbox})
                continue

            if not mailbox_email:
                _mark_row_error(row.name, f"No mailbox resolved for {doc.doctype} {doc.name} row {row.name}")
                continue

            moved_from = (
                previous_mailbox
                if previous_mailbox and previous_mailbox.lower() != mailbox_email.lower()
                else None
            )
            steps.append({"action": "put", "row": row.name, "mailbox": mailbox_email, "old_mailbox": moved_from})
        except Exception:
            _mark_row_error(row.name, frappe.get_traceback(), mailbox_email=mailbox_email)
            frappe.log_error(frappe.get_traceback(), "Team Daily Schedule Mailcow Sync")
    return {"removed": _removed_row_deletes(doc), "rows": steps}


def _run_sync_plan(doc, plan: dict):
    """Talk to Mailcow for a plan from _sync_plan. `doc` is the parent as saved (None: it is gone)."""
    for removed in plan.get("removed") or []:
        try:
            ok, error = _delete_uid_for_mailbox(removed["uid"], removed["mailbox"])
            if not ok:
                frappe.log_error(error or "Unknown delete error", "Team Daily Schedule Mailcow DELETE")
        except Exception:
            frappe.log_error(frappe.get_traceback(), "Team Daily Schedule Mailcow DELETE")

    rows_by_name = {row.name: row for row in ((doc.get(SCHEDULE_TABLE_FIELD) or []) if doc else [])}
    for step in plan.get("rows") or []:
        row = rows_by_name.get(step["row"])
        if not row:
            continue  # removed again before a background run; that save cancels it
        try:
            if step["action"] == "delete":
                ok, error = _delete_uid_for_mailbox(step["uid"], step["mailbox"])
                if not ok:
                    _mark_row_error(row.name, error or "Unknown delete error", mailbox_email=step["mailbox"])
                else:
                    _mark_row_deleted_or_skipped(row.name)
                continue

            if step.get("old_mailbox"):
                uid = (row.get("mailcow_uid") or "").strip() or _row_uid(row.name)
                ok, error = _delete_uid_for_mailbox(uid, step["old_mailbox"])
                if not ok:
                    _mark_row_error(row.name, error or "Unknown mailbox move delete error", mailbox_email=step["old_mailbox"])
                    continue

            _sync_row_to_mailcow(doc, row, mailbox_email=step["mailbox"])
        except Exception:
            _mark_row_error(row.name, frappe.get_traceback(), mailbox_email=step.get("mailbox"))
            frappe.log_error(frappe.get_traceback(), "Team Daily Schedule Mailcow Sync")


def run_sync_plan_in_background(doctype: str, name: str, plan: dict, user: str | None = None):
    """Background job (enqueued after the commit by sync_events_from_parent).

    The rows were marked pending in the request; a crash outside a single step (loading the
    parent, …) must not leave them pending for good, so it marks every planned row with the error.
    """
    try:
        doc = frappe.get_doc(doctype, name) if frappe.db.exists(doctype, name) else None
        _run_sync_plan(doc, plan)
    except Exception:
        for step in plan.get("rows") or []:
            _mark_row_error(step["row"], frappe.get_traceback(), mailbox_email=step.get("mailbox"))
        frappe.log_error(frappe.get_traceback(), "Team Daily Schedule Mailcow Sync")
    finally:
        frappe.db.commit()  # nosemgrep: the row status must be visible before the page reloads
        if user:
            frappe.publish_realtime(SYNC_DONE_EVENT, {"doctype": doctype, "name": name}, user=user)


def sync_events_from_parent(doc, method=None):
    """Sync schedule child rows to Mailcow for any parent doctype.

    With doc.flags.mailcow_sync_in_background, only the plan is made here: rows to send show
    "pending" (mailcow_synced 0, no error) until the job after the commit has run.
    """
    if not _has_schedule_table(doc):
        return

    plan = _sync_plan(doc)
    if not doc.flags.get(BACKGROUND_FLAG):
        _run_sync_plan(doc, plan)
        return
    if not (plan["removed"] or plan["rows"]):
        return
    for step in plan["rows"]:
        _update_row_sync_fields(step["row"], {"mailcow_synced": 0, "mailcow_last_error": ""})
    frappe.enqueue(
        "phamos.events.team_daily_schedule.run_sync_plan_in_background",
        queue="short",
        # each row may wait PUT_TIMEOUT plus the check after a timeout; the short queue's 300 s
        # default would kill a team-wide save midway
        timeout=max(300, SYNC_JOB_TIMEOUT_PER_ROW * (len(plan["rows"]) + len(plan["removed"])) + 60),
        enqueue_after_commit=True,
        doctype=doc.doctype,
        name=doc.name,
        plan=plan,
        user=frappe.session.user,
    )



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
