// Copyright (c) 2025, phamos.eu and contributors
// For license information, please see license.txt
frappe.ui.form.on("Implementation", {
	setup:function(frm){
		if(!frm.is_new()){
			add_row_to_sales_order(frm)
			frappe.call({
				method: "phamos.phamos.doctype.implementation.implementation.get_financial_history",
				args: {'name':frm.doc.name,'customer':frm.doc.customer},
				callback: function (r) {
					if(r.message){
						frm.set_value('sales_order_total_hrs', r.message['sales_order_qty'])
						frm.set_value('delivered_total_hrs', r.message['dn_qty'])
						frm.set_value('total_hrs_timesheet', r.message['timesheet_hrs'])
						frm.set_value('remaining_hrs',r.message['remaining_hrs'])
						let label1= ['Sales Order Hrs']
		                let value1 = [r.message['sales_order_qty']]

		                
		                $(frm.fields_dict.total_sales.wrapper).html('<div id="total-sales"><h1>hiiii</h1></div>');
		                
		                let chart = new frappe.Chart("#total-sales", {
		                    type: 'percentage',
		                    data: {
		                        labels: label1,
		                        datasets: [
				                    {name:"Financial Information",values: value1}]},
		                    colors: ['#7cd6fd'],
		                    height: 250,
		                    width:250
		                });
		                
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
	refresh: function(frm) {
		if(!frm.is_new()){
			frappe.call({
				method: "phamos.phamos.doctype.implementation.implementation.get_financial_history",
				args: {'customer':frm.doc.customer, 'name':frm.doc.name},
				callback: function (r) {
					if(r.message){
						let warning_label = r.message['sales_order_qty'] < r.message['timesheet_hrs'] ? '⚠️ TH exceeded!' : '';
						
						let labels = ['Delivered Hrs', 'Timesheet Hrs','Remaining Hrs',  warning_label];
		                let values = [r.message['dn_qty'], r.message['timesheet_hrs'],r.message['remaining_hrs'], 0];
 	                
		                $(frm.fields_dict.order_chart.wrapper).html('<div id="delivered-qty-chart"><h1></h1></div>');
		               
		                let chart = new frappe.Chart("#delivered-qty-chart", {
		                    type: 'percentage',
		                    data: {
		                        labels: labels,
		                        datasets: [
				                    {name:"Financial Information",values: values}]},
		                    colors: ['green','pink','blue','red'],
		                    height: 250,
		                    width:500
		                });

		                let label1= ['Sales Order Hrs']
		                let value1 = [r.message['sales_order_qty']]

		                
		                $(frm.fields_dict.total_sales.wrapper).html('<div id="total-sales"></div>');
						
						let chart1 = new frappe.Chart("#total-sales", {
		                    type: 'percentage',
		                    data: {
		                        labels: label1,
		                        datasets: [
				                    {name:"Financial Information",values: value1}]},
		                    colors: ['#7cd6fd'],
		                    height: 250,
		                    width:250
		                });
		           	}
				},
			});
		}
    },
});



function add_row_to_sales_order(frm){
	frappe.call({
        method: "frappe.client.get_list",
        args: {
            doctype: "Sales Order",
            filters: {
                customer: frm.doc.customer,
                custom_implementation:frm.doc.name,
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

