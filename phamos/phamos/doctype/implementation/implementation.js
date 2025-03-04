// Copyright (c) 2025, phamos.eu and contributors
// For license information, please see license.txt

frappe.ui.form.on("Implementation", {
	setup:function(frm) {
		console.log('****************')
	},
	after_save:function(frm){
		add_row_to_child_table(frm)
	},
});

function add_row_to_child_table(frm) {
	console.log('cccccccccccccc')
    let row = frm.add_child('status_information'); // 'items' is the child table fieldname
    row.maturity_level = frm.doc.maturity_level;
    row.mood = frm.doc.mood;
    row.forecast = frm.doc.forecast;
    row.time = frappe.datetime.now_datetime();
    frm.refresh_field('status_information'); // Refresh child table UI
}
