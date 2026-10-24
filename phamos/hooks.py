from . import __version__ as app_version

app_name = "phamos"
app_title = "phamos GmbH"
app_publisher = "phamos.eu"
app_description = "ERPNext Enhancement for phamos.eu"
app_email = "support@phamos.eu"
app_license = "MIT"

required_apps = ["erpnext", "hrms"]

add_to_apps_screen = [
	{
		"name": "personal_cockpit",
		"logo": "/assets/phamos/manifest/personal-icon-192.png",
		"title": "Personal Cockpit",
		"route": "/personal-cockpit",
		"has_permission": "phamos.api.personal_cockpit.check_app_permission",
	},
	{
		"name": "human_resources_spa",
		"logo": "/assets/phamos/manifest/human-resources-icon-192.png",
		"title": "Human Resources",
		"route": "/human-resources-cockpit",
		"has_permission": "phamos.api.human_resources_spa.check_app_permission",
	},
	{
		"name": "sales_spa",
		"logo": "/assets/phamos/manifest/sales-icon-192.png",
		"title": "Sales",
		"route": "/sales-cockpit",
		"has_permission": "phamos.api.sales_spa.check_app_permission",
	},
	{
		"name": "project_management_spa",
		"logo": "/assets/phamos/manifest/project-management-icon-192.png",
		"title": "Project Management Cockpit",
		"route": "/project-management-cockpit",
		"has_permission": "phamos.api.project_management_spa.check_app_permission",
	},
	{
		"name": "accounting_spa",
		"logo": "/assets/phamos/manifest/accounting-icon-192.png",
		"title": "Accounting",
		"route": "/accounting-cockpit",
		"has_permission": "phamos.api.accounting_spa.check_app_permission",
	},
	{
		"name": "software_development_spa",
		"logo": "/assets/phamos/manifest/software-development-icon-192.png",
		"title": "Software Development",
		"route": "/software-development-cockpit",
		"has_permission": "phamos.api.software_development_spa.check_app_permission",
	},
	{
		"name": "scan",
		"logo": "/assets/phamos/manifest/scan-icon-192.png",
		"title": "Lead Scan",
		"route": "/scan",
		"has_permission": "phamos.api.scan.check_app_permission",
	},
]

# Includes in <head>
# ------------------

# include js, css files in header of desk.html
app_include_css = [
    "/assets/phamos/css/sales_order_kpi.css",
    "/assets/phamos/css/dark_mode_fix.css",
    "checklist_dialog.bundle.css",  # hashed, so a new version is not served from browser cache
]
# app_include_js = "/assets/phamos/js/phamos.js"

app_include_js = [
    "https://code.highcharts.com/highcharts.js",
    "/assets/phamos/js/have_a_great_day.js",
    "/assets/phamos/js/custom_crm_activities.js",
    "/assets/phamos/js/hybrid_meeting_composer.js",
    "/assets/phamos/js/team_daily_schedule.js",
    "/assets/phamos/js/frappe_list_bulk_edit_override.js",  # Fixes null-label crash in bulk edit
    "checklist_dialog.bundle.js",  # Linked Checklists dialog (hashed bundle, see above)
    "web_profile_form.bundle.js",  # Web Profile forms: missing-translation hint, preview link
]


# include js, css files in header of web template
# web_include_css = "/assets/phamos/css/phamos.css"
# web_include_js = "/assets/phamos/js/phamos.js"
# Web Profile pages (/de|en/people, ...); scoped to .wp-page / [data-wp-listing]. Bundled by
# `bench build` so the URLs carry a content hash and browsers never keep a stale copy.
web_include_css = ["web_profile.bundle.css"]
web_include_js = ["web_profile.bundle.js"]

# include custom scss in every website theme (without file extension ".scss")
# website_theme_scss = "phamos/public/scss/website"

# include js, css files in header of web form
# webform_include_js = {"doctype": "public/js/doctype.js"}
# webform_include_css = {"doctype": "public/css/doctype.css"}

