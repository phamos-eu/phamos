from __future__ import annotations
import hmac, hashlib, json, base64
from datetime import datetime, timedelta, timezone
from email.utils import getaddresses
from typing import List, Dict
import frappe

# Reuse SOGo helpers from availability.create_event, but get DAV password via caldav.client (decrypt)
from .availability.create_event import _settings, _email as _user_email
from .caldav.client import calendar_item_url as _calendar_url
from .caldav.client import dav_password as _dav_pw
from .caldav.client import put_ics as _put_ics, delete_ics as _delete_ics


def _site_key() -> str:
    key = frappe.local.conf.get("encryption_key") if hasattr(frappe.local, 'conf') else None
    if not key:
        # fall back to site name hash if missing, though encryption_key should exist
        key = frappe.generate_hash()
    return key


def _sign(gid: str, uid: str, exp: int) -> str:
    msg = f"{gid}|{uid}|{exp}".encode()
    sig = hmac.new(_site_key().encode(), msg, hashlib.sha256).hexdigest()
    return sig


def _verify(gid: str, uid: str, exp: int, sig: str) -> bool:
    try:
        if int(exp) < int(datetime.now(timezone.utc).timestamp()):
            return False
    except Exception:
        return False
    good = _sign(gid, uid, int(exp))
    return hmac.compare_digest(good, sig or "")


def _fmt_dt(dt: datetime) -> str:
    return dt.strftime("%Y%m%dT%H%M%S")


def _ics(
    uid: str,
    subject: str,
    start_iso: str,
    end_iso: str,
    description: str = "",
    location: str = "",
    seq: int = 1,
    status: str | None = None,
    organizer: str | None = None,
    attendees: List[str] | None = None,
    method: str | None = None,
) -> str:
    import dateutil.parser
    tz = frappe.get_single("System Settings").time_zone 
    start = dateutil.parser.isoparse(start_iso)
    end = dateutil.parser.isoparse(end_iso)
    desc = (description or "").replace("\r", "\\n").replace("\n", "\\n")
    loc = (location or "").replace("\n", " ")
    summary = (subject or "").replace("\n", " ")
    status_line = f"STATUS:{status}" if status else None
    dtstamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    org_line = f"ORGANIZER:mailto:{organizer}" if organizer else None
    att_lines_list: List[str] = []
    if attendees:
        uniq = []
        for _, addr in getaddresses([(a if isinstance(a, str) else str(a)) for a in attendees]):
            if addr and addr not in uniq:
                uniq.append(addr)
        for a in uniq:
            att_lines_list.append(f"ATTENDEE;ROLE=REQ-PARTICIPANT;PARTSTAT=NEEDS-ACTION;RSVP=TRUE:mailto:{a}")

    # Build lines without indentation; METHOD belongs to VCALENDAR level
    lines: List[str] = [
        "BEGIN:VCALENDAR",
        "VERSION:2.0",
        "PRODID:-//ERPNext//phamos//EN",
    ]
    if method:
        lines.append(f"METHOD:{method}")
    lines.extend([
        "BEGIN:VEVENT",
        f"UID:{uid}",
        f"DTSTAMP:{dtstamp}",
        f"SEQUENCE:{seq}",
        f"SUMMARY:{summary}",
        f"DTSTART;TZID={tz}:{_fmt_dt(start)}",
        f"DTEND;TZID={tz}:{_fmt_dt(end)}",
        f"DESCRIPTION:{desc}",
        f"LOCATION:{loc}",
    ])
    if status_line:
        lines.append(status_line)
    if org_line:
        lines.append(org_line)
    lines.extend(att_lines_list)
    lines.extend([
        "END:VEVENT",
        "END:VCALENDAR",
    ])

    # Use CRLF for better compatibility with strict parsers
    return "\r\n".join(lines) + "\r\n"


def _sogo_put(uid: str, subject: str, start_iso: str, end_iso: str, description: str, location: str, seq: int = 1, status: str | None = None, organizer_user: str | None = None):
    # Reuse working client helper to avoid URL/auth mismatches
    owner = organizer_user or frappe.session.user
    email = owner  # principal matches sync_event behavior
    pw = _dav_pw(email)
    if not (email and pw):
        frappe.throw("Missing DAV credentials for organizer")
    # For SOGo tentative event creation, avoid attendees to prevent auto-invites; include organizer metadata
    organizer_email = None
    try:
        organizer_email = _user_email(owner)
    except Exception:
        organizer_email = None
    ics = _ics(uid, subject, start_iso, end_iso, description, location, seq=seq, status=status, organizer=organizer_email)
    # Delegate to client, which sets headers and auth correctly
    _put_ics(uid, ics, acting_user_id=owner)


def _sogo_delete(uid: str, organizer_user: str | None = None):
    # Reuse client helper for delete as well
    try:
        _delete_ics(uid)
    except Exception:
        # client helper already logs; keep non-fatal
        pass


