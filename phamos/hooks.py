from . import __version__ as app_version

app_name = "phamos"
app_title = "phamos GmbH"
app_publisher = "phamos.eu"
app_description = "ERPNext Enhancement for phamos.eu"
app_email = "support@phamos.eu"
app_license = "MIT"

required_apps = ["erpnext", "hrms"]
# Includes in <head>
# ------------------

# include js, css files in header of desk.html
app_include_css = [
    "/assets/phamos/css/sales_order_kpi.css",
    "/assets/phamos/css/dark_mode_fix.css"
]
# app_include_js = "/assets/phamos/js/phamos.js"

app_include_js = [
    "https://code.highcharts.com/highcharts.js",
    "/assets/phamos/js/have_a_great_day.js",
    "/assets/phamos/js/custom_crm_activities.js",
    "/assets/phamos/js/hybrid_meeting_composer.js",
    "/assets/phamos/js/team_daily_schedule.js",
    "/assets/phamos/js/frappe_list_bulk_edit_override.js",  # Fixes null-label crash in bulk edit
    "/assets/phamos/js/checklist_dialog.js",
]


# include js, css files in header of web template
# web_include_css = "/assets/phamos/css/phamos.css"
# web_include_js = "/assets/phamos/js/phamos.js"

# include custom scss in every website theme (without file extension ".scss")
# website_theme_scss = "phamos/public/scss/website"

# include js, css files in header of web form
# webform_include_js = {"doctype": "public/js/doctype.js"}
# webform_include_css = {"doctype": "public/css/doctype.css"}

# include js in page
# page_js = {"page" : "public/js/file.js"}

# include js in doctype views
doctype_js = {
	"Project" : "public/js/project.js",
	"Issue" : "public/js/issue.js",
	"Sales Order": "public/js/sales_order.js",
	"Lead": "public/js/lead.js",
	"Job Applicant": "public/js/job_applicant.js",
	"Job Opening": "public/js/job_opening.js",
    "Timesheet":"public/js/timesheet.js",
    "Email Account": "public/js/mailcow_email_account.js",
    "Event": "public/js/event.js",
    "Sales Invoice": "public/js/sales_invoice.js",
    "Customer": "public/js/customer.js",

}

doctype_list_js = {
    "Event": "public/js/event_list.js",
}

override_doctype_class = {
	"Job Applicant": "phamos.events.job_applicant.CustomJobApplicant"
}

website_route_rules = [
    {"from_route": "/schedule_interview/<name>", "to_route": "schedule_interview"}
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

update_website_context = ["phamos.website.update_website_context"]

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

# after_migrate = "phamos.install.after_migrate"

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

doc_events = {
	"Event": {
		"after_insert": "phamos.mailcow_integration.caldav.sync_event.on_upsert",
        "on_update": "phamos.mailcow_integration.caldav.sync_event.on_upsert",
		"on_trash": "phamos.mailcow_integration.caldav.sync_event.on_delete",
	},
    "Team": {
        "validate": "phamos.events.team_daily_schedule.validate_schedule_rows",
        "after_save": "phamos.phamos.doctype.team.team.create_team_capacity_ledger_entry",
        "after_insert": "phamos.events.team_daily_schedule.sync_events_from_parent",
        "on_update": "phamos.events.team_daily_schedule.sync_events_from_parent",
        "on_trash": "phamos.events.team_daily_schedule.cleanup_events_on_parent_trash"
    },
    "Communication": {
        "on_update": "phamos.events.communication.copy_attachments_to_reference_doc"
    },
    "Lead Data": {
        "after_insert": "phamos.events.lead_data.notify_lead_data_created_via_raven_dm"
    },
    "Raven Message": {
		"after_insert": "phamos.events.raven_bot.handle_lead_option_reply"
	},
    "Accounting Receipt": {
        "after_insert": [
            "phamos.phamos.doctype.accounting_receipt.accounting_receipt.sync_attachment_from_files",
            "phamos.phamos.doctype.accounting_receipt.mistral_pdf.run_auto_extract_if_attachment",
        ]
    },
    "Delivery Note": {
        "on_submit": "phamos.phamos.doctype.monthly_implementation_summary.monthly_implementation_summary.update_mis_timesheets_on_delivery_note_submit",
    },
    "Customer": {
        "on_update": "phamos.gitlab_integration.gitlab_group_utils.update_gitlab_avatar_on_customer"
    },
    "Interview Feedback": {
        "on_update": "phamos.phamos.hr.interview_summary.trigger_interview_summary",
        "on_submit": "phamos.phamos.hr.interview_summary.trigger_interview_summary",
        "on_cancel": "phamos.phamos.hr.interview_summary.trigger_interview_summary",
    },
}


# Scheduled Tasks
# ---------------
# In your_app/hooks.py

# your_app/hooks.py

fixtures = [
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
            "name", "in", ["Interview Confirmation"]
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
    },
}


# Testing
# -------

# before_tests = "phamos.install.before_tests"

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
    "Project": "phamos.custom_scripts.custom_python.project_dashboard.get_project_dashboard_data"
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

# Authentication and authorization
# --------------------------------

# auth_hooks = [
#	"phamos.auth.validate"
# ]