# include js in page
page_js = {
	"gitlab-issue-dashboard": "gitlab_integration/page/gitlab_issue_dashboard/gitlab_issue_dashboard_drilldown.js",
}

# include js in doctype views
doctype_js = {
	"Leave Application": "public/js/leave_application.js",  # calendar status (milestone 68)
	"Project" : "public/js/project.js",
	"Issue" : "public/js/issue.js",
	"Sales Order": "public/js/sales_order.js",
	"Lead": "public/js/lead.js",
	"Job Applicant": "public/js/job_applicant.js",
	"Job Opening": "public/js/job_opening.js",
    "Timesheet":"public/js/timesheet.js",
    "Email Account": "public/js/mailcow_email_account.js",
    "Event": "public/js/event.js",
    "Appointment": "public/js/appointment.js",
    "Sales Invoice": "public/js/sales_invoice.js",
    "Customer": "public/js/customer.js",
    "Delivery Note": "public/js/delivery_note.js",

}

doctype_list_js = {
    "Event": "public/js/event_list.js",
    "Monthly Implementation Summary": "public/js/monthly_implementation_summary_list.js",
}

doctype_calendar_js = {
    "Employee Availability": "public/js/employee_availability_calendar.js",
}

override_doctype_class = {
	"Job Applicant": "phamos.events.job_applicant.CustomJobApplicant"
}

website_route_rules = [
    {"from_route": "/schedule_interview/<name>", "to_route": "schedule_interview"},
    {"from_route": "/personal-cockpit", "to_route": "personal_cockpit"},
    {"from_route": "/personal-cockpit/<path:app_path>", "to_route": "personal_cockpit"},
    {"from_route": "/human-resources-cockpit", "to_route": "human_resources_spa"},
    {"from_route": "/human-resources-cockpit/<path:app_path>", "to_route": "human_resources_spa"},
    {"from_route": "/sales-cockpit", "to_route": "sales_spa"},
    {"from_route": "/sales-cockpit/<path:app_path>", "to_route": "sales_spa"},
    {"from_route": "/project-management-cockpit", "to_route": "project_management_spa"},
    {"from_route": "/project-management-cockpit/<path:app_path>", "to_route": "project_management_spa"},
    {"from_route": "/accounting-cockpit", "to_route": "accounting_spa"},
    {"from_route": "/accounting-cockpit/<path:app_path>", "to_route": "accounting_spa"},
    {"from_route": "/software-development-cockpit", "to_route": "software_development_spa"},
    {"from_route": "/software-development-cockpit/<path:app_path>", "to_route": "software_development_spa"},
    {"from_route": "/scan", "to_route": "scan"},
    {"from_route": "/scan/<path:app_path>", "to_route": "scan"},
]

# Web Profile sections (phamos/phamos#1492): one listing + one profile page per section and
# language, served by www/web_profile/{listing,profile}. Keep in sync with web_profile/sections.py.
_WEB_PROFILE_SLUGS = {
    "people": {"en": "people", "de": "personen"},
    "departments": {"en": "departments", "de": "abteilungen"},
    "teams": {"en": "teams", "de": "teams"},
    "modules": {"en": "modules", "de": "module"},
    "implementations": {"en": "implementations", "de": "implementierungen"},
    "industries": {"en": "industries", "de": "branchen"},
    "customers": {"en": "customers", "de": "kunden"},
    "partners": {"en": "partners", "de": "partner"},
    "events": {"en": "events", "de": "veranstaltungen"},  # Marketing Content (phamos.web_profile.events)
}
for _section, _slugs in _WEB_PROFILE_SLUGS.items():
    for _lang, _slug in _slugs.items():
        website_route_rules += [
            {"from_route": f"/{_lang}/{_slug}", "to_route": "web_profile/listing",
             "defaults": {"section": _section, "lang": _lang}},
            {"from_route": f"/{_lang}/{_slug}/<slug>", "to_route": "web_profile/profile",
             "defaults": {"section": _section, "lang": _lang}},
        ]