def _event_desc_with_markers(base_desc: str, group_id: str, uid: str, start_iso: str, end_iso: str, status: str = "Tentative") -> str:
    markers = [
        f"[HYBRID-GROUP: {group_id}]",
        f"[MAILCOW-UID: {uid}]",
        f"[PROPOSAL: {start_iso} -> {end_iso}]",
        f"[STATUS: {status}]",
    ]
    base_desc = base_desc or ""
    return (base_desc + "\n" + "\n".join(markers)).strip()


def _make_select_link(group_id: str, uid: str, ttl_days: int = 14) -> str:
    exp = int((datetime.now(timezone.utc) + timedelta(days=ttl_days)).timestamp())
    sig = _sign(group_id, uid, exp)
    base = frappe.utils.get_url("/api/method/phamos.mailcow_integration.hybrid_meeting.confirm_proposal")
    return f"{base}?gid={group_id}&uid={uid}&exp={exp}&sig={sig}"


def _inject_select_links_table(body_html: str, proposals: List[Dict]) -> str:
    """Ensure proposals table exists and contains a Select column with per-row secure links.

    If an existing table marked data-proposals-table="1" exists, replace it entirely with a
    freshly built table including the Select column. Otherwise, append a new table.
    """
    # Build fresh table HTML with Select column
    def table_html(rows: List[Dict]) -> str:
        esc = frappe.utils.escape_html
        header = (
            '<table class="table table-bordered" data-proposals-table="1" '
            'style="margin-top:8px; width:100%; border-collapse: collapse;">\n'
            '  <tbody>\n'
            f"    <tr><td><strong>{esc(frappe._('Date'))}</strong></td>"
            f"<td><strong>{esc(frappe._('Start'))}</strong></td>"
            f"<td><strong>{esc(frappe._('End'))}</strong></td>"
            # f"<td class=\"text-right\"><strong>{esc(frappe._('Select'))}</strong></td></tr>\n"
            "  </tbody>\n"
            "</table>\n"
        )
        rows_html = "".join(
            [
                "    <tr>"
                f"<td>{esc(r.get('date_str') or '')}</td>"
                f"<td>{esc(r.get('start_str') or '')}</td>"
                f"<td>{esc(r.get('end_str') or '')}</td>"
                # f"<td class=\"text-right\"><a href=\"{r.get('select_link')}\">{esc(frappe._('Select'))}</a></td>"
                "</tr>\n"
                for r in rows
            ]
        )
        return header.replace("  </tbody>", rows_html + "  </tbody>")

    body_html = body_html or ""
    marker = 'data-proposals-table="1"'
    if marker in body_html:
        # Replace existing table
        start = body_html.rfind("<table", 0, body_html.find(marker) + len(marker))
        end = body_html.find("</table>", body_html.find(marker))
        if start != -1 and end != -1:
            end += len("</table>")
            new_tbl = table_html(proposals)
            return body_html[:start] + new_tbl + body_html[end:]
        # Fallback to append if parsing failed
    sep = "<br>" if body_html and not body_html.endswith("\n") else ""
    return body_html + sep + table_html(proposals)


