// Copyright (c) 2025, phamos.eu and contributors
// For license information, please see license.txt
frappe.ui.form.on("Implementation", {
	setup:function(frm){
		if(!frm.is_new()){
			add_row_to_sales_order(frm)
			if (frm.doc.internal_implementation == 0) {
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
							
							frm.save()
						}
					},
				});
			}
		}
	},
	refresh: function(frm) {
		if (!frm.is_new()) {
			frm.add_custom_button('Set Implementation Status', () => {
				frappe.call({
					method: 'phamos.phamos.doctype.implementation.implementation.are_all_projects_closed',
					args: {
						implementation_name: frm.doc.name
					},
					callback: function (r) {
						if (r.message === true) {
							let d = new frappe.ui.Dialog({
								title: 'Set Implementation Status',
								fields: [
									{
										label: 'Status',
										fieldname: 'status',
										fieldtype: 'Select',
										options: ['Completed', 'Cancelled'],
										reqd: 1
									},
									{
										label: 'Reason',
										fieldname: 'reason',
										fieldtype: 'Small Text',
										reqd: 1
									}
								],
								primary_action_label: 'Submit',
								primary_action(values) {
									frm.set_value('status', values.status);
									frm.set_value('status_statement', values.reason);
									frm.save();
									d.hide();
								}
							});
							d.show();
						} else {
							frappe.throw(__('All projects must be closed before setting implementation status.'));
						}
					}
				});
			});
		}
		
		if (!frm.doc.resource_planning || frm.doc.resource_planning.length === 0) {
            return;
        }

        const categories = [];
        const billable = [];
        const nonBillable = [];

        frm.doc.resource_planning.forEach(row => {
            categories.push(row.month_and_year);
            billable.push(row.billable_time_spent || 0);
            nonBillable.push(row.non_billable_time_spent || 0);
        });

        const wrapper = frm.fields_dict.resource_chart.$wrapper;
        wrapper.empty();
        wrapper.append('<div id="resource-planning-highchart" style="height:400px;"></div>');

        // Render Highchart
        Highcharts.chart('resource-planning-highchart', {
            chart: {
                type: 'area'
            },
            title: {
                text: 'Billable vs Non-Billable Time'
            },
            xAxis: {
                categories: categories,
                tickmarkPlacement: 'on',
                title: {
                    enabled: false
                }
            },
            yAxis: {
                title: {
                    text: ''
                },
                labels: {
                    formatter: function () {
                        return this.value;
                    }
                }
            },
            tooltip: {
                shared: true,
                valueSuffix: 'hrs'
            },
            plotOptions: {
                area: {
                    stacking: 'normal',
                    lineColor: '#666666',
                    lineWidth: 1,
                    marker: {
                        enabled: false
                    }
                }
            },
            series: [
				{
					name: 'Non-Billable Time',
					data: nonBillable,
					color: '#ff9933'
				},
				{
                name: 'Billable Time',
                data: billable,
                color: '#3399ff'
            },]
        });
    
		// radar chart
		if (!frm.fields_dict.module_chart.$wrapper.find('canvas').length) {
            frm.fields_dict.module_chart.$wrapper.html('<canvas id="radar-chart" style="height: 500px;width: 500px;"></canvas>');
        }

        frappe.require("https://cdn.jsdelivr.net/npm/chart.js", function () {
            render_module_chart(frm);
        });
		// radar chart ends
		if(!frm.is_new()){ 
			frappe.call({
				method: "phamos.phamos.doctype.implementation.implementation.get_financial_history",
				args: {'customer':frm.doc.customer, 'name':frm.doc.name},
				callback: function (r) {
					if(r.message){
						if( r.message['sales_order_qty'] < r.message['timesheet_hrs']){
							let string1 ="TS Hrs exceeding Open SO Hrs"
							let remaining_hrs = Math.abs(r.message['remaining_hrs']).toString();
							let string2 = "TH"
							let warning_label = r.message['sales_order_qty'] < r.message['timesheet_hrs'] ? '⚠️'+ string1: '';
							
							let labels = ['DN Hrs', 'TS Hrs', warning_label];
			                let values = [r.message['dn_qty'], r.message['timesheet_hrs'], 0];
	 	                
			                $(frm.fields_dict.order_chart.wrapper).html('<div id="delivered-qty-chart"><h1></h1></div>');
			               
			                let chart = new frappe.Chart("#delivered-qty-chart", {
			                    type: 'percentage',
			                    data: {
			                        labels: labels,
			                        datasets: [
					                    {name:"Financial Information",values: values}]},
				                    colors: ['green','yellow','red'],
				                    height: 250,
				                    width:550,
				                    maxLegendLines: 2,
				                    truncateLegends: 10, 
		                	});
		                }
		                else if(r.message['sales_order_qty'] > r.message['timesheet_hrs']){
							let labels = ['DN Hrs', 'TS Hrs','Rm Hrs'];
			                let values = [r.message['dn_qty'], r.message['timesheet_hrs'],r.message['remaining_hrs']];
	 	                
			                $(frm.fields_dict.order_chart.wrapper).html('<div id="delivered-qty-chart"><h1></h1></div>');
			               
			                let chart = new frappe.Chart("#delivered-qty-chart", {
			                    type: 'percentage',
			                    data: {
			                        labels: labels,
			                        datasets: [
					                    {name:"Financial Information",values: values}]},
				                    colors: ['green','yellow','blue'],
				                    height: 250,
				                    width:500,
				                    maxLegendLines: 2,
				                    truncateLegends: 10, 
		                	});
		           		}
		           		else if(r.message['sales_order_qty'] ==r.message['timesheet_hrs']){
		           			let labels = ['DN Hrs', 'TS Hrs','Rm Hrs'];
			                let values = [r.message['dn_qty'], r.message['timesheet_hrs'],r.message['remaining_hrs']];
	 	                
			                $(frm.fields_dict.order_chart.wrapper).html('<div id="delivered-qty-chart"><h1></h1></div>');
			               
			                let chart = new frappe.Chart("#delivered-qty-chart", {
			                    type: 'percentage',
			                    data: {
			                        labels: labels,
			                        datasets: [
					                    {name:"Financial Information",values: values}]},
				                    colors: ['green','yellow','blue'],
				                    height: 250,
				                    width:500,
				                    maxLegendLines: 2,
				                    truncateLegends: 10, 
		                	});

		           		}
		           	}
				},
			});
		}
    },
	onload: function(frm) {
        if (frm.is_new()) {
            frappe.call({
                method: 'frappe.client.get_list',
                args: {
                    doctype: 'Implementation Module',
                    fields: ['name'],
                    limit_page_length: 1000 
                },
                callback: function(r) {
                    if (r.message) {
                        r.message.forEach(module => {
                            let child = frm.add_child('modules');
                            child.module = module.name;
                        });
                        frm.refresh_field('modules');
                    }
                }
            });
        }
    }
});
function render_module_chart(frm) {
    const labels = [];
    const currentLevels = [];
    const targetLevels = [];

    (frm.doc.modules || []).forEach(row => {
        if (row.is_required) {
            labels.push(row.module);
            currentLevels.push(row.current_level || 0);
            targetLevels.push(row.target_level || 0);
        }
    });

    const ctx = document.getElementById('radar-chart');
    if (!ctx) return;

    if (window.moduleRadarChart) {
        window.moduleRadarChart.destroy();
    }

    window.moduleRadarChart = new Chart(ctx, {
        type: 'radar',
        data: {
            labels: labels,
            datasets: [
                {
                    label: 'Current Level',
                    data: currentLevels,
                    backgroundColor: 'rgba(75, 202, 234, 0.3)',
                    borderColor: '#00bcd4',
                    borderWidth: 2
                },
                {
                    label: 'Target Level',
                    data: targetLevels,
                    backgroundColor: 'rgba(192, 5, 5, 0.2)',
                    borderColor: 'red',
                    borderWidth: 2
                }
            ]
        },
        options: {
            responsive: true,
			maintainAspectRatio: false,

            scales: {
                r: {
                    suggestedMin: 0,
                    suggestedMax: 10,
                    pointLabels: {
                        font: {
                            size: 12
                        }
                    }
                }
            }
        }
    });
}

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
					}
				},
			});
		}
	}
});

