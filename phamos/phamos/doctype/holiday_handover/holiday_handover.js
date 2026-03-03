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
}
});

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