@frappe.whitelist()
def create_proposals_and_send_email(payload: str):
    """Create one Tentative Event per proposal (ERPNext + SOGo), then send an email with selection links.

    Args:
        payload: JSON string with keys: reference_doctype, reference_name, subject, location,
                 email_subject, email_body, recipients, cc, bcc, sender, proposals:[{start,end}]
    """
    data = json.loads(payload) if isinstance(payload, str) else (payload or {})
    proposals: List[Dict] = data.get("proposals") or []
    if not proposals:
        frappe.throw("No proposals provided")
    recipients = (data.get("recipients") or "").strip()
    if not recipients:
        frappe.throw("Recipients required")

    group_id = frappe.generate_hash(length=12)
    reference_doctype = data.get("reference_doctype")
    reference_name = data.get("reference_name")
    event_subject = data.get("subject") or data.get("email_subject")
    location = data.get("location") or ""
    description = frappe.utils.strip_html(data.get("email_body") or "")  # plain desc for event
    organizer_user = frappe.session.user
    try:
        organizer_email = _user_email(organizer_user)
    except Exception:
        organizer_email = None

    formatted_rows: List[Dict] = []
    # Use Frappe's formatter with System Settings to avoid token conversion issues
    try:
        sys_fmt = frappe.db.get_single_value("System Settings", "date_format") or ""
    except Exception:
        sys_fmt = ""
    def format_date_for_email(dtobj: datetime) -> str:
        try:
            return frappe.utils.formatdate(dtobj.date(), sys_fmt or None)
        except Exception:
            return dtobj.strftime("%b %d, %Y")
    created_events: List[str] = []

    # Create events and SOGo entries
    for p in proposals:
        start_iso = p["start"]
        end_iso = p["end"]
        # Create SOGo first to get UID
        # Use sequence=1, STATUS Tentative
        uid = frappe.generate_hash(length=16)
        _sogo_put(uid, event_subject, start_iso, end_iso, description, location, seq=1, status="TENTATIVE", organizer_user=organizer_user)

        # Create ERPNext Event
        ev = frappe.get_doc({
            "doctype": "Event",
            "subject": event_subject,
            "event_type": "Private",
            "starts_on": start_iso,
            "ends_on": end_iso,
            "description": _event_desc_with_markers("", group_id, uid, start_iso, end_iso, status="Tentative"),
            "event_participants": [
                {"reference_doctype": reference_doctype, "reference_docname": reference_name},
            ],
        }).insert(ignore_permissions=True)
        created_events.append(ev.name)

        # Format strings for email link labels
        try:
            import dateutil.parser
            st = dateutil.parser.isoparse(start_iso)
            en = dateutil.parser.isoparse(end_iso)
            # Use system date format for the Date column via Frappe formatter; keep times as HH:mm
            date_str = format_date_for_email(st)
            start_str = st.strftime("%H:%M")
            end_str = en.strftime("%H:%M")
        except Exception:
            date_str, start_str, end_str = start_iso[:10], start_iso, end_iso

        formatted_rows.append({
            "uid": uid,
            "date_str": date_str,
            "start_str": start_str,
            "end_str": end_str,
            "select_link": _make_select_link(group_id, uid),
        })

    # Build the outgoing email content: include proposals table only if requested by UI
    body_html = data.get("email_body") or ""
    include_tbl = bool(int(data.get("include_proposals_in_email") or 0))
    body_with_links = _inject_select_links_table(body_html, formatted_rows) if include_tbl else body_html

    # Collect attachments: payload may include File docnames
    attachments_input = data.get("attachments") or []
    attachments = []
    if attachments_input:
        for fid in attachments_input:
            try:
                fdoc = frappe.get_doc("File", fid)
                attachments.append(fdoc.name)
            except Exception:
                pass

    # Send email via frappe.sendmail
    # Convert attachments to file_url dicts for sendmail compatibility
    attach_dicts = []
    for fid in attachments:
        try:
            fdoc = frappe.get_doc("File", fid)
            if fdoc.file_url:
                attach_dicts.append({"file_url": fdoc.file_url})
        except Exception:
            pass
    # Do not attach ICS on submit; invites are not sent at compose time

    frappe.sendmail(
        recipients=recipients,
        cc=data.get("cc"),
        bcc=data.get("bcc"),
        subject=data.get("email_subject") or event_subject,
        message=body_with_links,
        reference_doctype=reference_doctype,
        reference_name=reference_name,
        sender=data.get("sender") or frappe.session.user,
        attachments=attach_dicts or None,
        send_after=data.get("send_after") or None,
        delayed=(1 if data.get("send_after") else 0),
    )

    return {"group_id": group_id, "events": created_events}


@frappe.whitelist(allow_guest=True)
def confirm_proposal(gid: str, uid: str, exp: str, sig: str):
    """Confirm selected proposal: set chosen to Confirmed, delete others; send final ICS."""
    if not _verify(gid, uid, int(exp), sig):
        frappe.throw("Invalid or expired link")

    # Find all events in group
    event_names = frappe.get_all("Event", filters=[["description", "like", f"%[HYBRID-GROUP: {gid}]%"]], pluck="name")
    if not event_names:
        frappe.throw("No events found for this link")

    chosen = None
    others = []
    for name in event_names:
        ev = frappe.get_doc("Event", name)
        desc = ev.description or ""
        if f"[MAILCOW-UID: {uid}]" in desc:
            chosen = ev
        else:
            others.append(ev)

    if not chosen:
        frappe.throw("Selected proposal not found")

    # Delete other tentative events (ERPNext + SOGo) and keep only the selected one
    for ev in others:
        # extract other UID
        desc = ev.description or ""
        marker = "[MAILCOW-UID: "; idx = desc.find(marker)
        if idx >= 0:
            uid2 = desc[idx + len(marker):].split("]")[0].strip()
            try:
                # delete corresponding SOGo item using the event owner's credentials
                _sogo_delete(uid2, organizer_user=ev.owner)
            except Exception:
                pass
        # delete the ERPNext Event itself
        try:
            ev.delete(ignore_permissions=True)
        except Exception:
            pass

    # Set selected ERPNext Event status to Open and save (triggers sync to SOGo via hooks)
    try:
        # Many ERPNExt instances use Event.status with values like Open/Closed; set to Open
        if hasattr(chosen, "status"):
            chosen.status = "Open"
        chosen.save(ignore_permissions=True)
    except Exception:
        # non-fatal; at minimum we keep the selected Event
        pass

    # Do not send confirmation ICS via email automatically

    return {"ok": True, "message": "Your meeting has been confirmed."}
