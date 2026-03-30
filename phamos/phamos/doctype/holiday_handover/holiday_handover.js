// Copyright (c) 2026, phamos.eu and contributors
// For license information, please see license.txt

frappe.ui.form.on('Holiday Handover', {
	refresh: function(frm) {
		// Add custom button to fetch GitLab issues
		if (!frm.is_new()) {
			frm.add_custom_button(__('Fetch GitLab Issues'), function() {
				fetch_gitlab_issues(frm);
			});
		}

		// Inject clickable links into issue_title cells.
		// MutationObserver re-injects after any row expand/collapse/re-render.
		let grid = frm.fields_dict['issues'].grid;
		if (!grid._issue_links_hooked) {
			grid._issue_links_hooked = true;
			let observer = new MutationObserver(function() {
				inject_issue_title_links(frm);
			});
			observer.observe(grid.wrapper[0], { childList: true, subtree: true });
			grid._issue_observer = observer;
		}
		inject_issue_title_links(frm);
	},

	setup: function(frm) {
		// Set query for GitLab Issue in child table to filter by selected GitLab Project
		frm.set_query('gitlab_issue_id', 'issues', function(doc) {
			if (!doc.gitlab_project) {
				frappe.msgprint(__('Please select a GitLab Project first'));
				return { filters: { 'name': '' } }; // Return empty filter
			}
			return {
				filters: {
					'gitlab_project': doc.gitlab_project
				}
			};
		});
		
		// Set query for Acting Project Manager to exclude the current Project Manager
		frm.set_query('acting_project_manager', function(doc) {
			let filters = {};
			if (doc.project_manager) {
				filters = {
					'name': ['!=', doc.project_manager]
				};
			}
			return { filters: filters };
		});
	},

	implementation: function(frm) {
		// Store GitLab URL when Implementation is selected
		if (frm.doc.implementation) {
			frappe.call({
				method: 'frappe.client.get_list',
				args: {
					doctype: 'Project',
					filters: {
						custom_implementation: frm.doc.implementation
					},
					fields: ['custom_gitlab_project_url'],
					limit: 1
				},
				callback: function(r) {
					if (r.message && r.message.length > 0) {
						frm.gitlab_project_url = r.message[0].custom_gitlab_project_url;
					}
				}
			});
		}
	},
	
	gitlab_project: function(frm) {
		// Clear child table when GitLab Project changes
		if (frm.doc.issues && frm.doc.issues.length > 0) {
			frappe.confirm(
				__('Changing the GitLab Project will clear all selected issues. Do you want to continue?'),
				function() {
					// Clear the child table
					frm.clear_table('issues');
					frm.refresh_field('issues');
				},
				function() {
					// Revert the change
					frm.reload_doc();
				}
			);
		}
	}
});

// Child table event handler for auto-fill
frappe.ui.form.on('Holiday Handover Issue', {
	gitlab_issue_id: function(frm, cdt, cdn) {
		let row = locals[cdt][cdn];
		
		if (row.gitlab_issue_id) {
			// Fetch GitLab Issue data
			frappe.call({
				method: 'frappe.client.get',
				args: {
					doctype: 'GitLab Issue',
					name: row.gitlab_issue_id
				},
				callback: function(r) {
					if (r.message) {
						let gitlab_issue = r.message;
						
						// Auto-fill the fields from GitLab Issue
						frappe.model.set_value(cdt, cdn, 'issue_title', gitlab_issue.title || '');
						frappe.model.set_value(cdt, cdn, 'issue_status', gitlab_issue.state || '');
						frappe.model.set_value(cdt, cdn, 'assigned_to', gitlab_issue.assignee || '');
						frappe.model.set_value(cdt, cdn, 'due_date', gitlab_issue.due_date || '');
						frappe.model.set_value(cdt, cdn, 'description', gitlab_issue.description || '');
						frappe.model.set_value(cdt, cdn, 'issue_url', gitlab_issue.issue_url || '');
						frappe.model.set_value(cdt, cdn, 'parent_issue', gitlab_issue.parent_issue || '');
						frappe.model.set_value(cdt, cdn, 'gitlab_project', gitlab_issue.gitlab_project || '');
						
						frm.refresh_field('issues');
					}
				}
			});
		}
	}
});


function inject_issue_title_links(frm) {
	let grid = frm.fields_dict['issues'].grid;
	let issues = frm.doc.issues || [];

	// Disconnect observer during DOM mutation to avoid infinite loop
	if (grid._issue_observer) grid._issue_observer.disconnect();

	grid.wrapper.find('.grid-row[data-idx]').each(function() {
		let idx = parseInt($(this).attr('data-idx'));
		let row = issues.find(r => r.idx === idx);
		let $cell = $(this).find('[data-fieldname="issue_title"] .static-area');
		if (!row || !row.issue_url || !$cell.length || $cell.find('a').length) return;

		let title = $cell.text().trim();
		if (!title) return;

		$cell.html(
			'<a href="' + frappe.utils.escape_html(row.issue_url) + '"'
			+ ' target="_blank" rel="noopener">'
			+ frappe.utils.escape_html(title)
			+ '</a>'
		).find('a').on('click', function(e) {
			e.stopPropagation();
		});
	});

	// Reconnect observer
	if (grid._issue_observer) {
		grid._issue_observer.observe(grid.wrapper[0], { childList: true, subtree: true });
	}
}


function fetch_gitlab_issues(frm) {
if (!frm.doc.implementation) {
frappe.msgprint(__('Please select an Implementation first'));
return;
}

// Get GitLab Project URL from Implementation's Projects
frappe.call({
method: 'frappe.client.get_list',
args: {
doctype: 'Project',
filters: {
custom_implementation: frm.doc.implementation
},
fields: ['custom_gitlab_project_url'],
limit: 1
},
callback: function(r) {
if (r.message && r.message.length > 0 && r.message[0].custom_gitlab_project_url) {
let gitlab_url = r.message[0].custom_gitlab_project_url;

// Show dialog for GitLab integration
let d = new frappe.ui.Dialog({
title: __('Fetch GitLab Issues'),
fields: [
{
label: __('GitLab Project URL'),
fieldname: 'gitlab_url',
fieldtype: 'Data',
default: gitlab_url,
description: __('GitLab project URL')
},
{
label: __('Note'),
fieldname: 'note',
fieldtype: 'HTML',
options: '<p class="text-muted">' + 
__('GitLab API integration can be configured to auto-fetch issues. ') +
__('For now, you can manually add issues in the table below.') +
'</p>'
}
],
primary_action_label: __('Close'),
primary_action(values) {
d.hide();
}
});

d.show();
} else {
frappe.msgprint(__('No GitLab Project URL found for this Implementation'));
}
}
});
}
