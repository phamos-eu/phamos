# Mailcow Integration — User & Admin Guide (Accurate to Code)

This guide explains how the Mailcow Integration in the phamos app is configured and used. It focuses on what the code actually does: DocTypes, settings, hooks, and the public JS that wires up the UI. Most of it is non-technical, with concrete pointers so admins and users can find the right places in the system.

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
- The email sent to recipients contains a proposals table with per‑row “Select” links. These links are signed and expire.
- If there is exactly one proposal, the app also attaches a Tentative ICS to the outgoing email.

Confirmation flow:
- When a recipient clicks a “Select” link, `hybrid_meeting.confirm_proposal`
	- Keeps the chosen Event (sets status Open), deletes the others (ERPNext + SOGo), and relies on Event hooks to ensure SOGo is in sync.
	- Optionally sends a confirmation email with a final ICS.

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


