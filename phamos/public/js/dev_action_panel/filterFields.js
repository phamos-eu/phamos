// The Filter button's field list (FrappeFilter.vue). Kept free of DOM/Vue imports so it is
// unit-tested with vitest (filterFields.test.js).

// The fields the server lets the panel filter on: FILTERABLE_FIELDS in dev_action_panel.py
// (the fields the panel already shows). Keep both lists in sync.
export const FILTERABLE_FIELDS = {
	"GitLab Issue": [
		"name", "issue_id", "title", "state", "due_date", "start_date",
		"assignee", "assignee_email", "gitlab_username",
		"issue_url", "parent_issue", "gitlab_project", "labels",
		"gitlab_parent_issue", "gitlab_child_issue",
	],
	Project: ["name", "project_name", "status", "percent_billable", "customer"],
}

// Filter-only fields, named like the Timesheet list's GitLab Parent / Child Issue (#1896). They
// are not columns of GitLab Issue; the server works them out from parent_issue
// (ISSUE_FAMILY_FIELDS in dev_action_panel.py): "GitLab Parent Issue = #X" shows #X and its
// child issues, "GitLab Child Issue is set" shows child issues only.
export const VIRTUAL_FIELDS = {
	"GitLab Issue": {
		gitlab_parent_issue: { label: "GitLab Parent Issue", fieldtype: "Link", options: "GitLab Issue" },
		gitlab_child_issue: { label: "GitLab Child Issue", fieldtype: "Link", options: "GitLab Issue" },
	},
}

// Docfields for the field dropdown, so it offers only FILTERABLE_FIELDS (and also works for
// users without read permission on the doctype, for whom Frappe would list no fields).
export function filterFields(doctype, getDocfield) {
	const virtual = VIRTUAL_FIELDS[doctype] || {}
	return (FILTERABLE_FIELDS[doctype] || [])
		.map((fieldname) => {
			if (fieldname === "name") {
				return { fieldname: "name", label: "ID", fieldtype: "Link", options: doctype, parent: doctype }
			}
			if (virtual[fieldname]) return { fieldname, ...virtual[fieldname], parent: doctype }
			return getDocfield(doctype, fieldname)
		})
		.filter(Boolean)
}

// FilterGroup has no option for the field list, but each frappe.ui.Filter it creates takes
// filter_fields (passed on to its FieldSelect). In Frappe v15 every row (the first one,
// "+ Add a Filter", rows re-added from saved filters) is created by FilterGroup._push_new_filter
// with `new frappe.ui.Filter(args)`, so this wraps that method and swaps frappe.ui.Filter for
// the duration of the call only.
//
// Returns false, with a console warning, when that Frappe internal is not there any more (e.g.
// after an upgrade): the dropdown then shows Frappe's usual field list, and the server still
// refuses fields outside FILTERABLE_FIELDS.
export function restrictFilterFields(filterGroup, fields, ui, warn = console.warn) {
	if (typeof filterGroup?._push_new_filter !== "function" || typeof ui?.Filter !== "function") {
		warn("Developer Action Panel: cannot limit the Filter fields (Frappe's FilterGroup changed).")
		return false
	}
	const pushNewFilter = filterGroup._push_new_filter
	filterGroup._push_new_filter = function (...args) {
		const Filter = ui.Filter
		ui.Filter = class extends Filter {
			constructor(opts) {
				super({ ...opts, filter_fields: fields })
			}
		}
		try {
			return pushNewFilter.apply(this, args)
		} finally {
			ui.Filter = Filter
		}
	}
	return true
}