# Landing page of the newsletter double opt-in (Email Group "welcome_url", Marketing Content).
SUBSCRIPTION_CONFIRMED_ROUTES = {"de": "de/anmeldung-bestaetigt", "en": "en/subscription-confirmed"}
for _lang, _route in SUBSCRIPTION_CONFIRMED_ROUTES.items():
    website_route_rules.append({"from_route": f"/{_route}", "to_route": "web_profile/subscribed",
        "defaults": {"section": "events", "lang": _lang}})
# Old URLs of the sections are redirected with Website Route Redirect records (Website Settings)
# when a section goes live, not in code (phamos/phamos#1492).

# The HR cockpit used to live at /hr-cockpit; keep old links (Raven messages, bookmarks) working.
# /hr_spa was its www page path; servers keep a stale built hr_spa.html there, which would
# otherwise render without boot data.
# I Own My Work (/i-own-my-work) was replaced by the Personal Cockpit (phamos/phamos#1456).
# Its only deep route was /issue/<name>; Raven messages linked /issues/<name>. The first
# matching rule wins, so the specific rule comes first. /i_own_my_work was its www page path.
website_redirects = [
    {"source": r"/hr-cockpit(/.*)?", "target": r"/human-resources-cockpit\1"},
    {"source": "/hr_spa", "target": "/human-resources-cockpit"},
    {"source": r"/i-own-my-work/issues?/(.+)", "target": r"/personal-cockpit/issues/list/\1"},
    {"source": r"/i-own-my-work(/.*)?", "target": r"/personal-cockpit\1"},
    {"source": "/i_own_my_work", "target": "/personal-cockpit"},
]


# doctype_list_js = {"doctype" : "public/js/doctype_list.js"}
# doctype_tree_js = {"doctype" : "public/js/doctype_tree.js"}
# doctype_calendar_js = {"doctype" : "public/js/doctype_calendar.js"}

# Home Pages
# ----------

# application home page (will override Website Settings)
# home_page = "login"

get_website_user_home_page = "phamos.website.get_website_user_home_page"

on_login = ["phamos.website.on_login"]

update_website_context = [
    "phamos.website.update_website_context",
    "phamos.web_profile.chrome.update_website_context",  # language-aware navbar/footer, DIN 5008 footer
]

# Generators
# ----------

# automatically create page for each record of this doctype
# website_generators = ["Web Page"]

# Jinja
# ----------

# add methods and filters to jinja environment
# jinja = {
#	"methods": "phamos.utils.jinja_methods",
#	"filters": "phamos.utils.jinja_filters"
# }

# Installation
# ------------

after_install = "phamos.setup.ops_inbox.ensure_ops_inbox_setup"

after_migrate = [
	"phamos.setup.ops_inbox.ensure_ops_inbox_setup",
	"phamos.web_profile.setup.after_migrate",  # Web Page "Language" / "Translation Of" fields
	"phamos.cockpits.setup.after_migrate",  # ToDo fields of the Personal Cockpit (#1553)
	"phamos.setup.accounting_receipt.ensure_accounting_receipt_setup",  # AI Accountant role, user, bot
	"phamos.marketing.setup.after_migrate",  # Lead Source "Event" for event registrations
]

# Uninstallation
# ------------

# before_uninstall = "phamos.install.before_uninstall"
# after_uninstall = "phamos.uninstall.after_uninstall"

# Desk Notifications
# ------------------
# See frappe.core.notifications.get_notification_config

# notification_config = "phamos.notifications.get_notification_config"

# Permissions
# -----------
# Permissions evaluated in scripted ways

# permission_query_conditions = {
#	"Event": "frappe.desk.doctype.event.event.get_permission_query_conditions",
# }
#
# has_permission = {
#	"Event": "frappe.desk.doctype.event.event.has_permission",
# }

# Personal Cockpit focus sessions are private, System Managers included (#1556).
permission_query_conditions = {
	"Focus Session": "phamos.cockpits.permissions.focus_session_query",
	"ToDo Challenge": "phamos.cockpits.permissions.todo_challenge_query",
	"Day Plan": "phamos.cockpits.permissions.day_plan_query",
}

