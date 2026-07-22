# Functional Calendar Entry

Reusable child table for planning appointments on a **functional Email Account**
calendar (Mailcow/SOGo via CalDAV).

## Parents

| Parent | Table field |
|---|---|
| Team | `custom_team_daily_schedule` |
| Implementation | `appointment_schedule` |
| Department | `custom_appointment_schedule` |
| Employee | `custom_appointment_schedule` |

Registration lives in [`schedule_sync.SCHEDULE_PARENTS`](schedule_sync.py).
Hooks call `sync_events_from_parent` / `cleanup_events_on_parent_trash`.

## Adding another parent

1. Add a Table field with `options: Functional Calendar Entry`.
2. Add the parent DocType → fieldname to `SCHEDULE_PARENTS`.
3. Register the three doc_events in `hooks.py`.
4. On the parent form JS, call `phamos.functional_calendar.setup_email_account_query(frm)`.
5. Ensure the Email Account used on rows has a Mailcow DAV Password.

## Free slots

`Fetch Free Slots` queries the **selected Email Account** mailbox calendar
(not the signed-in user's personal calendar).
