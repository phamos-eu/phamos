// Copyright (c) 2025, phamos.eu and contributors
// For license information, please see license.txt

/*frappe.ui.form.on("Implementation", {
	setup:function(frm){
		console.log('**')
		if(!frm.is_new()){
			frappe.call({
				method: "phamos.phamos.doctype.implementation.implementation.get_financial_history",
				args: {'name':frm.doc.name},
				callback: function (r) {
					console.log('************')
				},
			});
		}
	}*/
	/*after_save:function(frm){
		add_row_to_child_table(frm)
	},*/
/*});*/
/*
function add_row_to_child_table(frm) {
    let row = frm.add_child('status_information'); // 'items' is the child table fieldname
    row.maturity_level = frm.doc.maturity_level;
    row.mood = frm.doc.mood;
    row.forecast = frm.doc.forecast;
    row.status = frm.doc.status;
    row.time = frappe.datetime.now_datetime();
    frm.refresh_field('status_information'); // Refresh child table UI
}*/