has_permission = {
	"Focus Session": "phamos.cockpits.permissions.focus_session_has_permission",
	"ToDo Challenge": "phamos.cockpits.permissions.todo_challenge_has_permission",
	"Day Plan": "phamos.cockpits.permissions.day_plan_has_permission",
}

# DocType Class
# ---------------
# Override standard doctype classes

# override_doctype_class = {
#	"ToDo": "custom_app.overrides.CustomToDo"
# }

# Document Events
# ---------------
# Hook on document methods and events

# doc_events = {
#	"*": {
#		"on_update": "method",
#		"on_cancel": "method",
#		"on_trash": "method"
#	}
# }

# Raven opens its Issue links in the matching cockpit instead of Desk (#1614).
raven_document_link_override = "phamos.api.issue_chat.document_link"

doc_events = {
	# Personal Cockpit: closed-on stamp, reschedule count, per-user refresh (#1553).
	"ToDo": {
		"before_insert": "phamos.cockpits.todo_hooks.before_insert",
		"validate": "phamos.cockpits.todo_hooks.validate",
		"on_update": [
			"phamos.cockpits.todo_hooks.on_update",
			# New assignees of an Issue join its Raven chat (#1614).
			"phamos.api.issue_chat.sync_assignee",
			# Closing or rescheduling a checklist item's ToDo updates the item (#1625).
			"phamos.phamos.doctype.checklist.checklist_assignment.sync_item_from_todo",
		],
		"on_trash": [
			"phamos.cockpits.todo_hooks.on_trash",
			"phamos.phamos.doctype.checklist.checklist_assignment.clear_item_todo_link",
		],
	},
	# Personal Cockpit check-ins: live updates to the employee's own user (#1571). Never fires
	# on sites without HRMS, since the doctype does not exist there.
	"Employee Checkin": {
		"on_update": "phamos.cockpits.checkin_hooks.on_update",
		"on_trash": "phamos.cockpits.checkin_hooks.on_trash",
	},
	# Leave Applications as all-day events in the employee's own calendar (milestone 68, Phase 2).
	# Never fires on sites without HRMS. on_update also runs on insert and before on_submit.
	"Leave Application": {
		"on_update": "phamos.phamos.hr.leave_calendar.sync_leave_event",
		"on_submit": "phamos.phamos.hr.leave_calendar.sync_leave_event",
		"on_cancel": "phamos.phamos.hr.leave_calendar.sync_leave_event",
		"on_trash": "phamos.phamos.hr.leave_calendar.remove_leave_event",
	},
	"Event": {
		# on_update also runs after insert; an after_insert hook here pushed every new Event twice.
		"on_update": "phamos.mailcow_integration.caldav.sync_event.on_upsert",
		"on_trash": "phamos.mailcow_integration.caldav.sync_event.on_delete",
	},
    "Team": {
        "validate": "phamos.events.team_daily_schedule.validate_schedule_rows",
        "after_save": "phamos.phamos.doctype.team.team.create_team_capacity_ledger_entry",
        "after_insert": "phamos.events.team_daily_schedule.sync_events_from_parent",
        "on_update": [
            "phamos.events.team_daily_schedule.sync_events_from_parent",
            "phamos.web_profile.mirror.push_to_profiles",
        ],
        "on_trash": "phamos.events.team_daily_schedule.cleanup_events_on_parent_trash"
    },
    "Communication": {
        "on_update": "phamos.events.communication.copy_attachments_to_reference_doc"
    },
    "Lead Data": {
        "after_insert": "phamos.events.lead_data.notify_lead_data_created_via_raven_dm"
    },
	# Status changes and conversions show up in the Issue chat; Closed archives it (#1621, #1622).
	"Issue": {"on_update": "phamos.api.issue_chat.on_issue_update"},
	"Task": {"after_insert": "phamos.api.issue_chat.on_task_insert"},
    "Raven Message": {
		# Mentioned people join the Issue chat before Raven notifies them (#1620).
		"validate": "phamos.api.issue_chat.add_mentioned_members",
		"after_insert": "phamos.events.raven_bot.handle_lead_option_reply"
	},
    "Account": {"on_update": "phamos.accounting.expense_accounts.clear_account_cache"},
    "Purchase Invoice": {"on_submit": "phamos.accounting.library.learn_from_purchase_invoice"},
    "Accounting Receipt": {
        "after_insert": [
            "phamos.phamos.doctype.accounting_receipt.accounting_receipt.sync_attachment_from_files",
            "phamos.phamos.doctype.accounting_receipt.mistral_pdf.run_auto_extract_if_attachment",
        ]
    },
    "Delivery Note": {
        "on_submit": "phamos.phamos.doctype.monthly_implementation_summary.monthly_implementation_summary.update_mis_timesheets_on_delivery_note_submit",
        "on_update_after_submit": "phamos.phamos.doctype.monthly_implementation_summary.monthly_implementation_summary.sync_mis_status_for_source_doc",
        "on_cancel": "phamos.phamos.doctype.monthly_implementation_summary.monthly_implementation_summary.sync_mis_status_for_source_doc",
    },
    # Event tickets: Attendee links and payment status (phamos.marketing.billing). Only on_change: it runs
    # once after every save, submit and cancel, and payments reach an invoice through db_set, which runs
    # on_change too. Hooking on_submit etc. as well ran the handler twice (phamos/phamos#1706).
    "Sales Invoice": {
        "on_submit": "phamos.phamos.doctype.monthly_implementation_summary.monthly_implementation_summary.sync_mis_status_for_source_doc",
        "on_update_after_submit": "phamos.phamos.doctype.monthly_implementation_summary.monthly_implementation_summary.sync_mis_status_for_source_doc",
        "on_cancel": "phamos.phamos.doctype.monthly_implementation_summary.monthly_implementation_summary.sync_mis_status_for_source_doc",
        "on_change": "phamos.marketing.billing.on_sales_invoice_change",
        "on_trash": "phamos.marketing.billing.on_sales_invoice_trash",
    },
    "Sales Order": {
        "on_update": "phamos.marketing.billing.on_sales_order_update",
        "on_submit": ["phamos.phamos.doctype.monthly_implementation_summary.monthly_implementation_summary.sync_mis_status_for_source_doc", "phamos.marketing.billing.on_sales_order_submit"],
        "on_update_after_submit": "phamos.phamos.doctype.monthly_implementation_summary.monthly_implementation_summary.sync_mis_status_for_source_doc",
        "on_cancel": ["phamos.phamos.doctype.monthly_implementation_summary.monthly_implementation_summary.sync_mis_status_for_source_doc", "phamos.marketing.billing.on_sales_order_cancel"],
        "on_trash": "phamos.marketing.billing.on_sales_order_cancel",
    },
    "Payment Entry": {
        "on_submit": "phamos.marketing.billing.on_payment_entry_change",
        "on_cancel": "phamos.marketing.billing.on_payment_entry_change",
    },
    # Seats left and sale state are cached with the event items: refresh them when attendees change.
    "Attendee": {
        "after_insert": "phamos.web_profile.sections.clear_events",
        "on_update": "phamos.web_profile.sections.clear_events",
        "on_trash": "phamos.web_profile.sections.clear_events",
    },
    "Lead": {
        "before_insert": "phamos.marketing.billing.lead_before_insert",
    },
    "Customer": {
        "on_update": [
            "phamos.gitlab_integration.gitlab_group_utils.update_gitlab_avatar_on_customer",
            "phamos.web_profile.mirror.push_to_profiles",
        ]
    },
    "Implementation": {
        "on_update": [
            "phamos.phamos.doctype.timesheet_record.timesheet_record.sync_implementation_time_limit_summary_on_save",
            "phamos.web_profile.mirror.push_to_profiles",
        ],
    },
    # Mirror facts onto the Web Profiles (phamos/phamos#1492).
    "Employee": {
        "on_update": [
            "phamos.web_profile.mirror.push_to_profiles",
            # Employment Contract: a leaver's open contract ends on the relieving date (#1596)
            "phamos.phamos.doctype.employment_contract.employment_contract.cap_contracts_at_relieving_date",
        ]
    },
    "Contact": {"on_update": "phamos.web_profile.mirror.push_to_profiles"},
    "Supplier": {"on_update": "phamos.web_profile.mirror.push_to_profiles"},
    "Sales Partner": {"on_update": "phamos.web_profile.mirror.push_to_profiles"},
    "Workspace": {"on_update": "phamos.web_profile.mirror.push_to_profiles"},
    "Department": {"on_update": "phamos.web_profile.mirror.push_to_profiles"},
    "Implementation Module": {"on_update": "phamos.web_profile.mirror.push_to_profiles"},
    "Interview Feedback": {
        "on_update": "phamos.phamos.hr.interview_summary.trigger_interview_summary",
        "on_submit": "phamos.phamos.hr.interview_summary.trigger_interview_summary",
        "on_cancel": "phamos.phamos.hr.interview_summary.trigger_interview_summary",
    },
    "GitLab Issue": {
        "on_trash": "phamos.gitlab_integration.label_ledger.delete_issue_label_ledger",
    },
    "Timesheet Record": {
        # Personal Cockpit timer: live updates to the employee's own user (#1572).
        "on_change": "phamos.cockpits.timer_hooks.on_change",
        "on_trash": "phamos.cockpits.timer_hooks.on_trash",
        "on_submit": [
            "phamos.gitlab_integration.gitlab_utils.sync_touch_time_on_timesheet_change",
            "phamos.gitlab_integration.gitlab_utils.sync_cycle_time_start_on_timesheet_change",
        ],
        "on_cancel": [
            "phamos.gitlab_integration.gitlab_utils.sync_touch_time_on_timesheet_change",
            "phamos.gitlab_integration.gitlab_utils.sync_cycle_time_start_on_timesheet_change",
        ],
    },
}


