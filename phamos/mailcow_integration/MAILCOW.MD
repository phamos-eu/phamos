# Mailcow Integration — User & Admin Guide (Accurate to Code)

This guide explains how the Mailcow Integration in the phamos app is configured a---

## 9) Attendees & Location Implementation

### Overview
Calendar events properly track attendees and location (Jitsi links) so that recipients from hybrid meeting emails are listed as attendees in SOGo calendar events, and meeting links are clickable.

### Event Custom Fields
The following hidden custom fields are added to Event doctype via migrations:

- **`custom_attendees_to`** (Small Text) - TO recipients marked as optional participants
- **`custom_attendees_cc`** (Small Text) - CC recipients marked as optional participants
- **`custom_attendees_bcc`** (Small Text) - BCC recipients marked as optional participants (hidden)
- **`custom_location`** (Data) - Meeting location or URL (e.g., Jitsi link)

**Migrations:**
- `phamos/patches/v1_0/add_event_attendee_fields.py`
- `phamos/patches/v1_0/add_event_location_field.py`

### How Attendees Work

1. **Compose Meeting:** User fills hybrid meeting composer with TO, CC, BCC recipients and the system auto-generates a Jitsi link
2. **Store Metadata:** Event is created with attendees and location stored in custom fields
3. **Recipient Separation:** System automatically separates internal Mailcow users from external recipients based on domain
4. **Optimized Delivery:**
   - **Internal Mailcow users:** Events created directly in their SOGo calendar via CalDAV (no ICS attachment needed)
   - **External recipients:** Receive ICS file attachments in email for importing to their calendars
   - **Mixed (internal + external):** ICS files attached for all recipients (internal users can ignore, external can import)
5. **ICS Generation (for external recipients only):** `caldav/ics.vevent()` extracts custom fields and generates:
   - `LOCATION:` line with the Jitsi URL (auto-clickable in SOGo)
   - `ATTENDEE:` lines for all recipients with RSVP=TRUE (enables auto-invites)
   - `METHOD:REQUEST` to indicate this is a meeting invitation
6. **Sync to SOGo:** Event hooks call `caldav/sync_event.on_upsert()` which syncs events for internal users

### Attendee Roles in ICS

All attendees are marked as **optional participants** with **RSVP enabled**:
- **TO/CC/BCC recipients:** `ROLE=OPT-PARTICIPANT;PARTSTAT=NEEDS-ACTION;RSVP=TRUE`

This means:
- Calendar clients display all attendees in the event details
- **Auto-invites ARE sent** (RSVP=TRUE triggers automatic calendar invitation emails)
- Attendees appear as "optional" rather than "required"
- Recipients receive calendar invitations they can accept/decline in their email clients

### Location Field (Jitsi Links)

- Auto-generated when creating hybrid meetings: `https://meet.jit.si/{15-char-random-id}`
- Stored in `custom_location` field on Event
- Included in ICS as `LOCATION:` field
- SOGo and other calendar apps automatically render URLs as clickable links

### Implementation Files

**Backend:**
- `phamos/mailcow_integration/hybrid_meeting.py` - Stores attendees and location when creating Events
- `phamos/mailcow_integration/caldav/ics.py` - Extended `vevent()` to generate ATTENDEE and LOCATION lines
- `phamos/mailcow_integration/caldav/sync_event.py` - Extracts attendees/location and passes to ICS generator
- `phamos/public/js/hybrid_meeting_composer.js` - Auto-generates Jitsi links via `_generate_jitsi_link()`

### Email Parsing

Handles both plain emails and "Name <email@example.com>" format using Python's `email.utils.getaddresses()`.

### Notes

- Attendees are stored as comma-separated email strings in custom fields
- BCC attendees are visible in the ICS (not truly "blind" in calendar context)
- Custom fields are hidden from Event form UI but accessible programmatically
- Location field syncs bidirectionally: ERPNext → SOGo and SOGo → ERPNext (via pull_events)

---

## 10) Diagram (based on sketch)

- User opens Hybrid Dialog → composes Email + selects Slots → submits
- App creates Tentative SOGo events + ERPNext Events with markers (stores attendees + Jitsi link)
- App checks recipient domains to separate internal (Mailcow) vs external recipients
- **If external recipients exist**: App generates ICS files (one per proposal) with METHOD:REQUEST and RSVP=TRUE
- App sends email with proposals table, "Select" links, and ICS files attached (if external recipients)
- **Internal Mailcow users:** Already have events in SOGo calendar (no ICS needed)
- **External recipients:** Receive calendar invitations in their email clients (can accept/decline)
- Recipient clicks "Select" → App confirms one, deletes others → Event hooks sync final state to SOGo
- App sends confirmation email with final CONFIRMED ICS (only if external recipients exist)

