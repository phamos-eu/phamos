# Personal Cockpit, first draft (phamos/phamos#1535)

Milestone 87 "Cockpit for Todos and other tasks targeted toward personal use".
Branch: `feat/1535-personal-cockpit-draft`, created from `origin/develop` (136d98d0,
which already contains the #1426 autosave/presence work and the renamed
`human_resources_frontend`).

This document started as the build proposal (2026-10-13). The decisions and the
work items below were agreed on 2026-10-14; the first step (#1540, together with
#1456) is implemented on this branch.

## Status and decisions (2026-10-14)

| Topic | Decision |
|---|---|
| Name and route | **Personal Cockpit**, `/personal-cockpit` |
| Tasks | All Tasks the user is assigned to (ToDo with `reference_type = Task`) |
| Issues | "Assigned to me" only; no "Created by me" tab |
| I Own My Work | Retired in this milestone (#1456), same MR as #1540 |
| Cockpit Raven chat | Retired for the moment; restore point and requirements in #1548 (milestone "Raven Integration in Cockpits", after "Upgrade to Raven v3") |
| Time tracking | Later (#1544) |

| Work item | Content | State |
|---|---|---|
| #1540 | Scaffold with my Issues, Tasks, Checklists; shared helpers in `issue_common.py`; personal scope in `department_cockpit.py` | implemented on this branch |
| #1456 | Retire I Own My Work and the cockpit Raven chat; redirects | implemented on this branch |
| #1541 | ToDo list, detail, create, close | open |
| #1542 | Today view | open |
| #1543 | Contacts on ToDos | open |
| #1544 | Time tracking | open, after #1549 |
| #1545 | CalDAV ToDo sync not registered | open |

Where this document and the implementation differ, the implementation wins:
the Issues view has no "Created by me" tab, the Raven deep-link fixes were
replaced by removing the cockpit Raven code, and I Own My Work is retired in the
first MR instead of the last.

## Why

Every cockpit so far (Human Resources, Sales, Accounting, Project Management,
Software Development on its branch) is scoped to a **department** set in phamos
Settings. The Personal Cockpit is scoped to **the logged-in user**: it shows only
work assigned to me, whatever department or project it belongs to.

Three older threads fold into it:

- **I Own My Work** (`frontend/`, `/i-own-my-work`) already shows "Assigned to me" and
  "Created by me" Issues, but it never moved onto the shared cockpit shell, is not
  installable as an app, and #1458 states it will be discontinued. The Personal
  Cockpit is its successor.
- **Milestone "Create PWA for Todo Doctype"** (#260 to #297) describes the ToDo part:
  a list sorted by due date then priority (#292), a detail dialog with the standard
  fields (#294), a clickable reference that opens in a new window (#295), creating a
  ToDo with a reference (#297), a due date that cannot lie in the past (#293), and,
  later, contacts on a ToDo (#296). #263 "find a suitable name" is still open.
- **#478 "Task priority overview"** asks for one view of everything important today,
  whether it is an Issue, a Task, a ToDo or something from a third-party system.

## What the user gets in the first draft

Sidebar of the Personal Cockpit at `/personal-cockpit`:

| Nav item | Route | What it shows | Built from |
|---|---|---|---|
| **Today** (home) | `/today` | Counts of my open ToDos, Issues, Tasks and Checklists; everything overdue or due today across those types; my time today and this week with the running timer, if any | New view; card pattern from `PmImplementationsHub.vue`, KPI cards from `ChecklistsHome.vue` |
| **ToDos** | `/todos`, `/todos/:name` | All my open ToDos (standalone and reference-bound), sorted by date then priority; open, edit, close, create | New `TodoList`, `TodoDetail`, `CreateTodoDialog` in `spa_shared`; row pattern from PM's `ImplementationTodoList.vue` |
| **Issues** | `/issues/list`, `/issues/list/:name` | Issues assigned to me | `IssuesInbox.vue`, `IssueDetail.vue` unchanged |
| **Tasks** | `/tasks/gantt`, `/tasks/gantt/:name` | Tasks assigned to me, Gantt plus detail | `TasksInbox.vue`, `TaskDetail.vue` unchanged except one guard (see Frontend) |
| **Checklists** | `/checklists`, `/checklists/:name`, `/checklists/home` | Checklists I own, plus checklists on my Issues and Tasks; the same dashboard HR has, scoped to me | `ChecklistsInbox.vue`, `ChecklistsHome.vue` unchanged |

Everything is personal, so there is no department picker and no setting to
configure. Any System User can open it.

## How "mine" is defined

Frappe's assignment model is the spine. Every assignment, whether on an Issue, a
Task, a Project or an Implementation, is a **ToDo** row with `allocated_to`,
`reference_type` and `reference_name`. A standalone ToDo has no reference. The
department cockpits already use exactly this for their (unused) `get_inbox`
endpoint, and so does I Own My Work. Nothing in the app filters on `_assign`.

| Record | "Mine" means |
|---|---|
| ToDo | `allocated_to = me`, `status = Open` (the ToDo list shows all of them, with or without reference) |
| Issue | an open ToDo with `reference_type = Issue` points at it; second tab: `owner = me` |
| Task | an open ToDo with `reference_type = Task` points at it |
| Checklist | `checklist_owner = me`, or its `reference_record` is one of my Issues or Tasks |
| Everything else (Project, Implementation, MIS, ...) | shows up only as a ToDo row in the ToDo list, with a Desk link |

One query over my open ToDos therefore feeds the Today counts, the ToDo list and the
name lists that scope the Issue, Task and Checklist views.

## Architecture

### Backend

**New module `phamos/api/personal_cockpit.py`.** Named `_cockpit`, not `_spa`,
because #1455 wants to retire the "spa" abbreviation; the www page follows
(`phamos/www/personal_cockpit.py`, route `/personal-cockpit`). It exposes the same
method names the shared views call on `config.api` (`get_form_options`,
`get_issues`, `get_issue`, `update_issue`, `update_status`, `set_assignees`,
`create_issue`, `create_task_from_issue`, `get_tasks`, `get_task`, `update_task`,
`update_task_status`, `update_task_dates`, `add_task_dependency`,
`set_task_assignees`, `create_task`, `get_checklists`, `get_checklist_dashboard`,
`create_checklist`, `checklist_reference_query`), so the shared views work without
knowing they are in a personal cockpit.

**Personal scope inside the existing engine, not a second engine.**
`phamos/api/department_cockpit.py` is 1200 lines of Issue, Task and Checklist logic
that only differs from what we need in six scope helpers. Proposal: add a `scope`
field to `CockpitConfig` and branch in those helpers.

```python
CONFIG = dc.CockpitConfig(
    label="Personal",
    department_field="",      # unused in personal scope
    project_field="",
    roles=("Employee",),      # only used for the assignee shortlist
    settings_method_name="get_personal_settings",
    scope="personal",         # new; default "department"
)
```

| Helper in `department_cockpit.py` | Department scope (today) | Personal scope (new) |
|---|---|---|
| `_issue_or_filters` | project in department projects, or `custom_department` | `["name", "in", my_issue_names]` from my open ToDos; optionally `["owner", "=", me]` for the "created" view |
| `_issue_in_scope` | department match | assigned to me or created by me |
| `get_tasks` filters | `department = dept` | `["name", "in", my_task_names]` |
| `get_task` check | `doc.department != dept` throws | not assigned to me throws |
| `_department_checklist_references` | department Issues and Tasks | my Issues and Tasks, plus `checklist_owner = me` |
| `_require_department`, `validate_project`, `get_settings` | read phamos Settings | no-op / no project constraint |
| `get_form_options` | department and its projects | `departments` = all, `projects` = all open, `shortlist_users` = Employees, and no department key |
| `create_task` | forces the department | takes the department from the chosen project, if any, and assigns to me |
| `create_issue` | department wrapper | delegate to `i_own_my_work.create_issue`, which already has no department constraint |

Writes keep the existing checks: `doc.check_permission("write")`, field locks via
`presence.assert_fields_unlocked`, and the `modified` timestamp for autosave.

**New endpoints, all in `personal_cockpit.py`:**

| Endpoint | Purpose |
|---|---|
| `get_my_todos(include_closed=0)` | My ToDos, sorted `date asc` (nulls last) then priority High, Medium, Low (#292). Rows use `project_management_spa._serialize_todo_row` extended with `reference_type`, `reference_name`, `reference_title` and `desk_url` |
| `get_todo(name)` | One ToDo for the detail pane |
| `create_todo(description, date=None, priority="Medium", reference_type=None, reference_name=None)` | Inserts through `frappe.get_doc(...).insert()` with `allocated_to = me`, `assigned_by = me`. Rejects a date before today (#293). The reference is a Link to DocType plus Dynamic Link to the record (#297) |
| `update_todo(name, description, date, priority, modified)` | Same optimistic-lock pattern as `update_issue` |
| `close_todo(name)` / `reopen_todo(name)` | Status Closed / Open. Closing a reference-bound ToDo is the same as removing the assignment in Desk, so it goes through `frappe.desk.form.assign_to.remove` to keep `_assign` on the parent in sync |
| `get_today()` | One round trip for the home page: open counts per type; ToDos overdue and due today; my Issues with `resolution_by` and my Tasks with `exp_end_date` up to today; my time today and this week plus the active timer session from `dev_action_panel.get_time_stats` and `get_active_session` |
| `get_personal_settings()` | Returns `{}` for now; keeps the `settingsMethod` contract so `TimesheetPanel` can come back later |
| `check_app_permission()` | Not Guest, not Website User. No role needed: every System User has personal work |

Going through the document API (not `frappe.db.set_value`) matters: Frappe's ToDo
controller keeps `_assign` on the parent in sync, applies its own per-user
permission query conditions, and would fire the dormant CalDAV ToDo sync
(`mailcow_integration/caldav/sync_todo.py`) if it ever gets wired into `hooks.py`.

**Wiring (the same 27-file recipe as commit 9b5e61ed, the Software Development
cockpit):**

- `phamos/hooks.py`: Apps-screen tile (logo `/assets/phamos/manifest/personal-icon-192.png`, title "Personal", route `/personal-cockpit`) and the two `website_route_rules`.
- `spa_shared/scripts/generate_app_manifests.py`: `APPS` entry `{slug: "personal", name: "Personal", route: "/personal-cockpit", color: "#0e7490", symbol: "user"}` (cyan-700, a -700 shade no cockpit tile uses yet; rose, orange, emerald, violet and slate are taken), then run the script for the manifest and icons.
- `phamos/tests/test_app_manifests.py`: `"personal_frontend": "/personal-cockpit"` in `FRONTENDS`.
- `.gitignore`: `phamos/public/personal` and `phamos/www/personal_cockpit.html`.
- Root `package.json`: `personal_frontend` in `install:frontends` and `build`, plus `dev:personal`.
- `phamos/translations/de.csv`: "Open in Personal Cockpit".
- No phamos Settings fields and no patch: the cockpit has nothing to configure.

**Raven deep links.** `issue_raven._spa_path_for` sends Issues and Checklists to
`/i-own-my-work/...` and Tasks to `/<cockpit>/tasks/<name>`. Neither matches a
frontend route today (the routers use `/issues/list/:name`, `/tasks/gantt/:name`
and `/checklists/:name`, and there is no catch-all). When I Own My Work is
retired, point Issues and Checklists at `/personal-cockpit/issues/list/<name>` and
`/personal-cockpit/checklists/<name>`, fix the Task path, and add a
`website_redirects` rule `/i-own-my-work(/.*)?` to `/personal-cockpit`, exactly as
was done for `/hr-cockpit`.

### Frontend

**New package `personal_frontend/`**, copied from the Software Development
scaffold (commit 9b5e61ed on `feat/1462-software-development-cockpit`, which is
the Human Resources package with names swapped):

| File | Value |
|---|---|
| `package.json` | name `personal-cockpit-ui`; build `--base=/assets/phamos/personal/`; `copy-html-entry` to `phamos/www/personal_cockpit.html` |
| `vite.config.js` | port **8087** (8086 is Software Development); `outDir ../phamos/public/personal` |
| `index.html` | title "Personal", manifest links to `/assets/phamos/manifest/personal-*` |
| `src/config.js` | `api: "phamos.api.personal_cockpit"`, `label: "Personal"`, `slug: "personal"`, `basePath: "/personal-cockpit"`, `settingsMethod: "get_personal_settings"`, `barColorStyleId: "personal-gantt-bar-colors"`, **no `departmentField`, no `projectField`** |
| `src/router.js` | `createSpaRouter({ config, rootRedirect: "/today", routes: [/today, /todos, /todos/:name, /checklists/home] })` |
| `src/App.vue` | `CockpitSidebar label="Personal" storage-key="personal-cockpit-sidebar-collapsed"` with the five nav items above |
| `src/main.js` | dev boot URL `phamos.www.personal_cockpit.get_context_for_dev` |
| `tailwind.config.js`, `postcss.config.cjs`, `main.css` | unchanged |

**Small changes in `spa_shared` (all backwards compatible for the department cockpits):**

1. `views/TasksInbox.vue` lines 97 to 98 block the Gantt unless `formOptions[config.departmentField]` is truthy. Only check when `config.departmentField` is set.
2. `views/ChecklistsInbox.vue` line 188 hard-codes "create a checklist for an HR Issue or Task". Use `config.label`.
3. `components/CreateIssueDialog.vue` lines 167 to 170 default department and project from the department config. Add `assign_to` defaulting to the session user when `config.personal` is true, so a new Issue stays in my scope.
4. (Dropped 2026-10-14: no "Created by me" tab.)
5. `components/AssigneePicker.vue`: an "Assign to me" chip. Useful in every cockpit, essential here.

**New shared components** (in `spa_shared` so Project Management's
`ImplementationTodoList` can converge on them later):

- `components/TodoList.vue`: rows with description (plain text, first line), due date with overdue styling, priority badge, reference pill (`FrappeLink`-style preview via `link_preview.get_link_preview_lines`), Desk link in a new tab (#295), Close button.
- `components/TodoDetail.vue`: the standard fields (#294) with an explicit Save button in the first draft, so no field locks are needed for ToDo (`presence.LOCKABLE_DOCTYPES` stays as it is). Inline autosave can follow once the pattern is proven.
- `components/CreateTodoDialog.vue`: description, date (default today, no past dates), priority, optional reference (DocType select limited to Issue, Task, Project, Implementation, Customer, Lead, Opportunity, Contact, plus a `FrappeLink` for the record).
- `utils/todoSort.js`: pure sort helper (date ascending, nulls last, then priority), unit-tested with Vitest.

**Today view** (`personal_frontend/src/views/TodayHome.vue`): four count cards
linking into the lists, then two columns: "Due today and overdue" (ToDos, Issues,
Tasks mixed, each row linking to its detail route) and "Time" (today, this week,
running timer). Built from the single `get_today()` call. Realtime refresh via
`useDocRealtime` on `ToDo` list updates can come later.

## Delivery plan

Five merge requests into `develop`, each small enough for one review. After
each: QA on the test system, cherry-pick onto `version-15`, staging, production
(the release path from #1458).

Revised 2026-10-14: MR 1, 2 and 5 of the original plan became one MR (#1540 + #1456).

| MR | Content | Done when |
|---|---|---|
| #1540 + #1456 | Scaffold `personal_frontend`, API and www module, hooks, manifest and icons; personal scope for Issues, Tasks and Checklists; retire I Own My Work, the `frontend/` package and the cockpit Raven chat; redirects | The cockpit installs as its own app and lists my Issues, Tasks and Checklists; `/i-own-my-work` redirects; department cockpits unchanged |
| #1541 | ToDos: endpoints, `TodoList`, `TodoDetail`, `CreateTodoDialog`, sort helper, due-date rule | List, detail, create and close work as described in #1541 |
| #1542 | Today: `get_today()` and `TodayHome.vue`, including time from `dev_action_panel` | One screen answers "what is important today" |

Time in the cockpit (#1544) depends on fixing one thing first (#1549): `dev_action_panel.pause_timer`,
`resume_timer` and `stop_timer` (exposed through `api/timesheet_timer.py`) do not
check that the Timesheet Record belongs to the caller. Showing the timer in a
personal cockpit is the moment to add that check.

## Testing

- `phamos/tests/test_personal_cockpit.py` (FrappeTestCase, same conventions as `test_department_cockpit.py`):
  - parity: the whitelisted names of `personal_cockpit` are a superset of `human_resources_spa` (pattern from `test_software_development_cockpit.py` on feat/1462);
  - scope: user A assigned to Issue X sees it, user B does not; a Task without my ToDo is rejected by `get_task`; a Checklist I own but on someone else's Issue is listed;
  - ToDos: sort order, past date rejected, close goes through `assign_to.remove` and clears `_assign` on the parent, Website User gets no access;
  - `get_today()` buckets (overdue, today, later).
- `test_app_manifests.py` covers the new manifest automatically once `FRONTENDS` has the entry.
- Vitest: `spa_shared/utils/todoSort.test.js`.
- Manual, per the #1458 steps: install in Chrome, cmd-tab shows the new icon, Desk opens in the browser; light and dark mode; long German labels do not break the sidebar (#1457 is still open, texts stay English for now).

## Not in the first draft

- Contacts on a ToDo (#1543).
- Raven mentions or unread counts: there is no API for it yet.
- My OKRs (`OKR.responsible_person`), leave balance, upcoming leave: good second-draft candidates.
- Calendar: `mailcow_integration/availability` can return my busy and free slots for today, but it needs a Mailcow DAV password per user; decide after checking coverage.
- "Assigned by me, waiting on others" (ToDo `assigned_by = me`, `allocated_to != me`): cheap to add once the ToDo list exists.
- Real-time collaborative editing (#1534) and translations (#1457) follow their own issues.

## Open questions (answered 2026-10-14)

See "Status and decisions" at the top.

## Findings along the way

Filed as separate issues on 2026-10-14:

- #1545 `mailcow_integration/caldav/sync_todo.py` is not registered in `hooks.py`.
- #1546 `TimesheetPanel.vue` and its `timerApi` config key are dead since ac737c92.
- #1547 `scan_frontend` and `human_resources_frontend` both use dev port 8082.
- #1548 Raven deep links matched no frontend route (folded into the Raven re-introduction).
- Security: #1549 timer endpoints without ownership check, #1550 `allow_guest` endpoint in the project action panel, #1551 `update_customer_comment` without permission check, #1552 SQL built with f-strings in `get_graph_data`.

## Reuse map

Backend, usable as is: `i_own_my_work.get_inbox`, `create_issue`, `update_issue`,
`set_assignees`; `department_cockpit` serializers and all Task and Checklist writes;
`checklist_inbox.*`; `presence.*`; `link_preview.get_link_preview_lines`;
`issue_raven.*`; `project_management_spa._serialize_todo_row`;
`dev_action_panel.get_time_stats`, `get_active_session`, `get_my_timesheets`;
`spa_boot.get_spa_boot`.

Frontend, usable as is: `CockpitShell`, `CockpitSidebar`, `createSpaRouter`,
`IssuesInbox`, `IssueDetail`, `TasksInbox`, `TaskDetail`, `TaskGantt`,
`ChecklistsInbox`, `ChecklistsHome`, `ChecklistDetail`, `ChecklistEditor`,
`AssigneePicker`, `UserAvatar`, the filter components, `useAutosaveDoc`,
`useDocRealtime`, `useFieldLocks`, `deskUrl`, `appWindow`.

Frontend, patterns to copy: I Own My Work `Inbox.vue` tabs; PM
`ImplementationTodoList.vue` and `ImplementationTodoQuickAdd.vue`;
`PmImplementationsHub.vue` cards; `IssueKanban` and `IssueCalendar` as alternative
layouts for a later draft.