# Scheduled Tasks
# ---------------
# In your_app/hooks.py

# your_app/hooks.py

fixtures = [
    {"dt": "Role", "filters": [
        [
            "name", "in", [
                "Bookstack User",
                "Bookstack Manager",
            ]
        ]
    ]},
    {"dt": "Scheduled Job Type", "filters": [
        [
            "name", "in", [
                "mattermost_daily_thread.create_mattermost_thread",
                "raven_daily_thread.create_raven_thread",
            ]
        ]
    ]},
    {"dt": "Custom Field", "filters": [
        [
            "module", "=", "Phamos"
        ]
    ]},
    {"dt": "Property Setter", "filters": [
        [
            "module", "=", "Phamos"
        ]
    ]},
    {"dt": "Email Template", "filters": [
        [
            "name", "in", ["Interview Confirmation", "Event Subscription Confirmation"]
        ]
    ]}
]

scheduler_events = {
    "daily": [
        "phamos.api.send_daily_timesheet_comment_summary",
        "phamos.phamos.doctype.team.team.update_all_teams_weekly_holidays",
        # MIS: on 1st only — previous calendar month; see create_monthly_implementation_summaries docstring
        "phamos.phamos.doctype.monthly_implementation_summary.create_monthly_implementation_summaries.create_monthly_implementation_summaries",
        "phamos.api.send_daily_birthday_wishes",
        "phamos.bookstack_integration.sync.sync_all_instances",
        # MIS: auto-close open summaries once every linked SO/DN is fully delivered and billed
        "phamos.phamos.doctype.monthly_implementation_summary.monthly_implementation_summary.auto_close_fulfilled_mis",
        # Personal Cockpit: settle yesterday in running ToDo challenges (#1557)
        "phamos.api.personal_challenges.evaluate_all_challenges",
        # Event tickets: payment status for payments booked without hooks
        "phamos.marketing.billing.sync_payment_status",
        # Employment Contract: Upcoming -> Active -> Expired as dates pass (#1596)
        "phamos.phamos.doctype.employment_contract.employment_contract.update_contract_statuses",
    ],
    "weekly": [
        # Personal Cockpit: checklists left behind by ToDos deleted without hooks (#1554)
        "phamos.cockpits.maintenance.cleanup_orphan_todo_checklists",
    ],
    "monthly": [
        "phamos.api.send_monthly_comment_summary"
    ],
    "cron": {
        # Weekly customer report — every Monday at 07:00 server time.
        "0 7 * * 1": [
            "phamos.gitlab_integration.generate_weekly_report.send_weekly_reports_for_all_implementations",
        ],
        # Keep GitLab projects/milestones/issues fresh, including already synced issues.
        "30 */2 * * *": [
            "phamos.gitlab_integration.gitlab_utils.sync_gitlab_data_background",
        ],
        # Personal Cockpit: end focus sessions that ran past their limit (#1556).
        "*/5 * * * *": [
            "phamos.api.personal_focus.expire_focus_sessions",
        ],
        # Personal Cockpit: fix today's day plans that were never started (#1559).
        "0 10 * * *": [
            "phamos.api.personal_day_plan.freeze_day_plans",
        ],
    },
}


