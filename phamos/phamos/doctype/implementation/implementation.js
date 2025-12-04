// Copyright (c) 2025, phamos.eu and contributors
// For license information, please see license.txt
frappe.ui.form.on("Implementation", {
    from_date(frm) {
        render_resource_planning_graph(frm); // From date change
    },
    to_date(frm) {
        render_resource_planning_graph(frm); // To date change
    },
    prediction_from_date(frm) {
        render_resource_planning_graph(frm, true); // Prediction date change
    },
    prediction_to_date(frm) {
        render_resource_planning_graph(frm, true); // Prediction date change
    },
    setup: function (frm) {
            add_row_to_sales_order(frm)
                frappe.call({
                    method: "phamos.phamos.doctype.implementation.implementation.get_financial_history",
                    args: { 'name': frm.doc.name, 'customer': frm.doc.customer },
                    callback: function (r) {
                        if (r.message) {
                            frm.set_value('sales_order_total_hrs', r.message['sales_order_qty'])
                            frm.set_value('delivered_total_hrs', r.message['dn_qty'])
                            frm.set_value('total_hrs_timesheet', r.message['timesheet_hrs'])
                            frm.set_value('remaining_hrs', r.message['remaining_hrs'])
                            let label1 = ['Sales Order Hrs']
                            let value1 = [r.message['sales_order_qty']]


                            $(frm.fields_dict.total_sales.wrapper).html('<div id="total-sales"><h1>hiiii</h1></div>');

                            let chart = new frappe.Chart("#total-sales", {
                                type: 'percentage',
                                data: {
                                    labels: label1,
                                    datasets: [
                                        { name: "Financial Information", values: value1 }]
                                },
                                colors: ['#7cd6fd'],
                                height: 250,
                                width: 250
                            });

                            frm.save()
                        }
                    },
                });
    },
    refresh: function (frm) {
        // add_row_to_sales_order(frm);
        frm.fields_dict.reset.$input.on('click', function () {
            frm.set_value("prediction_from_date", "");
            frm.set_value("prediction_to_date", "");
            render_resource_planning_graph(frm, false); // without prediction filter
        });

        // Update button
        // frm.fields_dict.update.$input.on('click', function () {
        //     render_resource_planning_graph(frm, true); // use prediction filter
        // });
        if (!frm.doc.prediction_from_date && !frm.doc.prediction_to_date) {
            render_resource_planning_graph(frm, false);  // normal graph
        } else {
            render_resource_planning_graph(frm, true);   // prediction filter ke sath
        }

        // Quick Add Predictions Button - Render in HTML field
        
        if (frm.fields_dict.quick_add_button_html && frm.fields_dict.quick_add_button_html.$wrapper) {
            let button_html = `
                <div style="margin: 15px 0; padding: 10px; background-color: #f8f9fa; border-radius: 5px; text-align: center;">
                    <button class="btn btn-primary" id="quick-add-predictions-btn" style="font-size: 14px;">
                        <svg class="icon icon-sm" style="margin-right: 5px;">
                            <use href="#icon-add"></use>
                        </svg>
                        Quick Add Predictions
                    </button>
                </div>
            `;
            frm.fields_dict.quick_add_button_html.$wrapper.html(button_html);
            
            frm.fields_dict.quick_add_button_html.$wrapper.find('#quick-add-predictions-btn').on('click', function() {
        let today = new Date();
        let months = [];
        
        // Generate current month + next 3 months
        for (let i = 0; i < 4; i++) {
            let date = new Date(today.getFullYear(), today.getMonth() + i, 1);
            let year = date.getFullYear();
            let month = String(date.getMonth() + 1).padStart(2, '0');
            let monthYear = `${year}-${month}`;
            months.push({ month_and_year: monthYear, prediction: 0, date: frappe.datetime.nowdate() });
        }
        
        // Generate month options for next 12 months
        let monthOptions = [];
        for (let i = 0; i < 12; i++) {
            let date = new Date(today.getFullYear(), today.getMonth() + i, 1);
            let year = date.getFullYear();
            let month = String(date.getMonth() + 1).padStart(2, '0');
            monthOptions.push(`${year}-${month}`);
        }
        
        let d = new frappe.ui.Dialog({
            title: __('Quick Add Predictions'),
            fields: [
                {
                    fieldname: 'predictions_table',
                    fieldtype: 'Table',
                    label: 'Predictions',
                    cannot_add_rows: false,
                    cannot_delete_rows: false,
                    in_place_edit: true,
                    data: months,
                    fields: [
                        {
                            fieldname: 'month_and_year',
                            fieldtype: 'Select',
                            in_list_view: 1,
                            label: 'Month And Year',
                            options: monthOptions.join('\n'),
                            columns: 2
                        },
                        {
                            fieldname: 'prediction',
                            fieldtype: 'Int',
                            in_list_view: 1,
                            label: 'Prediction',
                            columns: 2
                        },
                        {
                            fieldname: 'date',
                            fieldtype: 'Date',
                            in_list_view: 1,
                            default: frappe.datetime.nowdate(),
                            read_only: 1,
                            label: 'Date',
                            columns: 2
                        }
                    ]
                }
            ],
            primary_action_label: __('Add Predictions'),
            primary_action(values) {
                // Add predictions to child table
                let tableData = values.predictions_table || [];
                
                tableData.forEach(row => {
                    if (row.prediction && row.prediction > 0 && row.month_and_year) {
                        let child_row = frm.add_child('resource_planning_prediction');
                        child_row.month_and_year = row.month_and_year;
                        child_row.prediction = row.prediction;
                        child_row.date = row.date || frappe.datetime.nowdate();
                        // Don't set idx - let the framework handle it
                    }
                });
                
                // Sort the child table by month_and_year in ascending order before saving
                if (frm.doc.resource_planning_prediction) {
                    frm.doc.resource_planning_prediction.sort((a, b) => {
                        let dateA = a.month_and_year || '';
                        let dateB = b.month_and_year || '';
                        return dateA.localeCompare(dateB);
                    });
                    
                    // Re-index the sorted rows
                    frm.doc.resource_planning_prediction.forEach((row, index) => {
                        row.idx = index + 1;
                    });
                }
                
                // Clear and refresh the child table field to force UI update
                frm.fields_dict['resource_planning_prediction'].grid.grid_rows = [];
                frm.fields_dict['resource_planning_prediction'].grid.refresh();
                
                frm.save().then(() => {
                    frm.refresh_field('resource_planning_prediction');
                    frappe.show_alert({
                        message: __('Predictions added successfully'),
                        indicator: 'green'
                    });
                });
                
                d.hide();
            }
        });
        
        d.show();
            });
        }
        

        let options = [];
        let today = new Date();
        let currentMonth = today.getMonth(); // 0-based (0 = Jan)
        let currentYear = today.getFullYear();

        for (let i = 0; i < 12; i++) {
            let date = new Date(currentYear, currentMonth + i, 1); // add i months
            let year = date.getFullYear();
            let month = String(date.getMonth() + 1).padStart(2, '0'); // 1-based month
            options.push(`${year}-${month}`);
        }

        console.log("Setting options for month_and_year:", options);

        if (frm.fields_dict['resource_planning_prediction']) {
            frm.fields_dict['resource_planning_prediction'].grid.update_docfield_property(
                'month_and_year',
                'options',
                options.join('\n')
            );
        } else {
            console.warn("Child table field not available yet.");
        }

        frm.add_custom_button('Set Implementation Status', () => {
            let d = new frappe.ui.Dialog({
                title: 'Set Implementation Status',
                fields: [
                    {
                        label: 'Status',
                        fieldname: 'status',
                        fieldtype: 'Select',
                        options: ['Completed', 'Cancelled', 'Reactivated', 'Hold', 'Escalated'],
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
                    if (['Completed', 'Cancelled'].includes(values.status)) {
                        // ✅ Backend check only for these 3
                        frappe.call({
                            method: 'phamos.phamos.doctype.implementation.implementation.are_all_projects_closed',
                            args: {
                                implementation_name: frm.doc.name
                            },
                            callback: function (r) {
                                if (r.message === true) {
                                    frm.set_value('status', values.status);
                                    frm.set_value('status_statement', values.reason);
                                    frm.save();
                                    d.hide();
                                } else {
                                    frappe.throw(__('All projects must be closed before setting this status.'));
                                }
                            }
                        });
                    } else if (values.status === 'Reactivated') {
                        frm.set_value('status', 'Open');
                        frm.set_value('status_statement', values.reason);
                        frm.save();
                        d.hide();
                    }else {
                        // ✅ Hold & Escalated bypass condition
                        frm.set_value('status', values.status);
                        frm.set_value('status_statement', values.reason);
                        frm.save();
                        d.hide();
                    }
                }
            });
            d.show();
        });

        //////////////////////////////////////////////////////////////////////////////////////////////////////

        // radar chart
        // Add canvas to first field
        if (!frm.fields_dict.module_chart.$wrapper.find('canvas').length) {
            frm.fields_dict.module_chart.$wrapper.html('<canvas id="radar-chart-1" style="height: 500px;width: 500px;"></canvas>');
        }

        // Add canvas to second field
        if (!frm.fields_dict.modules_overview.$wrapper.find('canvas').length) {
            frm.fields_dict.modules_overview.$wrapper.html('<canvas id="radar-chart-2" style="height: 300px;width: 300px;"></canvas>');
        }

        // Load Chart.js and render
        frappe.require("https://cdn.jsdelivr.net/npm/chart.js", function () {
            render_module_chart(frm, 'radar-chart-1');
            render_module_chart(frm, 'radar-chart-2');
        });
        // radar chart ends
            frappe.call({
                method: "phamos.phamos.doctype.implementation.implementation.get_financial_history",
                args: { 'customer': frm.doc.customer, 'name': frm.doc.name },
                callback: function (r) {
                    if (r.message) {
                        if (r.message['sales_order_qty'] < r.message['timesheet_hrs']) {
                            let string1 = "TS Hrs exceeding Open SO Hrs"
                            let remaining_hrs = Math.abs(r.message['remaining_hrs']).toString();
                            let string2 = "TH"
                            let warning_label = r.message['sales_order_qty'] < r.message['timesheet_hrs'] ? '⚠️' + string1 : '';

                            let labels = ['DN Hrs', 'TS Hrs', warning_label];
                            let values = [r.message['dn_qty'], r.message['timesheet_hrs'], 0];

                            $(frm.fields_dict.order_chart.wrapper).html('<div id="delivered-qty-chart"><h1></h1></div>');

                            let chart = new frappe.Chart("#delivered-qty-chart", {
                                type: 'percentage',
                                data: {
                                    labels: labels,
                                    datasets: [
                                        { name: "Financial Information", values: values }]
                                },
                                colors: ['green', 'yellow', 'red'],
                                height: 250,
                                width: 550,
                                maxLegendLines: 2,
                                truncateLegends: 10,
                            });
                        }
                        else if (r.message['sales_order_qty'] > r.message['timesheet_hrs']) {
                            let labels = ['DN Hrs', 'TS Hrs', 'Rm Hrs'];
                            let values = [r.message['dn_qty'], r.message['timesheet_hrs'], r.message['remaining_hrs']];

                            $(frm.fields_dict.order_chart.wrapper).html('<div id="delivered-qty-chart"><h1></h1></div>');

                            let chart = new frappe.Chart("#delivered-qty-chart", {
                                type: 'percentage',
                                data: {
                                    labels: labels,
                                    datasets: [
                                        { name: "Financial Information", values: values }]
                                },
                                colors: ['green', 'yellow', 'blue'],
                                height: 250,
                                width: 500,
                                maxLegendLines: 2,
                                truncateLegends: 10,
                            });
                        }
                        else if (r.message['sales_order_qty'] == r.message['timesheet_hrs']) {
                            let labels = ['DN Hrs', 'TS Hrs', 'Rm Hrs'];
                            let values = [r.message['dn_qty'], r.message['timesheet_hrs'], r.message['remaining_hrs']];

                            $(frm.fields_dict.order_chart.wrapper).html('<div id="delivered-qty-chart"><h1></h1></div>');

                            let chart = new frappe.Chart("#delivered-qty-chart", {
                                type: 'percentage',
                                data: {
                                    labels: labels,
                                    datasets: [
                                        { name: "Financial Information", values: values }]
                                },
                                colors: ['green', 'yellow', 'blue'],
                                height: 250,
                                width: 500,
                                maxLegendLines: 2,
                                truncateLegends: 10,
                            });

                        }
                    }
                },
            });
    },
    onload: function (frm) {
        frm.set_df_property("graph_overview_section", "collapsible", 0);
        if (frm.is_new()) {
            frappe.call({
                method: 'frappe.client.get_list',
                args: {
                    doctype: 'Implementation Module',
                    fields: ['name', 'is_standard', 'is_required'],
                    filters: {
                        is_standard: 1
                    },
                    limit_page_length: 1000
                },
                callback: function (r) {
                    if (r.message) {
                        let existingModules = frm.doc.modules || [];

                        r.message.forEach(module => {
                            let existingRow = existingModules.find(row => row.module === module.name);

                            if (existingRow) {
                                existingRow.is_required = module.is_required ? 1 : 0;
                            } else {
                                let child = frm.add_child('modules');
                                child.module = module.name;
                                child.is_required = module.is_required ? 1 : 0;
                            }
                        });

                        frm.refresh_field('modules');
                    }
                }
            });
        }
    },
    generate_auto_email: function (frm) {
        frappe.call({
                    method: "phamos.phamos.doctype.implementation.implementation.generate_auto_email_reports",
                    args: {
                        docname: frm.doc.name
                    },
                    callback: function (r) {
                        if (!r.exc) {
                            frappe.msgprint("Auto Email Reports generated successfully!");
                            frm.reload_doc();
                        }
                    }
                });
    }



});
function render_module_chart(frm, canvasId) {
    const labels = [];
    const currentLevels = [];
    const targetLevels = [];

    (frm.doc.modules || []).forEach(row => {
        if (row.is_required) {
            let label = row.module;

            const duplicateCount = labels.filter(l => l.startsWith(row.module)).length;

            if (duplicateCount > 0 && row.stage) {
                label = `${row.module} (${row.stage})`;
            } else if (duplicateCount > 0) {
                label = `${row.module} (${duplicateCount + 1})`;
            }

            labels.push(label);
            currentLevels.push(row.current_level || 0);
            targetLevels.push(row.target_level || 0);
        }
    });

    const ctx = document.getElementById(canvasId);
    if (!ctx) return;

    // Destroy old chart if exists
    if (ctx.chartInstance) {
        ctx.chartInstance.destroy();
    }

    ctx.chartInstance = new Chart(ctx, {
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

function add_row_to_sales_order(frm) {
    frappe.call({
        method: "frappe.client.get_list",
        args: {
            doctype: "Sales Order",
            filters: {
                customer: frm.doc.customer,
                custom_implementation: frm.doc.name,
                status: ["in", ["To Deliver", "To Bill", "To Deliver and Bill"]]
            },
            fields: ["name", "status", "total_qty", "title"],
            order_by: "transaction_date desc",
        },
        callback: function (response) {
            if (response.message.length > 0) {
                frm.clear_table("sales_order_status_information"); // Clear existing data

                response.message.forEach(order => {
                    let row = frm.add_child("sales_order_status_information");
                    row.sales_order = order.name;
                    row.so_title = order.title;
                    row.total_hrs = order.total_qty;
                    row.status = order.status;
                });
                frm.refresh_field("sales_order_status_information"); // Refresh child table
            }
        }
    });
}
function render_resource_planning_graph(frm, usePredictionFilter = false) {
    const fromMonth = frm.doc.from_date ? frm.doc.from_date.slice(0, 7) : null;
    const toMonth = frm.doc.to_date ? frm.doc.to_date.slice(0, 7) : null;

    const predictionFrom = frm.doc.prediction_from_date
        ? frm.doc.prediction_from_date
        : null;
    const predictionTo = frm.doc.prediction_to_date
        ? frm.doc.prediction_to_date
        : null;

    function isWithinRange(monthYear, from, to) {
        return (!from || monthYear >= from) && (!to || monthYear <= to);
    }

    // Planning data normal filter (month_and_year)
    const planningData = (frm.doc.resource_planning || []).filter(row =>
        row.month_and_year && isWithinRange(row.month_and_year, fromMonth, toMonth)
    );

    // Prediction data filter
    let predictionData = (frm.doc.resource_planning_prediction || []).filter(row =>
        row.month_and_year && isWithinRange(row.month_and_year, fromMonth, toMonth)
    );

    // if prediction_from_date ya prediction_to_date is set then override it
    if (predictionFrom || predictionTo) {
        predictionData = predictionData.filter(row => {
            let creationDate = row.date ? row.date.slice(0, 10) : null; // YYYY-MM-DD
            return creationDate && (
                (!predictionFrom || creationDate >= predictionFrom) &&
                (!predictionTo || creationDate <= predictionTo)
            );
        });
    }

    console.log("Planning Data:", planningData);
    console.log("Prediction Data:", predictionData);


    const categorySet = new Set();
    planningData.forEach(row => categorySet.add(row.month_and_year));
    predictionData.forEach(row => categorySet.add(row.month_and_year));

    const categories = Array.from(categorySet).sort((a, b) => new Date(a) - new Date(b));
    const categoryIndexMap = {};
    categories.forEach((month, idx) => categoryIndexMap[month] = idx);

    const billable = new Array(categories.length).fill(0);
    const nonBillable = new Array(categories.length).fill(0);

    planningData.forEach(row => {
        const idx = categoryIndexMap[row.month_and_year];
        billable[idx] += row.billable_time_spent || 0;
        nonBillable[idx] += row.non_billable_time_spent || 0;
    });

    const predictionPoints = predictionData.map(row => ({
        x: categoryIndexMap[row.month_and_year],
        y: row.prediction || 0
    })).sort((a, b) => a.x - b.x);

    const monthlyPredictionSum = {};
    const monthlyPredictionCount = {};
    predictionData.forEach(row => {
        const month = row.month_and_year;
        monthlyPredictionSum[month] = (monthlyPredictionSum[month] || 0) + (row.prediction || 0);
        monthlyPredictionCount[month] = (monthlyPredictionCount[month] || 0) + 1;
    });

    const averagePredictions = categories.map(month => {
        const sum = monthlyPredictionSum[month] || 0;
        const count = monthlyPredictionCount[month] || 0;
        return count > 0 ? sum / count : null;
    });

    // Function to render chart in any field
    function renderChartInField(fieldname, containerId, height = 400, width = 400) {
        const wrapper = frm.fields_dict[fieldname].$wrapper;
        wrapper.empty();
        wrapper.append(`<div id="${containerId}" style="height:${height}px; width:${width}px;"></div>`);

        Highcharts.chart(containerId, {
            chart: { zoomType: 'xy' },
            title: { text: 'Billable vs Non-Billable Time with Prediction' },
            xAxis: { categories, title: { text: 'Month' } },
            yAxis: { title: { text: 'Time (hrs)' } },
            tooltip: { shared: true, valueSuffix: ' hrs' },
            legend: {
                itemStyle: {
                    fontSize: '10px'
                }
            },
            plotOptions: {
                area: { stacking: 'normal', marker: { enabled: false } },
                line: { marker: { enabled: true, radius: 4 } }
            },
            series: [
                { name: 'Non-Billable Time', type: 'area', data: nonBillable, color: '#ff9933' },
                { name: 'Billable Time', type: 'area', data: billable, color: '#3399ff' },
                {
                    name: 'Prediction', type: 'scatter', data: predictionPoints, color: '#28a745',
                    marker: { symbol: 'circle', radius: 5 },
                    tooltip: { pointFormat: '<span style="color:{series.color}">●</span> {series.name}: <b>{point.y} hrs</b><br/>' }
                },
                {
                    name: 'Average Prediction', type: 'line', data: averagePredictions, color: 'red',
                    dashStyle: 'ShortDash',
                    marker: { enabled: true, symbol: 'diamond', radius: 4 },
                    tooltip: { pointFormat: '<span style="color:{series.color}">●</span> {series.name}: <b>{point.y:.2f} hrs</b><br/>' }
                }
            ]
        });
    }


    // Render in both fields
    renderChartInField('resource_chart', 'resource-planning-highchart-1', 400, 1000);
    renderChartInField('total_time_spend', 'resource-planning-highchart-2', 300, 300);

}



frappe.ui.form.on("Sales Order Status Information", {
    setup: function (frm) {
            frappe.call({
                method: "phamos.phamos.doctype.implementation.implementation.get_financial_history",
                args: { 'name': frm.doc.name },
                callback: function (r) {
                    if (r.message) {
                        frm.set_value('sales_order_total_hrs', r.message['sales_order_qty'])
                        frm.set_value('delivered_total_hrs', r.message['dn_qty'])
                        frm.set_value('total_hrs_timesheet', r.message['timesheet_hrs'])
                        frm.set_value('remaining_hrs', r.message['remaining_hrs'])
                    }
                },
            });
    }
});

frappe.ui.form.on('Implementation Item', {
    module: function(frm, cdt, cdn) {
        let child = locals[cdt][cdn];

        if (!child.module) {
            frappe.model.set_value(cdt, cdn, 'current_level', '');
            return;
        }
        let rows = frm.doc.modules.filter(r => r.module === child.module);
        if (rows.length > 1) {
            let previous_row = rows[0];

            if (previous_row.current_level) {
                frappe.model.set_value(cdt, cdn, 'current_level', previous_row.current_level);
            }
        }
    }
});








