<!-- Approved plan of 2026-10-15 for the ToDo part of the Personal Cockpit (#1535, #1553–#1562). Kept verbatim; update the status in docs/personal-cockpit-draft.md. -->

# Personal Cockpit ToDos: dashboard, targets, focus mode, day planning, Eisenhower, checklists

Plan written 2026-10-14 (evening) for Wolfram's review on 2026-10-15. He asked for deep planning
with scientific research and product inspiration, and is away, so this plan **makes the decisions
and marks what he should confirm** (section 9). Nothing in it is implemented yet; step 2 (#1541
ToDo list/detail/create/close) sits uncommitted on `feat/1541-personal-cockpit-todos`.

## 1. Context

The Personal Cockpit shows only what is assigned to the logged-in user. Step 1 (Issues, Tasks,
Checklists; MR !929) is in review; step 2 (ToDos list) is built. Wolfram's new direction for the
ToDo part, in his words: the sidebar item "ToDos" opens a **dashboard** and the list becomes a
child "List"; the dashboard must help the user **really close ToDos rather than manage them**
("we churn through our todo list"); a **focus mode** that locks the cockpit to chosen ToDos until
the user breaks out; **day planning** into the user's calendar (Mailcow/SOGo) plus an **Eisenhower
matrix** for today/this week; an **open vs closed ratio**; **gamified, user-set targets** ("close
2 every day for 10 days", "2 planned + 2 spontaneous"); **checklists on ToDos**. Rule: any new
cockpit setting goes into a new module **Cockpits** with a Cockpit Settings page (#1376), never
into phamos Settings.

Three investigations fed this plan: a codebase inventory (what exists, what is broken), an
evidence-graded research dossier (goal setting, implementation intentions, planning fallacy,
gamification/SDT, focus and attention residue, prioritisation, churn, measurement), and a survey
of 12 product groups (Todoist, Microsoft To Do, Sunsama, TickTick, Things, Amazing Marvin, Motion/
Reclaim/Morgen/Akiflow, Forest/Opal/Freedom/Cold Turkey, Habitica, Structured, Frappe apps, Linear/
Jira/Basecamp). The full reports are in this session; the parts that drive decisions are below.

## 2. What the evidence says (and what it rules out)

Design principles the plan applies, each with its evidence grade (A meta-analysis/large RCT,
B solid experiments, C correlational or single study, D practitioner claim):

| # | Principle | Evidence | Applied where |
|---|---|---|---|
| 1 | A ToDo needs a **time slot, not just a date** | Implementation intentions, d≈.3–.65 (A); vaccination field RCT: date+time +4.2 pp, date only n.s. (B) | Day planner places ToDos into calendar slots |
| 2 | **Plan few**: 3–5 committed per day, 1–3 in focus | Planning many goals at once backfires (B); Little's law; attention residue (B) | My Day cap, focus queue |
| 3 | **Calibrate with own history** | Planning fallacy: 30% finish by their own estimate (B); feedback on past accuracy helps (B) | Estimate vs actual factor on the dashboard |
| 4 | Targets **self-set, specific, moderately hard, from the user's baseline, opt-in** | Goal-setting d .42–.80 (A); consent decides whether gamification helps or hurts (B) | Challenge dialog suggests from median; all opt-in |
| 5 | **Forgiveness built in**: jokers, repair, "welcome back", never reset to zero, no all-or-nothing | Broken-streak display lowers engagement (B); reserves raise persistence 55% vs 37% (B); rewarding the return after a miss was the best of 54 interventions, 61k people (A) | Challenge rules and copy |
| 6 | Progress shown with the **small-area rule** | Goal gradient, endowed progress (B) | "3 of 10 done" early, "2 to go" late |
| 7 | Feedback **informs, never controls**; no tangible rewards, no activity badges | Tangible rewards undermine intrinsic motivation d −.3 to −.4; verbal feedback +.3 (A) | Copy, no points shop |
| 8 | **Private, no leaderboard** | Removing rank feedback raised sales 11% (B); mandatory badges+leaderboard lowered grades (B); measurement erodes enjoyment (B); German works-council/GDPR angle | Metrics private by default, no manager view |
| 9 | **Make importance salient at the moment of choice** | Mere-urgency effect (B, replication pending) | Eisenhower payoff prompt, one important slot per day |
| 10 | **Guard against easy-win substitution** | ER physicians picked easy tasks under load, hurting throughput (B) | Important closures counted separately; micro-ToDos excluded from targets |
| 11 | **Close the loop when switching away** | One-minute ready-to-resume plan cuts attention residue (B); a concrete plan removes intrusive thoughts about unfinished goals (B) | Park/exit asks for a resume note |
| 12 | Focus = **voluntary commitment with friction, never a hard lock** | Commitment devices help those who choose them (B); blocking raised stress for some users (C) | Graduated break-out |
| 13 | **Force a decision on stale items; dropping is legitimate** | Churn mechanisms: optimistic planning, urgency bias, easy wins, abstract items (B) | Decide dialog after 3 reschedules; Cancelled = "dropped" |
| 14 | **Reflect daily, review weekly at a landmark** | Shutdown plan aids detachment (B); fresh-start effect (B); reflection 15 min/day +23% (C, working paper) | Shutdown ritual; Monday review (later) |
| 15 | **Measure flow and age, not only counts** | Goodhart; near-miss misreporting (B) | Net flow, lead time, oldest items beside the ratio |

**Do not build** (evidence): punitive streak loss or "streak lost" copy; leaderboards or rankings
among colleagues; targets switched on by managers; points shops, vouchers, badges for activity;
raw "closed count" targets without a quality guard; all-or-nothing rewards; a hard lock or a
mandatory Pomodoro; silent rollover of unfinished items; real-time counters on by default;
myths in UI copy ("23 minutes to refocus", "66 days to a habit", "timeboxing doubles
productivity", the retracted self-imposed-deadlines paper).

**Product patterns copied**: Microsoft To Do's My Day clears nightly and leftovers return as
suggestions; Sunsama's planning ritual (review yesterday → pull in → estimate → capacity check
against 5.5 h → order/timebox → obstacles), rollover counter, "Done for the day"; Amazing Marvin's
procrastination count that only completion clears; Todoist days-off and vacation mode; Duolingo's
two streak freezes; TickTick's Eisenhower quadrants derived from existing fields; Reclaim 2.0 and
Morgen's "propose, then apply" for calendar writes; Opal/Freedom's graduated exits (free in the
first minute, then friction). Nobody tracks "planned vs spontaneous"; that target is new.

## 3. v1 defaults (all user-adjustable)

| Setting | Default |
|---|---|
| Focus session | 3 ToDos (1–5), 25 / 50 min presets or stopwatch, first 60 s free exit, then reason + resume note + 10 s wait that doubles per break-out that day; a meeting from the calendar ends the session |
| Daily target | 2 closes/day; challenge length 10 working days; weekends, Holiday List days and approved leave excluded |
| Jokers | 1 earned per 5 working days, hold at most 2; a missed day can be repaired by closing 2× the target the next day |
| Planned vs spontaneous | "planned" = on the confirmed day plan (confirmation or frozen at 10:00); closed otherwise = spontaneous; created-and-closed within 10 min counts spontaneous at most, max 2/day |
| My Day | Clears at midnight; leftovers become suggestions with a rollover badge; after 3 rollovers a decision is required (today / new slot / delegate / drop) |
| Capacity | 5.5 h of estimated ToDo time minus meetings; soft cap 6 ToDos |
| Eisenhower | important = ToDo `important` flag (seeded from priority High); urgent = due ≤ today + 2 working days; rules in user preferences |
| Overdue | No penalty; visible counter; bonus credit for closing items older than 7 days |
| Notifications | At most 2 per day (plan prompt, shutdown prompt); none during focus |
| Metrics | Private; weekly trend default; the ratio card stays because Wolfram asked for it, paired with net flow and age |

## 4. What the user gets (information architecture)

Sidebar: **ToDos** (parent, opens the dashboard at `/todos`) with children **List**
(`/todos/list`, `/todos/list/:name`), **Plan** (`/todos/plan/:date?`), **Matrix** (`/todos/matrix`).
**Focus** (`/todos/focus`) has no sidebar entry; it is entered from the dashboard, the Decide dialog,
the matrix or the list, and while a session runs every cockpit route redirects there. Children
appear only when their MR ships. Root redirect stays `/todos`.

**Dashboard (`TodosHome.vue`)**, top to bottom:
1. Call-to-action band: one line of state ("4 planned, 1 done") and the buttons *Plan my day* /
   *Start focus* / *Shut down*; the primary one depends on time of day and plan state.
2. Number cards with a 7/30/90-day toggle: Open now, Closed, Dropped, and the **ratio** Wolfram asked
   for (closed in period vs open now), each with "vs previous period".
3. Flow: created vs closed per week with the net number under each bar; "half of your ToDos close
   within P50 days, 85 % within P85". Beside it the **challenge card** (ring, small-area text, jokers
   as reserve, "welcome back").
4. **Oldest open** (age, reschedule badge ↻n, one-click **Decide**) and **Done today** (planned vs
   spontaneous, important starred) with the calibration line ("your 1 h estimates take 1.4 h").
5. Age of open ToDos (buckets) and closed by kind (important / other / dropped).
First-week empty state: one card pointing to the list.

**Decide dialog** (the cheapest anti-churn lever, shared by dashboard, list, shutdown): *Do now*
(→ focus), *Plan* (date; a time slot once the calendar ships), *Later this week*, *Drop* (Cancelled,
with a reason; shown everywhere as "dropped", a legitimate closure). Queue mode for bulk decisions.
"Delegate" is deferred (ToDo has a single assignee; needs assignment semantics).

**List**: unchanged order (date → priority → age); adds an important star, estimate chip, planned
marker, reschedule badge, a "Stale (n)" filter with *Decide all*. Detail adds Important, Estimate,
Planned row, the resume note ("where to pick up") and the **Checklists** section exactly as on Tasks.

**Matrix**: 2×2 for this week's candidates (≤15 shown), HTML5 drag between quadrants (keyboard
1–4 as the non-pointer path). Moving into "important" asks the payoff question ("What happens if
this isn't done this week?", optional note stored as a Comment). Quick actions per card: plan a slot,
start focus, drop.

**Plan (My Day)**: left the candidates (Overdue, Due today, Yesterday's leftovers with rollover
badge, This week, Unscheduled) with estimate chips; right, once the calendar ships, a **day
timeline** 07:00–19:00 (own CSS-grid component, 15-min rows, grey busy blocks from Mailcow, draggable
ToDo blocks, "now" line) and a **capacity bar** (planned vs 5.5 h minus meetings; over → "defer (D)
or drop (Z)"). **Morning ritual** stepper: review yesterday → pick ≤ 6 → estimate → check capacity →
place the top 3 → confirm (preview of calendar writes, then apply). **Shutdown ritual**: done list →
each open planned item gets a next step and a when (Tomorrow / This week / Pick slot / Drop) → tomorrow's
top 3 → one line → "Done for the day". Nothing rolls over silently.

**Focus**: one active ToDo (description, checklist, timer 25/50/stopwatch, estimate vs elapsed), the
queue beside it, *Done* → auto-advance, *Park* → resume note (+ optional slot), quick capture that
creates a ToDo without leaving, "Session complete" at the end. The sidebar dims with "In focus until
11:30"; the header shows the timer. **Break-out** is graduated: free in the first 60 s; afterwards a
reason, a resume note for the current item and a countdown button (10 s, doubling per break-out that
day). No typed sentence, no hard lock, Desk button untouched (it is another app). A calendar meeting
ends the session with the park prompt.

**Targets**: card + dialog. Kinds in v1: *Close N a day* and *N important a day* (MR 6), *N planned +
M spontaneous* (MR 10). Suggested numbers from the user's own median; 10 working days; jokers; "start
on Monday" hint. Copy never contains "streak lost", "failed" or "reset" (enforced by a unit test).

## 5. Data model and backend

**Module `Cockpits`** (`phamos/cockpits/`, listed in `phamos/modules.txt`; created in MR 2 because the
custom fields reference it): `setup.py` (`after_migrate`: `create_custom_fields(..., update=True)` +
property setter), `todo_hooks.py`, `permissions.py`, `workdays.py`, `defaults.py`, `maintenance.py`,
and the doctypes below. **No Cockpit Settings single yet** (no site-wide setting exists; candidates
listed in #1376). Per-user preferences via the DefaultValue pattern of `get_sales_order_kpi_preference`
(`phamos/api/__init__.py:260-296`), keys `cockpit_work_start/end`, `cockpit_capacity_minutes`,
`cockpit_my_day_cap`, `cockpit_focus_minutes`, `cockpit_focus_max_todos`, `cockpit_urgent_days`,
already shipped to the SPA as `sysdefaults`.

**Custom fields on ToDo** (prefix `cockpit_`, module Cockpits, one collapsible section):
`closed_on` Datetime + `closed_by` Link User (stamped in `validate` on Open → Closed/Cancelled,
cleared on reopen; `assign_to.set_status` saves through `doc.save`, so Desk and ERPNext closes are
caught), `important` Check (seeded from priority High), `first_due_date` (set once at insert),
`reschedule_count` Int (+1 when `date` moves later while Open), `estimate_minutes`, `actual_minutes`
(from focus), `resume_note` Small Text. **Property setter**: `ToDo.date` default "" so a ToDo without a
due date stays undated (today every API-created ToDo is "due today"; assignments keep `nowdate()`).
**Backfill patch**: `closed_on`/`closed_by` from the newest Version row that set the status (fallback
`modified`), `first_due_date`, `important`; idempotent, batched, counts reported.
**ToDo hooks**: `before_insert`, `validate`, `on_update` (close → delete future planning Events, mark
started ones Completed, mark today's plan row Done; publish `cockpit_todos_changed` to the user),
`on_trash` (delete linked Checklists and Events, detach plan/focus rows; runs before Frappe's link
check so no LinkExistsError).

**New doctypes** (autoname hash, `user` set from the session, `track_changes 0`, DocPerms System
Manager + `if_owner` for Desk User, plus `permission_query_conditions`/`has_permission` hooks admitting
only the owner and Administrator; registered in `user_data_fields` for GDPR export/erasure):
- **Day Plan** (user, date, status Draft/Confirmed/Closed, confirmed_at, frozen_at, auto_frozen,
  work_start/end, capacity_minutes, meeting_minutes, planned_minutes, calendar_available, shutdown_at,
  reflection) + **Day Plan Item** (todo, summary snapshot, estimate_minutes, slot_start/end,
  calendar_event, added_at, important_at_plan, carried_over, carried_from, outcome
  Done/Moved/Dropped/Open, moved_to, reason, done_in_focus, actual_minutes).
- **Focus Session** (user, status Active/Ended, started_at, planned_minutes, planned_end, ended_at,
  grace_minutes, meeting_at, outcome Completed/Broke out/Expired/Interrupted, break_out_reason,
  day_plan, current_todo) + **Focus Session Item** (todo, summary, started_at, done, done_at, parked,
  resume_note, actual_minutes). One Active per user; the server never refuses `end_focus`.
- **ToDo Challenge** (user, title, kind, target_closes / target_planned / target_spontaneous /
  target_important, start_date, end_date, working_days 10, skip_weekends/holidays/leave, jokers_allowed
  = min(2, days//5), jokers_used, baseline_per_day, status Active/Completed/Ended/Abandoned, days_counted,
  days_met, current_streak, best_streak, last_evaluated_date) + **ToDo Challenge Day** (date,
  working_day, closes, planned_closes, spontaneous_closes, spontaneous_counted, important_closes,
  micro_closes, dropped, counted, target, result Pending/Met/Missed/Joker/Repaired/Skipped).

**Counting rules** (`phamos/cockpits/defaults.py`: MICRO_MINUTES 15, STALE_DAYS 14, STALE_RESCHEDULES 3,
FREEZE_TIME 10:00): for day D, `closed(D)` = my ToDos with `closed_by = me` and `closed_on` on D;
`dropped(D)` = Cancelled by me (shown, never counted); `planned(D)` = closed ∩ plan rows with
`added_at ≤ confirmed_at|frozen_at`; `micro` = created-and-closed within 15 min and not planned
(excluded from targets, shown as "quick wins"); `spontaneous` = the rest, counted up to the
spontaneous target (or the daily target); `important` = `cockpit_important`. Today is computed on
read; past days are materialised into Challenge Day rows by an idempotent `evaluate_challenge` run
lazily on read and nightly. Working days: `cockpit_workweek`, Employee holiday list (`is_holiday`),
approved Leave Applications (guarded if HRMS absent). Joker auto-covers a missed day; a Missed day
becomes Repaired when the next working day closes `target + shortfall`; nothing older than the repair
window ever flips; completion → Completed or **Ended** (never "Failed"); `current_streak` shown only
≥ 2; "Welcome back" after a gap. Suggestion: median closes per working day over the last 20 working
days × 1.2, clamped 1–5, start next Monday.

**Endpoints** (service modules `phamos/api/personal_*.py`, whitelisted wrappers in
`phamos/api/personal_cockpit.py`; every query filters on the session user, no endpoint takes a `user`):
- Dashboard: `get_todo_dashboard(period)` → ratio, flow weeks, lead_time p50/p85, aging, oldest,
  stale, closures, today (done feed, planned/spontaneous/important/dropped, plan status), calibration,
  challenge ring, suggested challenge, day state for the CTA band. Metrics helpers in a neutral
  `phamos/api/dashboard_metrics.py` (`window_metric`, `open_at`, `age_buckets`, `percentile`,
  `weekly_windows`); `department_cockpit._window_metric/_open_at` become aliases, checklist dashboard
  unchanged.
- ToDos: `update_todo` gains `important`, `estimate_minutes`, `resume_note`; `decide_todo(name, action,
  date, reason)`; `drop_todo(name, reason)`.
- Matrix: `get_matrix(scope)`, `set_quadrant(todo, important, urgent, date, payoff_note)`; urgent =
  date set and ≤ today + 2 working days; moving out of "urgent" requires a new date (counts as a
  reschedule).
- Day plan: `get_day_plan(date)`, `add_to_day`, `plan_todo(todo, start, end)` (creates a private
  Frappe Event with `reference_doctype = ToDo`, `send_reminder 0`; the existing Event → SOGo hook
  pushes it), `move_todo_slot`, `unplan_todo`, `set_item_estimate`, `confirm_day_plan`,
  `shutdown_day(date, outcomes, reflection)`; busy blocks from `pull_event_slots` (own ToDo slots
  excluded by UID); `calendar.available` false with a reason instead of an error; 10:00 freeze job.
- Focus: `start_focus(todos, minutes)`, `get_active_focus()` (router guard), `focus_switch`,
  `focus_mark_done`, `focus_park(todo, note, slot?)`, `end_focus(outcome, reason)`; realtime
  `cockpit_focus_changed` to the user's room; expiry job every 5 min; actual minutes feed calibration.
- Challenges: `get_challenges`, `get_challenge`, `create_challenge`, `abandon_challenge`,
  `suggest_challenge`.
- Preferences: `get_cockpit_preferences`, `set_cockpit_preference` (allow-listed keys, ranges).
- Checklists: `"ToDo"` in `CHECKLIST_REFERENCE_DOCTYPES`, title fallback via `personal_todos._summary`,
  `_personal_reference_names` returns Issue/Task/ToDo so my ToDo checklists appear in the personal
  Checklists list and dashboard, `create_checklist`/`checklist_reference_query` accept ToDo in the
  personal scope; Checklist Template `department` stays required (open point).

**Realtime for lists**: a per-user event `cockpit_todos_changed` published from the ToDo hook
(`user=allocated_to`, and the previous assignee on reassignment) and a `useUserRealtime(event,
handler)` composable. Not the site-wide `list_update` room, which carries every user's changes.

## 6. Mailcow CalDAV track (bug fix today, prerequisite for calendar slots)

Verified in `phamos/mailcow_integration/caldav/client.py` and `sync_event.py`: `put_ics` always
sends `If-None-Match: *`, so every Event update is rejected (412) and only logged; `after_insert` +
`on_update` push each new Event twice; `delete_ics` uses the session user's calendar; the push runs
inside the request with a 30 s timeout; `_event_recurrence_rule` uses `get_datetime` without import.
Fix in one MR, QA'd alone with a real mailbox: precondition only on the first push (like
`team_daily_schedule._put_ics_upsert`), remove the `after_insert` hook line, `delete_ics(uid,
acting_user_id)` with `doc.owner`, `frappe.enqueue` after commit (`doc.flags.mailcow_sync_now` for
tests), a `custom_mailcow_sync_error` field next to `custom_mailcow_synched` so the cockpit can show
"not synced: no DAV password" instead of a silent Error Log, the missing import. Untouched:
`pull_events`, `sync_todo.py`, `ics.vtodo`, `create_sogo_event` (dead or broken; noted in #1545).
Self-service DAV passwords are out of scope (the doctype is System Manager only): the planner shows
"Calendar not connected, ask an administrator" and works without it.

## 7. Delivery: ten small MRs

Each is a feature branch from develop, reviewable in one sitting, valuable alone. Sizes S/M/L; days
are implementation incl. tests, excluding review and QA. Total roughly 30–40 developer-days; with two
developers about 5–6 weeks to MR 8, 2–3 more for 9–10.

| # | MR (work item) | Size | Days | Needs | Value alone |
|---|---|---|---|---|---|
| 1 | **#1541** ToDo list/detail/create/close, committed as is **plus** the route move (`/todos/list[/:name]`, `/todos` redirects there, sidebar parent "ToDos" with child "List") | S | 0.5–1 | !929 | My ToDos; no redirects to undo later |
| 2 | **Dashboard: lifecycle fields, flow and age metrics, Decide dialog** (Cockpits module skeleton, custom fields, property setter, hooks, backfill patch, `dashboard_metrics.py`, `get_todo_dashboard`, `decide_todo`/`drop_todo`, `TodosHome`, `DecideTodoDialog`, shared `StatCard`/`HorizontalBars`/`PeriodBars` lifted from `ChecklistsHome` with the dark-mode token fix, `useUserRealtime`) | M | 3–4 | 1 | Honest numbers and a forced decision on stale items |
| 3 | **Checklists on ToDos** (allow-list, title fallback, personal scope, `TodoDetail` section, dialog/filter options, `on_trash` cleanup, non-admin tests) | S/M | 1.5–2.5 | 1 (parallel to 2) | Same checklists as on Issues and Tasks |
| 4 | **Eisenhower matrix** (`cockpit_important` + urgent rule, `workdays.py`, `get_matrix`, `set_quadrant`, `TodosMatrix`, payoff prompt, `eisenhower.js`/`workingDays.js`) | S/M | 2–3 | 2 | Pick the few that matter |
| 5 | **Focus mode** (Focus Session doctypes, endpoints, expiry job, realtime, router guard, locked sidebar, `TodosFocus`, timer, park, graduated break-out, quick capture, `focusRules.js`) | M/L | 4–6 | 2 | Lock in 1–3 ToDos and close them |
| 6 | **Challenges** (ToDo Challenge doctypes, evaluation with jokers/repair, suggestion from baseline, nightly job, `ChallengeCard`, `CreateChallengeDialog`, `challengeProgress.js`; kinds "closes per day" and "important per day") | M | 4–5 | 2 (4 for workdays) | Self-set, private targets |
| 7 | **Mailcow CalDAV fixes** (section 6) | M | 3–4 | none, parallel track | Repairs today's Event sync for everyone |
| 8 | **My Day: plan few, start the day, shut down** (Day Plan doctypes, add/confirm/freeze/shutdown, soft cap 6, leftovers with rollover badge, `TodosPlan` without timeline, morning ritual, shutdown ritual, Done-for-the-day screen) | M | 4–5 | 2 (reuses Decide) | No silent rollover; works without any calendar |
| 9 | **Place ToDos in the calendar** (`plan_todo`/`move`/`unplan` with Events, busy blocks via `pull_event_slots` + cache, `DayTimeline`, `CapacityBar`, `SlotPickerDialog`, estimates, calendar-not-connected state, ToDo → Event cleanup) | L | 6–8 | 7, 8 | Time slots against real meetings |
| 10 | **Planned vs spontaneous** (classification, challenge kind "N planned + M spontaneous", dashboard split) | S | 1–2 | 6, 8 | The target nobody else offers |

Critical path 1 → 2 → 4 → 5 → 6 and 2 → 8 → 9 → 10; 3 and 7 run in parallel. The calendar tail is
last on purpose: the cockpit is useful even if DAV coverage turns out low.

## 8. Risks and mitigations

- **DAV coverage unknown; users cannot self-serve** (doctype is System Manager only; Administrator
  cannot use CalDAV at all). Count DAV rows vs active users before MR 9; planner degrades to "ask an
  administrator".
- **CalDAV latency**: reads with 8 s timeout and a 5-minute per-user/day cache; writes queued after
  commit; the plan renders first, busy blocks when they arrive.
- **Works council / GDPR**: per-person productivity metrics. Private by construction (session-user
  scoping, owner-only doctypes, no manager view, no export, no Energy Points, GDPR data fields);
  challenges and focus opt-in; inform the works council before the pilot if there is one. Not legal
  advice; have it checked.
- **Hard-lock expectation**: the cockpit *is* locked (every route redirects to Focus); only the
  break-out is graduated. If Wolfram wants more, a per-user "strict for N minutes" preference is a
  later S item; no timed refusal.
- **Checklist permissions** are System Manager only in the repo; production grants via Custom DocPerm.
  Hide the section when the user lacks read; MR 3 changes no permissions.
- **`ToDo.date` always set** today; the property setter fixes cockpit-created ToDos, assignments keep
  today's date; urgency therefore uses the reference's own due date when present.
- **Version backfill accuracy**: no Version for `db_set` paths; patch reports counts; lead time is
  labelled "since <backfill>".
- **frappe-ui Calendar** unusable (no drop target, light-only, browser-local time, global shortcuts)
  → own `DayTimeline`, no resize/multi-day in v1.
- **Test users are System Managers** → add a user with only Employee/Desk User roles for every
  ownership and permission test.
- **Goodhart**: closures count only for ToDos created before the day started or planned; micro-ToDos
  excluded; dropped never counts; important counted separately; no leaderboard.
- **Novelty decay**: time-limited challenges; evaluate at 8–12 weeks (section 11).
- **MR 7 changes the Event sync for everyone**: ship alone, QA create/update/delete with a connected
  user and one without a DAV password; the error field makes regressions visible.

## 9. Decisions for Wolfram (defaults chosen so work can start)

| # | Decision | Default in this plan |
|---|---|---|
| 1 | Lock strictness | Graduated break-out, no hard lock, Desk button untouched |
| 2 | Targets opt-in | Yes; nothing runs until the user creates a challenge |
| 3 | Ratio card | Closed in period vs open now, with net flow, lead time and age beside it |
| 4 | When "planned" is fixed | At "Start the day"; 10:00 if never confirmed |
| 5 | Days that don't count | Weekends, holiday list, approved leave, automatically |
| 6 | Work window | User preference → Employee shift → 08:00–17:00; capacity 5.5 h minus meetings; timeline 07–19 |
| 7 | Cockpits module now | Yes (MR 2), Cockpit Settings single only when a real setting appears (#1376) |
| 8 | `important` as its own flag | Yes, seeded from priority High (your judgement vs the assigner's priority) |
| 9 | ToDo `date` default | Property setter removes "Today" (affects Desk's new-ToDo form site-wide) |
| 10 | #1542 Today view | Re-scoped to cross-type "due today" (Issues, Tasks, time) after this programme |
| 11 | Mailcow fixes change sync for everyone | Yes, as a bug fix with its own QA |
| 12 | "Drop" = status Cancelled, reason kept | Yes; shown as "dropped", never deleted |
| 13 | Challenge end states | "Completed" or "Ended", never "Failed" |
| 14 | Not in v1 | Committed mode (typed sentence), delegate action, Monday review, notifications/Reminder, accountability partner, auto-scheduling, process-goal challenges, focus calendar block, Checklist Template department relaxation |

## 10. GitLab work items (created on approval, parent #1535, milestone 87)

New Tasks (house style Why / What / Not in scope / Done when; full drafts exist from the review step):
"Personal Cockpit: ToDos dashboard — closed-on, flow and age metrics, Decide dialog" (MR 2);
"… Checklists on ToDos" (3); "… Eisenhower matrix for today and this week" (4); "… Focus mode (and
module Cockpits)" (5); "… ToDo challenges (self-set targets)" (6); "Mailcow CalDAV: upsert, single
push, owner-correct delete, async with sync status" (7, Issue, Mailcow context); "… My Day — plan
few, start the day, shut down the day" (8); "… Place ToDos in the calendar (Mailcow)" (9);
"… planned vs spontaneous closures" (10); "… opt-in pilot and evaluation (8–12 weeks)".
Updates: #1541 (route move), #1542 (re-scope), #1545 and #290 (VEVENT, not VTODO; linked to 7/9),
#477 (breaks become a Day Plan block type after 9), #1376 (MR 5 creates the module), #1211/#1309
(future work-window source), #1535 umbrella paragraph; `docs/personal-cockpit-draft.md` gets this
plan's status table and a Privacy section.

## 11. Verification

- **Per MR**: FrappeTestCase modules (`test_todo_hooks`, `test_todo_dashboard`, `test_checklist_on_todo`,
  `test_cockpits_eisenhower`, `test_cockpits_focus`, `test_cockpits_challenges`, `test_day_plan`,
  `test_mailcow_sync_event` with `requests` patched) using a non-System-Manager fixture user and the
  `notify_assignment` patch; Vitest for every pure helper (`dashboardFormat`, `eisenhower`,
  `workingDays`, `challengeProgress` incl. forbidden-words test, `focusRules`, `planCapacity`,
  `dayPhase`); run on `~/frappe-bench-v15` (`bench --site erpnext.local run-tests --app phamos
  --module …`, clear cache first) and `cd personal_frontend && yarn test && yarn build`.
- **Browser per MR** (built app on `localhost:8000/personal-cockpit`, dark mode, 768 px, keyboard-only
  path): dashboard numbers against a hand count; Decide → Drop removes the row and bumps "Dropped";
  matrix drag persists and the payoff prompt appears; focus: reload keeps the lock, second tab follows,
  break-out countdown grows; challenge: two closes → green cell, idle day → joker, no "streak" text
  anywhere; plan: confirm, shutdown with Keep/Drop/Tomorrow, leftovers with rollover badge next day;
  calendar: busy blocks match SOGo, a dropped ToDo creates an Event in SOGo and Desk, unconnected user
  sees the fallback.
- **Pilot**: 5–8 volunteers, baseline two weeks of backfilled `closed_on`; per-participant,
  self-read metrics (net flow, lead time P50/P85, age of oldest open, mean reschedule count, planned vs
  done, done vs dropped, focus sessions and share left early); surveys at weeks 4, 8, 12. Success:
  net flow ≥ 0 most weeks, P85 lead time and oldest-open age down vs baseline, drops visible (not
  hidden rollovers), planned-vs-done ≥ 60 % on confirmed days, most focus sessions end with a closure,
  more than half still using it in week 12 with no reported added stress. Flat numbers but stable use
  → keep dashboard and Decide, simplify challenges.

## 12. Immediately after approval

1. Commit #1541 on its branch with the route move, push, open the MR into develop.
2. Create the work items of section 10 and the linked updates.
3. Start MR 2 (dashboard, lifecycle fields, Decide) and, in parallel if a second developer is free,
   MR 7 (Mailcow fixes).

## Privacy

Closed-on dates, lead times, focus sessions, day plans and challenges are per-person productivity
data. In Germany such data is personal data under the GDPR, and a system able to monitor
performance can fall under works-council co-determination (§87(1) No. 6 BetrVG). The design
therefore keeps every metric private to the logged-in user by construction: every endpoint scopes
to the session user and takes no `user` argument, the new doctypes are readable only by their owner
and Administrator (System Managers get no list of other people's data), there is no manager view,
no export and no leaderboard, Energy Points are not used, the doctypes are registered for Frappe's
personal-data download and deletion, and challenges and focus mode are opt-in. If there is a works
council, inform it before the pilot (#1562). This is a design rationale, not legal advice.
