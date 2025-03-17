// Copyright (c) 2025, phamos.eu and contributors
// For license information, please see license.txt

<<<<<<< HEAD
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
	refresh:function(frm){
		frm.doc.sales_order_status_information.forEach(row => {
            let data1= (row.delivered_total_hrs/row.total_hrs).toFixed(2)
            console.log(')))))))))))))))))))))',data)
            let data = response.message;
            let values = data.map(d => data);
            new frappe.Chart("#chart", {
			    type: "bar",
			    data: {
			        datasets: [{ name: "Total Sales", values:values}]
			    }
			});
        });
        //m.refresh_field("items");  
	}
});



function add_row_to_sales_order(frm){
	frappe.call({
        method: "frappe.client.get_list",
        args: {
            doctype: "Sales Order",
            filters: {
                customer: frm.doc.customer,
                status: ["in", ["To Deliver", "To Bill", "To Deliver and Bill"]]
            },
            fields: ["name", "status", "total_qty"],
            order_by: "transaction_date desc",
        },
        callback: function(response) {
            if (response.message.length > 0) {
                frm.clear_table("sales_order_status_information"); // Clear existing data
                response.message.forEach(order => {
                    let row = frm.add_child("sales_order_status_information");
                    row.sales_order = order.name;
                    row.total_hrs = order.total_qty;
                    row.status = order.status;
                });
                frm.refresh_field("sales_order_status_information"); // Refresh child table
            } 
        }
    });
}


frappe.ui.form.on("Sales Order Status Information", {
	setup:function(frm){
		if(!frm.is_new()){
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
	}
});

/*new frappe.Chart("#chart", {
    type: "bar",
    data: {
        labels: labels,
        datasets: [{ name: "Total Sales", values: values }]
    }
});*/
=======
// frappe.ui.form.on("Implementation", {
// 	refresh(frm) {

// 	},
// });
>>>>>>> 250ef5c4fa6b888e08874909c04625ee2c1c4bd7
