// Copyright (c) 2025, phamos.eu and contributors
// For license information, please see license.txt

frappe.ui.form.on("Recruitment Settings", {
	onload: function(frm) {
		frm.fields_dict.job_opening_configs.grid.get_field('job_opening').get_query = function() {
			return {
				filters: {
					'status': 'Open'
				}
			};
		};
	}
});
