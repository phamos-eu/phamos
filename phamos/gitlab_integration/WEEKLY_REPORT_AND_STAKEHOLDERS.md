# Stakeholder Management & Weekly Customer Report — Implementation Notes

This documents the Stakeholder Management tab and the GitLab-based weekly
customer report feature on the **Implementation** doctype: what exists, what
was added/fixed, and how to test each part.

## 1. Stakeholder Management

**Files:**
- `phamos/phamos/doctype/implementation/implementation.json`
- `phamos/phamos/doctype/implementation_stakeholder/implementation_stakeholder.json`

The "Stakeholders" tab on Implementation was renamed to **"Stakeholder
Management"**. The `Implementation Stakeholder` child table (field
`stakeholders`) holds:

| Field | Type | Notes |
|---|---|---|
| `contact` | Link (Contact) | Used for both customer and internal stakeholders |
| `full_name` | Data | Fetched from `contact.full_name` |
| `email` | Data | Fetched from `contact.email_id`, required |
| `stakeholder_organisation` | Select | Internal / Customer / Third Party |
| `stakeholder_type` | Select | Project Manager / Team Member / Sponsor / Supplier / End User (extend later as needed) |
| `stakeholder_position` | Data | Free-text position/title |
| `receive_timesheet_report` | Check | Existing — opts into the daily/weekly timesheet email |
| `receive_weekly_customer_report` | Check | Existing — opts into the GitLab-based weekly report below |
| `comments` | Small Text | Free-text notes |

### Test
1. Open any Implementation → **Stakeholder Management** tab.
2. Add a row, confirm all fields above appear with correct Select options.
3. Save, reload the doc, confirm values persisted.

## 2. Weekly Customer Report (GitLab-based)

Generates a per-Implementation weekly email summarizing what was deployed to
production (from GitLab Issues + their comments) and total timesheet hours,
using Mistral to write the summary from a configurable prompt.

### Pre-existing pieces (already in the codebase before this work)

- **`Customer Weekly Report Settings`** doctype — the AI prompt, settable
  per-Implementation or as a global default (`is_default` + `enabled`).
- **`phamos/gitlab_integration/generate_weekly_report.py`** — core pipeline:
  `get_deployed_issues()` (GitLab Issues with `merged_to_production_at` /
  `testing_on_production_at` in range), `get_timesheet_breakdown()`,
  `_call_mistral()`, `generate_and_send_weekly_report()` (orchestrates +
  emails stakeholders with `receive_weekly_customer_report` checked).

### Added / fixed in this round

| Change | File | Why |
|---|---|---|
| `weekly_report_mistral_model` field | `phamos/phamos/doctype/phamos_settings/phamos_settings.json` | The report previously reused `mistral_model`, which is set to an OCR-only model for receipt processing (`accounting_receipt/mistral_pdf.py`) — every report call 400'd. Now decoupled, defaults to `mistral-small-latest`. |
| `GitLab Issue Comment` child doctype (new) | `phamos/gitlab_integration/doctype/gitlab_issue_comment/` | Stores `note_id` (unique), `author`, `commented_at`, `comment`. Attached as `comments` table field on `GitLab Issue`. |
| `Note Hook` webhook handling | `phamos/gitlab_integration/gitlab_utils.py` — `_handle_note_webhook`, `_upsert_issue_comment` | The webhook receiver previously only processed `Issue Hook` events and silently dropped everything else. Now also handles `Note Hook`, filtered to `noteable_type == "Issue"` and skipping GitLab's system-generated notes (label/assignee changes) so only real discussion is stored. Idempotent on `note_id`. |
| `backfill_issue_comments(project_name=None)` | same file | One-off historical sync via `/issues/:iid/notes`, for issues that existed before the webhook was registered. |
| `note_events` in webhook registration | `register_webhooks_for_all_projects()`, same file | Now requests `note_events`. Also detects already-registered hooks and `PUT`s to enable `note_events` on them instead of skipping ("already registered"), so existing production webhooks get upgraded rather than needing full re-registration. |
| Comments feed into the prompt | `generate_weekly_report.py` — `get_deployed_issues()`, `_format_issues_for_prompt()` | Each deployed ticket's non-system comments are attached and included in the text sent to Mistral. |
| `send_weekly_reports_for_all_implementations()` | `generate_weekly_report.py` | Bulk runner: every Implementation with at least one stakeholder opted into "Weekly Report"; failures are isolated per-implementation (logged, doesn't block the rest). |
| Scheduler cron | `phamos/hooks.py` | `"cron": {"0 7 * * 1": [...]}` — every Monday 07:00 server time, calling the bulk runner above. Uses `cron` rather than Frappe's generic `weekly` hook because the latter doesn't guarantee a specific day. |
| Two admin buttons | `phamos/gitlab_integration/doctype/gitlab_settings/gitlab_settings.js` | Added to the existing `add_custom_button` group pattern on GitLab Settings: **"Backfill Issue Comments"** and **"Send Weekly Reports Now (Test)"**. |
| Default report settings record | data only | Created a real `Customer Weekly Report Settings` doc named "Default Weekly Customer Report" (`is_default=1`, `enabled=1`) so the cron has something to use out of the box — review/edit its prompt text. |

### Test — full checklist

1. **`bench migrate`** — required for the new `GitLab Issue Comment`
   doctype and the `weekly_report_mistral_model` field.
2. **GitLab Settings**: set `Webhook Base URL` (public URL of the server
   receiving webhooks) and `Webhook Secret`, then click **"Set Webhooks"**
   (registers `note_events`, or upgrades an already-registered hook).
3. Post a comment on a real GitLab issue in a synced project → check that
   issue's `GitLab Issue` doc → **Comments** table populates. Confirms the
   live webhook path.
4. Click **"Backfill Issue Comments"** → check older/pre-existing issues'
   Comments tables populate too. Confirms the historical-pull path.
5. Ensure at least one Implementation has a linked `GitLab Project` (none do
   on the original dev DB this was built against — check first) and a
   Stakeholder row with `receive_weekly_customer_report` checked and a real
   email.
6. Click **"Send Weekly Reports Now (Test)"** on GitLab Settings → check the
   Sent/Failed list in the result dialog, and check `Email Queue` /
   the recipient's inbox for delivery status.
7. **phamos Settings → Data Extract tab**: confirm `Weekly Report Model` is a
   separate field from `Model`, set to a real chat-completions model (e.g.
   `mistral-small-latest`, not an OCR model).
8. To test the Monday cron without waiting a week:
   `bench execute phamos.gitlab_integration.generate_weekly_report.send_weekly_reports_for_all_implementations`

### Known limitations (inherent to GitLab's webhook API, not bugs here)

- GitLab does not fire a webhook when a comment is **deleted** — a
  synced comment will remain in ERPNext even if removed on GitLab.
- Comments only attach to issues that already exist as a `GitLab Issue`
  record. The periodic issue sync (`sync_all_issues` /
  `sync_issues_for_project`) only pulls issues that have an **assignee** —
  a comment webhook for an unassigned, never-synced issue will silently
  no-op.

### Deferred (not built)

- Merge Requests / GitHub PRs as a report source — explicitly out of scope
  for now; sticking with GitLab Issues (+ labels driving the "deployed to
  PROD" detection) + comments.
- A permanent default outgoing Email Account — needed before the Monday
  cron can actually deliver mail (a personal SMTP account was used only for
  a one-off manual test, not left as the default).