# Testing
# -------

before_tests = "phamos.install.before_tests"

# Overriding Methods
# ------------------------------
#
# override_whitelisted_methods = {
#	"frappe.desk.doctype.event.event.get_events": "phamos.event.get_events"
# }
#
# each overriding function accepts a `data` argument;
# generated from the base implementation of the doctype dashboard,
# along with any modifications made in other Frappe apps
# override_doctype_dashboards = {
#	"Task": "phamos.task.get_dashboard_data"
# }

override_doctype_dashboards = {
    "Project": "phamos.custom_scripts.custom_python.project_dashboard.get_project_dashboard_data",
    "Delivery Note": "phamos.custom_scripts.custom_python.delivery_note_dashboard.get_delivery_note_dashboard_data",
    "Employee": "phamos.custom_scripts.custom_python.employee_dashboard.get_employee_dashboard_data",
}

# exempt linked doctypes from being automatically cancelled
#
# auto_cancel_exempted_doctypes = ["Auto Repeat"]

# Ignore links to specified DocTypes when deleting documents
# -----------------------------------------------------------

# ignore_links_on_delete = ["Communication", "ToDo"]

# Request Events
# ----------------
# before_request = ["phamos.utils.before_request"]
# after_request = ["phamos.utils.after_request"]

# Job Events
# ----------
# before_job = ["phamos.utils.before_job"]
# after_job = ["phamos.utils.after_job"]

