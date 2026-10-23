# Mailcow / SOGo calendar in the Personal Cockpit (milestone 68)

Plan of 2026-10-23 for https://git.phamos.eu/phamos/phamos/-/milestones/68
"Mailcow User Calendar from Wolfram". Kept in the repo like `personal-cockpit-draft.md`;
the status table is updated as phases ship.

## Direction

Milestone 68 started in July 2026 as "let ERPNext know when a user is free" and produced an
Employee Availability doctype, a "Mailcow Calander" Desk page and Appointment work
(#1211, #1212, #1213, #1230, #1231, #1310, #1311). The need behind it, a per-user availability
scheme (#1292, #1309), was never built, and the Appointment/Raven direction was never agreed.

New direction: bring mailcow/SOGo into the Personal Cockpit (`/personal-cockpit`) so users do
their day-to-day calendar work there instead of in SOGo. First an embedded SOGo, then a real
personal calendar on the Frappe Event doctype, then Leave Applications as all-day events in the
employee's own calendar, later the leave auto-reply from the Leave Application.

| Decision (2026-10-23) | |
|---|---|
| Open milestone-68 items | Parked: the availability scheme (#1292/#1309) becomes Phase 7. #1211, #1230, #1310 and #1311 are proposed for closing as superseded. |
| SOGo host | A subdomain of phamos.eu, so the iframe is same-site; only the framing headers on the mailcow nginx change. |
| Calendar scope | Week view reading SOGo and Frappe Events, then create/edit/delete with all-day and multi-day events, then invites, recurrence and reminders. |
| Leave calendar entry | A Frappe Event (all-day, Private, owned by the employee, reference Leave Application), pushed by the existing Event sync. |

## Phases and status

| Phase | Content | Work item | State |
|---|---|---|---|
| 0 | Shared sync groundwork: all-day, STATUS, URL, METHOD in `ics.vevent`; owner as organizer; `pull_event_slots` all-day flag and timeout; `slot_cache`; Event field `custom_mailcow_status` | tbd | branch `feat/mailcow-calendar-groundwork` |
| 1 | SOGo embedded in the cockpit (`/calendar/sogo`), nginx `frame-ancestors` ops task | tbd | in progress (own session) |
| 2 | Leave Application → all-day Event in the employee's calendar | tbd | planned |
| 3 | My Calendar week view (read: Frappe Events + SOGo, dedupe by UID, connect banner) | tbd | planned |
| 4 | Create, edit, delete from the cockpit; all-day and multi-day | tbd | planned |
| 5 | Invites, recurrence, reminders | tbd | planned |
| 6 | Leave auto-reply from the Leave Application (ManageSieve spike first) | tbd | planned |
| 7 | Availability scheme as work-window source | #1292 / #1309 | parked |

What is reused: `mailcow_integration/caldav/client.py` (`put_ics`, `delete_ics`, `dav_password`),
`caldav/ics.py` (`vevent`), `caldav/sync_event.py` (`on_upsert`, `push_event`, `on_delete`,
`pull_event_slots`), the "***** Auto Generated *****" link block from
`events/team_daily_schedule.py`, the Personal Cockpit façade `api/personal_cockpit.py` and the
section recipe of commit 41e385c5 ("My Contract").

Checked against mailcow's `openapi.yaml` on 2026-10-23: the REST API has no vacation or sieve
endpoint. App passwords (`/api/v1/add/app-passwd`) can carry `sieve_access`, so ManageSieve
(port 4190) is the only programmatic path to an out-of-office reply (Phase 6 spike).

## Work item drafts

House style: Why / What / Not in scope / Done when. Parent: a new umbrella issue, or #1211
rewritten; milestone 68.

### Phase 0 — Mailcow CalDAV: all-day events, status, URL, organizer, slot cache

**Why.** Leave events need all-day entries with a tentative state and a link back; the cockpit
calendar needs a cheap, bounded read of SOGo. Today `vevent` writes only timed CONFIRMED events
with METHOD:REQUEST, a queued push names Administrator as organizer, and `pull_event_slots`
turns all-day events into 24 h blocks with a fixed 30 s timeout.

**What.** `ics.vevent(all_day, status, url, method)` with defaults that keep old callers
unchanged (DTSTART/DTEND VALUE=DATE with exclusive end; STATUS CONFIRMED/TENTATIVE/CANCELLED;
`URL:`; METHOD REQUEST only when attendees exist, else PUBLISH). `push_event` passes the owner's
email as organizer, `all_day`, the new hidden Event field `custom_mailcow_status` and the Desk URL
of `reference_doctype`/`reference_docname`. `pull_event_slots(start, end, timeout=30)` clamps the
timeout and marks every slot with `all_day` plus inclusive `start_date`/`end_date`.
New `caldav/slot_cache.py`: five-minute cache per mailbox and range, dropped after every push or
delete. Tests in `phamos/tests/test_mailcow_sync_event.py` with `requests` patched.

**Not in scope.** VALARM reminders (Phase 5), `pull_events`, VTODO (#1545), self-service DAV
passwords.

**Done when.** The test module passes; an Event with `all_day` shows as an all-day entry in SOGo;
a queued push shows the owner as organizer; the fixture migrates cleanly.

### Phase 1 — Personal Cockpit: SOGo calendar embedded

**Why.** Users should get used to opening their calendar in the cockpit before the cockpit has
its own calendar.

**What.** Nav item "Calendar" with child "SOGo"; route `/calendar/sogo` with a full-height iframe
on `{base_url}/SOGo/so/{email}/Calendar/view` (`client.sogo_calendar_url`) and a permanent
"open in a new tab" link; `personal_calendar.get_calendar_state()`; German strings; MAILCOW.MD
section with the nginx `frame-ancestors` change on the mailcow host.

**Not in scope.** Single sign-on into SOGo; detecting a blocked frame (not possible cross-origin).

**Done when.** With the nginx change the SOGo calendar loads inside the cockpit; without it the
new-tab link works; Administrator and users without Mailcow Settings see an explanation.

### Phase 2 — Leave Application: all-day event in the employee's personal calendar

**Why.** Approved and planned leave should be visible where the employee plans their days and
on their phone, with one click back to the Leave Application.

**What.** `phamos/phamos/hr/leave_calendar.py` hooked on `on_update`, `on_submit`, `on_cancel`,
`on_trash`: one Private all-day Event per Leave Application, owned by the employee's user
(owner set after insert), `send_reminder 0`, subject "Leave (draft): {type}" while unsubmitted
(STATUS TENTATIVE) and "Leave: {type}" once Approved (CONFIRMED), half day in the title,
description with the Desk link; removed on Rejected, Cancelled or delete. Leave form headline
"in {user}'s calendar" / "not synced: {error}" via `get_calendar_state`. Tests skip without
HRMS.

**Not in scope.** Team or approver calendars; the auto-reply (Phase 6).

**Done when.** The QA steps in `docs/mailcow-calendar-plan.md` (draft → approve → cancel,
reject at submit, delete, missing DAV password) all behave as described on a real mailbox.

### Phase 3 — Personal Cockpit: My Calendar week view

**Why.** One week grid with meetings from SOGo and everything ERPNext knows (Events, leave) is
the first screen that can replace SOGo for looking at the day.

**What.** `personal_calendar.get_calendar(from_date, to_date, refresh)`: my Frappe Events
(owner, participant, public; recurring expanded) plus SOGo slots from `slot_cache`, deduplicated
by UID, one event shape with system-timezone strings and all-day dates; `calendar.available`
with a reason instead of an error. `CalendarWeek.vue` with `CalendarWeekGrid` (own CSS grid,
all-day row, now line), read-only `CalendarEventDialog`, connect banner, realtime
`cockpit_calendar_changed`. `/calendar` opens the week; "SOGo" stays as the child item.

**Not in scope.** Writes (Phase 4); editing SOGo-only events; month view.

**Done when.** Frappe Events, SOGo-native events and pushed events appear once each; users
without a DAV password still see their Frappe events; timed events sit at the user's local hour.

### Phase 4 — Personal Cockpit: create, edit and delete events

**What.** `create_event`, `update_event`, `delete_event` through the Event Document API
(owner = session user, `check_permission`, optimistic lock on `modified`, all-day normalised to
00:00:00–23:59:59); dialog create/edit modes; click on a slot creates; drag moves; "Event" in the
Create menu.

**Done when.** An event created in the cockpit appears in SOGo within seconds; participants
cannot edit; deleting removes it from SOGo and Desk.

### Phase 5 — Personal Cockpit: invites, recurrence, reminders

**What.** Attendees from Event Participants and free emails (METHOD:REQUEST, SOGo sends the
invitation), repeat rules with BYMONTHDAY for monthly/yearly, VALARM from a reminder field.

**Done when.** An external attendee receives an invitation; a weekly event repeats; the phone
reminds.

### Phase 6 — Leave Application: auto-reply text and activation

**Spike first.** App password with `sieve_access`, ManageSieve on port 4190, how a phamos script
coexists with SOGo's own script (`include :personal "sogo";` plus a `vacation` block guarded by
`currentdate`). The spike decides whether Phase 6 is built or stays a documented manual step.

**What (if viable).** Fields "Who covers for me", subject and response text with a "Fill from
template" button (from/to dates, cover person); activation on submit with Approved, removal on
cancel; state shown on the form.

### Phase 7 — Availability scheme (parked)

Reuse the data model from #1309 sections 1–3 as the work-window source for My Day and the
free-slot helpers; drop the Raven and Appointment callers unless re-decided.

## Verification

```bash
bench --site erpnext.local run-tests --app phamos --module phamos.tests.test_mailcow_sync_event
bench --site erpnext.local run-tests --app phamos --module phamos.tests.test_leave_calendar
bench --site erpnext.local run-tests --app phamos --module phamos.tests.test_personal_calendar
yarn test:spa
```

Manual QA on a bench with one real mailbox (user U with a Mailcow DAV Password, `host_name`
set so `get_url_to_form` is not localhost):

1. Phase 1: `/personal-cockpit/calendar/sogo` before the nginx change shows the empty frame and
   the new-tab link works; after the change SOGo loads inside the frame.
2. Phase 2: as HR create a draft leave for U (3 days, half day on day 2): SOGo shows an all-day
   tentative "Leave (draft): …" on exactly those days, the URL opens the Leave Application, the
   Desk calendar of U shows the Event. Change dates → the object moves. Approve and submit →
   "Leave: …", confirmed. Cancel, reject at submit and delete of a draft each remove it. Remove
   U's DAV password → the Event exists and the Leave form shows the error.
3. Phase 3/4: as U the week view shows Frappe Events, SOGo-native events and pushed events once;
   create, edit and delete in the dialog reach SOGo; participant and SOGo-only events are
   read-only; a user without a DAV password sees the banner but still their Frappe events.
4. Phase 5: an event with one external attendee produces an invitation; a weekly event shows
   every week; a reminder rings on the phone.

## Risks in the existing code

- Queued pushes wrote `ORGANIZER:mailto:Administrator` (fixed in Phase 0).
- `Mailcow Settings.auto_sync_events` is never read; every Event is pushed.
- `Event.send_reminder` defaults to 1; leave events set it to 0.
- `frappe.desk.doctype.event.event.get_events` hides past events, hence the cockpit's own query.
- Private Events are unreadable for HR client-side; the Leave form reads through the server.