This optimized flow avoids redundancy for internal users while ensuring external recipients get proper calendar invitations.

This is the actual flow reflected in `hybrid_meeting.py`, `caldav/client.py`, `caldav/ics.py`, and `hooks.py`. focuses on what the code actually does: DocTypes, settings, hooks, and the public JS that wires up the UI. Most of it is non-technical, with concrete pointers so admins and users can find the right places in the system.

---

## 1) Components (What exists in this app)

- DocTypes
	- Mailcow Settings (Single)
		- Fields: Base URL, Domain, API Key (Password), Default Quota, Auto Sync Events (Check)
		- Location: `Mailcow Integration > Mailcow Settings`
		- Purpose: Stores Mailcow server URL and an API key used for Mailcow REST endpoints (e.g., creating app passwords).
	- Mailcow DAV Password
		- Fields: User (Link to User, unique), DAV Password (Password), Reset Password (Data)
		- Purpose: Stores each user’s generated DAV app password (for SOGo/CalDAV). The app uses this to authenticate calendar operations.

- Server modules (selected)
	- `mailcow_integration/dav_password.py` — generates Mailcow app passwords via Mailcow API and stores them in “Mailcow DAV Password”.
	- `mailcow_integration/caldav/client.py` — CalDAV helpers for PUT/DELETE ICS, resolve organizer email, and read decrypted DAV password.
	- `mailcow_integration/caldav/sync_event.py` — Hooks to sync ERPNext Event changes to SOGo (on insert/update/delete) and to pull events.
	- `mailcow_integration/availability/next_free_slot.py` — Free slot discovery used by the hybrid composer and Event helper dialog.
	- `mailcow_integration/hybrid_meeting.py` — Orchestrates multi‑slot proposals, emails with “Select” links, and confirmation cleanup.
	- `mailcow_integration/utils.py` — Shared helpers (Mailcow API headers from decrypted API key, mailbox query, timezone, etc.).

- Client (public) JS
	- `public/js/hybrid_meeting_composer.js` — The 2‑column “Schedule Meeting & Email” dialog (email on left, event on right). Fetches slots, manages proposals, injects a proposals table into the email body using System Settings date format, submits to backend.
	- `public/js/event.js` — Adds a “Fetch Free Slots” helper on the Event form with a tabbed slot picker; applies a picked slot to the Event.
	- `public/js/event_list.js` — Adds a “Pull Events” button on the Event list to import events from Mailcow for the current user.
	- `public/js/mailcow_user.js` — Adds “Generate DAV Password” button on the User form to create and store a DAV app password.

- Hooks
	- `hooks.py`
		- Includes: `hybrid_meeting_composer.js` globally for Desk.
		- doctype_js: Event (event.js), User (mailcow_user.js), among others.
		- doctype_list_js: Event list (event_list.js).
		- doc_events on Event: after_insert/on_update → `caldav/sync_event.on_upsert`, on_trash → `caldav/sync_event.on_delete`.

---

## 2) Setup (Admin)

1. Open “Mailcow Settings” (single doctype)
	 - Base URL: your Mailcow base, e.g., `https://mail.example.com`
	 - Domain: your primary Mailcow domain (informational, used by some flows)
	 - API Key: the Mailcow API key (stored encrypted). Used by code via `utils._headers()` to call Mailcow REST endpoints.
	 - Auto Sync Events (optional): the code supports auto ICS sync via Event hooks regardless of this flag; treat it as a feature switch if used in your policies.

2. Generate a DAV password for each user (in User form)
	 - Go to: User > open a user > “Mailcow” group > click “Generate DAV Password”.
	 - This calls `phamos.mailcow_integration.dav_password.generate_dav_password`:
		 - Verifies the mailbox exists in Mailcow (`utils.get_mailbox`).
		 - Calls `create_app_password` against Mailcow API to create an app password for protocol `dav_access`.
		 - Creates/updates a “Mailcow DAV Password” record with the app password.
	 - The app password is used by CalDAV operations (SOGo) in `caldav/client.py`.

3. Verify system settings
	 - System Settings → Time Zone and Date Format: used throughout for consistent display and ICS generation.
	 - User profile email should be correct; the organizer email resolves to the session user’s email in most flows.

---

## 3) Using the Hybrid “Schedule Meeting & Email” dialog (User)

Where:
- On CRM docs (e.g., Lead), a custom button “Schedule Meeting & Email” opens the composer.