# User Data Protection
# --------------------

# user_data_fields = [
#	{
#		"doctype": "{doctype_1}",
#		"filter_by": "{filter_by}",
#		"redact_fields": ["{field_1}", "{field_2}"],
#		"partial": 1,
#	},
#	{
#		"doctype": "{doctype_2}",
#		"filter_by": "{filter_by}",
#		"partial": 1,
#	},
#	{
#		"doctype": "{doctype_3}",
#		"strict": False,
#	},
#	{
#		"doctype": "{doctype_4}"
#	}
# ]

# Personal Cockpit focus sessions belong to their user: exported and deleted with the user's data.
user_data_fields = [
	{"doctype": "Focus Session", "filter_by": "user", "redact_fields": ["break_out_reason"]},
	{"doctype": "ToDo Challenge", "filter_by": "user", "redact_fields": ["title"]},
	{"doctype": "Day Plan", "filter_by": "user", "redact_fields": ["reflection"]},
	# Event attendees are matched by their email address (they have no user account).
	{"doctype": "Attendee", "filter_by": "email", "redact_fields": ["first_name", "last_name", "full_name",
		"phone", "company_name", "job_title", "notes", "follow_up_notes"]},
]

# Authentication and authorization
# --------------------------------

# auth_hooks = [
#	"phamos.auth.validate"
# ]
