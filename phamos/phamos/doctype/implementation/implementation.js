// Copyright (c) 2025, phamos.eu and contributors
// For license information, please see license.txt
/*
frappe.ui.form.on("Implementation", {
	setup:function(frm){
		if(!frm.is_new()){
			add_row_to_sales_order(frm)
			frappe.call({
				method: "phamos.phamos.doctype.implementation.implementation.get_financial_history",
				args: {'name':frm.doc.name},
				callback: function (r) {
					if(r.message){
						frm.set_value('sales_order_total_hrs', r.message['sales_order_qty'])
						frm.set_value('delivered_total_hrs', r.message['dn_qty'])
						frm.set_value('total_hrs_timesheet', r.message['timesheet_hrs'])
						frm.set_value('remaining_hrs',r.message['remaining_hrs'])
						if(r.message['open_so'] == 1){
							frm.set_value('open_so', 'Yes')
						}
						else{
							frm.set_value('open_so', 'No')
						}
						frm.save()
					}
				},
			});
		}
	}, 
});
*/