What you do:
1. Email side: fill To/CC/BCC, Subject, and Message. Optionally insert an Email Template and select attachments. You can schedule send using “Schedule Send At”.
2. Event side: set a day and duration, click “Fetch Available Slots” (uses `availability.next_free_slot.free_slots_for_day`). Pick one or multiple slots (they appear in the proposals table).
3. Optionally click “Add” or “Add All” to paste a proposals table into your email body. The Date column uses your System Settings date format, Start/End are HH:mm.
4. Click “Create Event & Send Email”.

What happens in the backend:
- For each proposal, `hybrid_meeting.create_proposals_and_send_email` creates a Tentative SOGo entry (via `caldav.client.put_ics`) and an ERPNext Event with markers so they can be managed as a set.
- **Optimized ICS attachment**: The system checks recipient domains and only generates/attaches ICS files if there are external (non-Mailcow) recipients. Internal users already have the events in their SOGo calendar via CalDAV.
- The email sent to recipients contains a proposals table with per‑row "Select" links. These links are signed and expire.

Confirmation flow:
- When a recipient clicks a "Select" link, `hybrid_meeting.confirm_proposal`
	- Keeps the chosen Event (sets status Open), deletes the others (ERPNext + SOGo), and relies on Event hooks to ensure SOGo is in sync.
	- **Sends a confirmation email** with the final confirmed ICS attached (only if external recipients exist) with updated status (CONFIRMED) and incremented sequence number.

---

## 4) Event helpers (User)

- Event form button “Fetch Free Slots”
	- Provided by `public/js/event.js`.
	- Opens a dialog with a tabbed list of free slots (horizontally scrollable). Pick a slot to fill `starts_on` and `ends_on`.

- Event list “Pull Events”
	- Provided by `public/js/event_list.js`.
	- Lets you fetch recent Mailcow events into ERPNext Events for the current user over a date range (up to 90 days). Uses `caldav/sync_event.pull_events`.

---

## 5) How calendar sync works (Plain terms with light detail)

- Outbound (ERPNext → Mailcow):
	- Event hooks (`hooks.py`) call `caldav/sync_event.on_upsert` on new/updated Events and `on_delete` when deleted.
	- The hook builds an ICS (`caldav/ics.vevent`) and uses `caldav/client.put_ics`/`delete_ics` to sync with SOGo, using the session user’s DAV password from “Mailcow DAV Password”.

- Proposals (Hybrid):
	- `hybrid_meeting.py` creates Tentative SOGo entries per proposal (no attendees to avoid auto‑invites), plus ERPNext Events with group/UID markers.
	- Confirmation deletes non‑selected entries and opens the chosen one; SOGo updates are handled by Event hooks.
	- ICS attachments for emails include organizer metadata and METHOD where relevant.

---

## 6) Security & permissions

- “Select” links are signed and time‑limited; the server validates them before confirming a proposal.
- DAV app passwords are created through Mailcow’s API and stored encrypted in the “Mailcow DAV Password” doctype; they are used only for CalDAV calls.
- Only users with permission to create/send emails and Events will see and use these features.

---

## 7) Troubleshooting & FAQs

I don’t see “Generate DAV Password” on a User:
- Ensure you’re on the User form and not creating a new user (button appears when not new). Check role permissions.

Free slots dialog shows nothing:
- Confirm Mailcow Settings (Base URL, API Key) and the user has a DAV password. Then try a different day/duration.

SOGo doesn’t show tentative events from proposals:
- Make sure a DAV password exists for the current session user and the Mailcow base URL is correct. Check server logs for CalDAV errors.

Dates in emails look odd:
- The app uses System Settings → Date Format. Adjust it to the format you expect.

Pulling events fails or returns none:
- Verify the date range (max 90 days) and that the user’s DAV password is valid.

---

## 8) Quick checklist (Admins)

- Mailcow Settings populated: Base URL, API Key, (Domain optional), and you know whether you use Auto Sync Events.
- Users generated DAV passwords via User form → Mailcow → Generate DAV Password.
- System Settings: Time Zone + Date Format; Site URL set.
- Hooks active for Event doc (set in `hooks.py`).

---

## 9) Diagram (based on sketch)

- User opens Hybrid Dialog → composes Email + selects Slots → submits
- App creates Tentative SOGo events + ERPNext Events with markers
- App sends email with proposals and “Select” links
- Recipient clicks “Select” → App confirms one, deletes others → Event hooks sync final state to SOGo
- Optional: App sends final ICS

This is the actual flow reflected in `hybrid_meeting.py`, `caldav/client.py`, and `hooks.py`.


