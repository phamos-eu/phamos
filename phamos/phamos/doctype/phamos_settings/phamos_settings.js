// Copyright (c) 2023, phamos.eu and contributors
// For license information, please see license.txt

frappe.ui.form.on('phamos Settings', {
	// refresh: function(frm) {

	// }

});
frappe.ui.form.on('phamos Settings', {
    validate: function(frm) {
        // Filter out the enabled channels
        let enabled_channels = frm.doc.mattermost_channel.filter(channel => channel.enable);

        // Check if more than one channel is enabled
        if (enabled_channels.length > 1) {
            frappe.msgprint(__('Only one Mattermost Channel can be enabled at a time.'));
            // Prevent the form from being saved
            frappe.validated = false;
        }
    }
});
