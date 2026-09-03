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
    user_with_permission(frm) {
    frm.trigger("render_auto_email_reports_section");
    },
    setup: function (frm) {
            if (frm.is_new()) {
                add_row_to_sales_order(frm);
            }
                frappe.call({
                    method: "phamos.phamos.doctype.implementation.implementation.get_financial_snapshot",
                    args: { 'name': frm.doc.name, 'customer': frm.doc.customer },
                    callback: function (r) {
                        if (r.message) {
                            const financial = r.message.financial_history || {};
                            let label1 = ['Sales Order Hrs'];
                            let value1 = [financial['sales_order_qty']];


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
                        }
                    },
                });
        // Address - filter by customer via Dynamic Link
        frm.set_query("billing_address", function() {
            return {
                query: "frappe.contacts.doctype.address.address.address_query",
                filters: {
                    link_doctype: "Customer",
                    link_name: frm.doc.customer
                }
            };
        });

        // Contact - billing_contact
        frm.set_query("billing_contact", function() {
            return {
                query: "frappe.contacts.doctype.contact.contact.contact_query",
                filters: {
                    link_doctype: "Customer",
                    link_name: frm.doc.customer
                }
            };
        });

        // Contact - invoicing_email_id
        frm.set_query("invoicing_email_id", function() {
            return {
                query: "frappe.contacts.doctype.contact.contact.contact_query",
                filters: {
                    link_doctype: "Customer",
                    link_name: frm.doc.customer
                }
            };
        });
    },
    refresh: function (frm) {
        if (!frm.is_new()) {
            add_row_to_sales_order(frm);
        }
        sort_resource_planning_by_month_desc(frm);
        setup_implementation_theme_watcher(frm);
        frm.trigger("append_implementation_chapters_to_modules");
        frm.trigger("render_review_cadence_indicator");

        if (!frm.is_new()) {
            frm.add_custom_button(__("Create Meeting"), () => {
                frappe.new_doc("Stakeholder Meeting", {
                    implementation: frm.doc.name,
                });
            });
        }
        frm.trigger("render_auto_email_reports_section");
        frm.trigger("render_active_reports_overview");
        frm.trigger("render_gitlab_projects_section");
        frm.trigger("render_gitlab_issues_section");
        frm.trigger("render_gitlab_milestones_section");
        frm.trigger("render_risk_overview_section");
        frm.trigger("render_rank_html_section");

        if (!document.getElementById("gitlab-custom-style")) {
            const style = document.createElement("style");
            style.id = "gitlab-custom-style";
            style.innerHTML = `
                .gitlab-project-connection .document-link {
                    display: flex;
                    align-items: center;
                }

                .gitlab-project-connection .document-link-badge {
                    display: flex;
                    align-items: center;
                    gap: 6px;
                }

                .gitlab-project-connection .btn-new {
                    height: 22px;
                    width: 22px;
                    padding: 0;
                    display: flex;
                    align-items: center;
                    justify-content: center;
                }

                .gitlab-project-connection .btn-new svg {
                    width: 12px;
                    height: 12px;
                }
            `;
            document.head.appendChild(style);
        }

        if (!document.getElementById("risk-overview-style")) {
            const riskStyle = document.createElement("style");
            riskStyle.id = "risk-overview-style";
            riskStyle.innerHTML = `
                .risk-overview-table {
                    width: 100%;
                    border-collapse: collapse;
                    font-size: 12px;
                }

                .risk-overview-table thead th {
                    text-align: left;
                    font-size: 10px;
                    text-transform: uppercase;
                    letter-spacing: 0.02em;
                    color: var(--text-muted, #8d99a6);
                    font-weight: 600;
                    padding: 4px 6px;
                    border-bottom: 1px solid var(--border-color, #d1d8dd);
                }

                .risk-overview-table tbody td {
                    padding: 6px;
                    border-bottom: 1px solid var(--border-color, #f0f2f4);
                    vertical-align: middle;
                }

                .risk-overview-table tbody tr:last-child td {
                    border-bottom: none;
                }

                .risk-overview-table tbody tr:hover {
                    background: var(--control-bg, #f8f9fa);
                }

                .risk-overview-table td.risk-level {
                    text-align: right;
                    font-weight: 600;
                }

                .risk-overview-pill {
                    display: inline-block;
                    padding: 1px 8px;
                    border-radius: 10px;
                    font-size: 10px;
                    font-weight: 600;
                    color: #fff;
                    white-space: nowrap;
                }
            `;
            document.head.appendChild(riskStyle);
        }

        if (!document.getElementById("implementation-rank-style")) {
            const rankStyle = document.createElement("style");
            rankStyle.id = "implementation-rank-style";
            rankStyle.innerHTML = `
                .implementation-rank-card {
                    border: 1px solid var(--border-color, #d1d8dd);
                    border-radius: 10px;
                    padding: 10px 12px;
                    background: var(--control-bg, #f8f9fa);
                }

                .implementation-rank-title {
                    font-size: 12px;
                    font-weight: 700;
                    text-transform: uppercase;
                    letter-spacing: 0.03em;
                    color: var(--text-muted, #8d99a6);
                    margin-bottom: 6px;
                }

                .implementation-rank-row {
                    display: flex;
                    justify-content: space-between;
                    align-items: center;
                    gap: 8px;
                    padding: 5px 0;
                    border-top: 1px solid var(--border-color, #e3e8ee);
                }

                .implementation-rank-row:first-of-type {
                    border-top: none;
                }

                .implementation-rank-label {
                    font-size: 13px;
                    color: var(--text-color, #2f3542);
                }

                .implementation-rank-value {
                    font-size: 12px;
                    font-weight: 700;
                    color: var(--text-color, #2f3542);
                    background: var(--bg-color, #ffffff);
                    border: 1px solid var(--border-color, #d1d8dd);
                    border-radius: 999px;
                    padding: 2px 8px;
                    min-width: 42px;
                    text-align: center;
                }
            `;
            document.head.appendChild(rankStyle);
        }

        // Avoid mutating child table on every refresh; server-side save logic keeps rows consistent.
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
                <style>
                    .quick-add-predictions-wrap {
                        margin: 15px 0;
                        padding: 10px;
                        background: var(--control-bg, #f8f9fa);
                        border: 1px solid var(--border-color, #d1d8dd);
                        border-radius: 8px;
                        text-align: center;
                    }

                    .quick-add-predictions-wrap #quick-add-predictions-btn {
                        font-size: 14px;
                    }
                </style>
                <div class="quick-add-predictions-wrap">
                    <button class="btn btn-primary" id="quick-add-predictions-btn">
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
                // Get predictions from dialog (only data, no indexes)
                let tableData = values.predictions_table || [];
                
                // Filter and add valid predictions to the child tablerender_gitlab_issues_section
                tableData.forEach(row => {
                    if (row.prediction && row.prediction > 0 && row.month_and_year) {
                        let child_row = frm.add_child('resource_planning_prediction');
                        child_row.month_and_year = row.month_and_year;
                        child_row.prediction = row.prediction;
                        child_row.date = frappe.datetime.nowdate();
                    }
                });
                
                // Sort by date descending (newest first) after adding new rows
                if (frm.doc.resource_planning_prediction && frm.doc.resource_planning_prediction.length > 0) {
                    frm.doc.resource_planning_prediction.sort((a, b) => {
                        let dateA = a.date ? new Date(a.date) : new Date(0);
                        let dateB = b.date ? new Date(b.date) : new Date(0);
                        return dateB - dateA; // Descending order (newest first)
                    });
                }
                
                // Refresh the grid to show new rows
                frm.refresh_field('resource_planning_prediction');
                
                d.hide();
                
                frm.save().then(() => {
                    frappe.show_alert({
                        message: __('Predictions added successfully'),
                        indicator: 'green'
                    });
                });
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
        frm.add_custom_button('Create Gitlab Project', function () {
        let d = new frappe.ui.Dialog({
            title: 'Create GitLab Project',
            fields: [
                {
                    label: 'GitLab Project Name',
                    fieldname: 'gitlab_project_name',
                    fieldtype: 'Data',
                    default: frm.doc.name,
                    reqd: 1,
                    description: 'You can edit this name for GitLab Project. Implementation link will remain the same.'
                }
            ],
            primary_action_label: 'Create Project',
            primary_action(values) {
                d.hide();
                frappe.call({
                    method: 'phamos.gitlab_integration.gitlab_group_utils.create_gitlab_project_for_implementation',
                    args: {
                        implementation_name: frm.doc.name,
                        gitlab_project_name: values.gitlab_project_name
                    },
                    callback: function (r) {
                        if (!r.exc) {
                            frm.reload_doc();
                        }
                    }
                });
            }
        });
        d.show();
    });

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
                    } else if (values.status === 'Escalated') {
                        d.hide();
                        frappe.call({
                            method: 'phamos.phamos.doctype.implementation.implementation.escalate_implementation',
                            args: {
                                implementation_name: frm.doc.name,
                                reason: values.reason
                            },
                            callback: function(r) {
                                if (!r.exc && r.message) {
                                    frappe.show_alert({
                                        message: __('Escalation {0} created', [r.message]),
                                        indicator: 'orange'
                                    });
                                    frm.reload_doc();
                                }
                            }
                        });
                    } else {
                        // Hold
                        frm.set_value('status', values.status);
                        frm.set_value('status_statement', values.reason);
                        frm.save();
                        d.hide();
                    }
                }
            });
            d.show();
        });

        frm.add_custom_button(__('Generate Weekly Report'), function () {
            const today = frappe.datetime.get_today();
            const toDate = frappe.datetime.add_days(today, -1);
            const fromDate = frappe.datetime.add_days(today, -7);

            let d = new frappe.ui.Dialog({
                title: __('Generate Weekly Customer Report'),
                fields: [
                    {
                        label: __('From Date'),
                        fieldname: 'from_date',
                        fieldtype: 'Date',
                        default: fromDate,
                        reqd: 1
                    },
                    {
                        label: __('To Date'),
                        fieldname: 'to_date',
                        fieldtype: 'Date',
                        default: toDate,
                        reqd: 1
                    }
                ],
                primary_action_label: __('Generate & Send'),
                primary_action(values) {
                    d.hide();
                    frappe.show_alert({ message: __('Generating report, please wait…'), indicator: 'blue' });
                    frappe.call({
                        method: 'phamos.phamos.doctype.implementation.implementation.generate_weekly_customer_report',
                        args: {
                            implementation_name: frm.doc.name,
                            from_date: values.from_date,
                            to_date: values.to_date
                        },
                        callback: function (r) {
                            if (!r.exc && r.message) {
                                const res = r.message;
                                frappe.show_alert({
                                    message: __('Report sent to {0} recipient(s). {1} ticket(s) included.', [
                                        res.recipients.length, res.issues_count
                                    ]),
                                    indicator: 'green'
                                });
                            }
                        }
                    });
                }
            });
            d.show();
        }, __('Reports'));

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
            load_module_chapter_titles(frm, () => {
                render_module_chart(frm, 'radar-chart-1');
                render_module_chart(frm, 'radar-chart-2');
            });
        });
        // radar chart ends
            frappe.call({
                method: "phamos.phamos.doctype.implementation.implementation.get_financial_snapshot",
                args: { 'customer': frm.doc.customer, 'name': frm.doc.name },
                callback: function (r) {
                    if (r.message) {
                        const financial = r.message.financial_history || {};
                        // Use one rounded set of values for both the fields and the chart
                        const float_precision = cint(frappe.sys_defaults.float_precision) || 3;
                        const sales_order_hrs = cint(financial['sales_order_qty']);
                        const delivered_total_hrs = flt(financial['dn_qty'], float_precision);
                        const timesheet_hrs = flt(financial['timesheet_hrs'], float_precision);
                        const remaining_hrs = flt(financial['remaining_hrs'], float_precision);

                        // Keep dashboard fields in sync without marking form dirty on every refresh.
                        const set_computed_field = (fieldname, value, normalize) => {
                            const current = normalize(frm.doc[fieldname]);
                            const next = normalize(value);
                            if (current !== next) {
                                frm.doc[fieldname] = value;
                                frm.refresh_field(fieldname);
                            }
                        };

                        set_computed_field('sales_order_total_hrs', sales_order_hrs, cint);
                        set_computed_field('delivered_total_hrs', delivered_total_hrs, v => flt(v, float_precision));
                        set_computed_field('total_hrs_timesheet', timesheet_hrs, v => flt(v, float_precision));
                        set_computed_field('remaining_hrs', remaining_hrs, v => flt(v, float_precision));

                        const has_overrun = remaining_hrs < 0;
                        const labels = ['DN Hrs', 'TS Hrs', 'Rm Hrs'];
                        // Percentage charts cannot plot a negative segment.
                        const values = [
                            delivered_total_hrs,
                            timesheet_hrs,
                            Math.max(remaining_hrs, 0),
                        ];
                        const remaining_color = has_overrun ? '#e24c4c' : '#418fe5';
                        const format_hrs = value =>
                            format_number(value, null, float_precision);

                        $(frm.fields_dict.order_chart.wrapper).html(`
                            <style>
                                .financial-chart-legend {
                                    display: flex;
                                    flex-wrap: wrap;
                                    gap: 42px;
                                    margin: -70px 0 35px 50px;
                                }
                                .financial-chart-legend-item {
                                    display: grid;
                                    grid-template-columns: 12px auto;
                                    column-gap: 9px;
                                    align-items: center;
                                }
                                .financial-chart-legend-dot {
                                    width: 12px;
                                    height: 12px;
                                    border-radius: 3px;
                                    grid-row: 1 / span 2;
                                }
                                .financial-chart-legend-label {
                                    font-weight: 600;
                                }
                                .financial-chart-legend-value {
                                    color: var(--text-muted);
                                    font-size: 12px;
                                }
                            </style>
                            <div id="delivered-qty-chart"></div>
                            <div class="financial-chart-legend">
                                <div class="financial-chart-legend-item">
                                    <span class="financial-chart-legend-dot" style="background:#48bb78"></span>
                                    <span class="financial-chart-legend-label">DN Hrs</span>
                                    <span class="financial-chart-legend-value">${format_hrs(delivered_total_hrs)}</span>
                                </div>
                                <div class="financial-chart-legend-item">
                                    <span class="financial-chart-legend-dot" style="background:#f6c768"></span>
                                    <span class="financial-chart-legend-label">TS Hrs</span>
                                    <span class="financial-chart-legend-value">${format_hrs(timesheet_hrs)}</span>
                                </div>
                                <div class="financial-chart-legend-item">
                                    <span class="financial-chart-legend-dot" style="background:${remaining_color}"></span>
                                    <span class="financial-chart-legend-label">Rm Hrs</span>
                                    <span class="financial-chart-legend-value">${format_hrs(remaining_hrs)}</span>
                                </div>
                            </div>
                        `);

                        new frappe.Chart("#delivered-qty-chart", {
                            type: 'percentage',
                            data: {
                                labels: labels,
                                datasets: [
                                    { name: "Financial Information", values: values }
                                ]
                            },
                            colors: ['#48bb78', '#f6c768', remaining_color],
                            showLegend: false,
                            height: 250,
                            width: 550,
                            maxLegendLines: 2,
                            truncateLegends: 10,
                        });
                    }
                },
            });
    },
    onload: function (frm) {
        populate_auto_email_reports(frm);
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
                    frm.reload_doc();
                }
            }
        });
    },
    render_active_reports_overview(frm) {
        if (frm.is_new()) return;
        if (!frm.fields_dict.active_email_reports) return;

        frappe.call({
            method: "phamos.phamos.doctype.implementation.implementation.get_active_email_reports_overview",
            args: { implementation: frm.doc.name },
            callback: r => {
                const data = r.message || {};
                const weekly = data.weekly_report || {};

                const buttonWrapper = frm.fields_dict.weekly_report_settings_button_html?.wrapper;
                if (buttonWrapper) {
                    $(buttonWrapper).html(
                        `<button class="btn btn-default btn-sm" type="button">${__("Weekly Report Settings")}</button>`
                    );
                    $(buttonWrapper).find("button").on("click", () => {
                        if (weekly.settings) {
                            frappe.set_route("Form", "Customer Weekly Report Settings", weekly.settings);
                        } else {
                            frappe.new_doc("Customer Weekly Report Settings", {
                                implementation: frm.doc.name,
                            });
                        }
                    });
                }

                const incoming = (data.reports || []).map(row => ({
                    email: row.email || "",
                    report: row.report || "",
                    frequency: row.frequency || "",
                    status: row.status || "",
                }));

                const existing = (frm.doc.active_email_reports || []).map(row => ({
                    email: row.email || "",
                    report: row.report || "",
                    frequency: row.frequency || "",
                    status: row.status || "",
                }));

                if (JSON.stringify(existing) === JSON.stringify(incoming)) return;

                frm.clear_table("active_email_reports");
                incoming.forEach(row => {
                    const child = frm.add_child("active_email_reports");
                    child.email = row.email;
                    child.report = row.report;
                    child.frequency = row.frequency;
                    child.status = row.status;
                });
                frm.refresh_field("active_email_reports");
                frm.doc.__unsaved = 0;
                frm.toolbar && frm.toolbar.show_title_as_dirty();
            },
        });
    },
    render_gitlab_issues_section(frm) {
        if (frm.is_new()) return;

        const implementation = frm.doc.name;
        const wrapper = frm.fields_dict.gitlab_issues_html?.wrapper;
        if (!wrapper) return;

        $(wrapper).html(`
            <div class="gitlab-project-connection">
                <div class="document-link" data-doctype="GitLab Issue">
                    <div class="document-link-badge">
                        <span class="count hidden"></span>
                        <a class="badge-link" href="#">${__("GitLab Issues")}</a>
                    </div>
                    <button class="btn btn-new btn-secondary btn-xs icon-btn">
                        <svg class="icon icon-sm"><use href="#icon-add"></use></svg>
                    </button>
                </div>
            </div>
        `);

        const $link  = $(wrapper).find(".document-link");
        const $count = $link.find(".count");

        // ── open list ──────────────────────────────────────────────────
        $link.find(".badge-link").on("click", e => {
            e.preventDefault();

            frappe.call({
                method: "frappe.client.get_list",
                args: {
                    doctype: "GitLab Project",
                    filters: { implementation: implementation },
                    fields: ["name"],
                    limit: 0
                },
                callback: r => {
                    const projects = (r.message || []).map(d => d.name);

                    if (!projects.length) {
                        frappe.msgprint(__("Koi GitLab Project linked nahi hai."));
                        return;
                    }

                    frappe.route_options = { gitlab_project: ["in", projects] };
                    frappe.set_route("List", "GitLab Issue", "List");
                }
            });
        });

        // ── new doc ────────────────────────────────────────────────────
        $link.find(".btn-new").on("click", e => {
            e.preventDefault();
            frappe.new_doc("GitLab Issue", {
                implementation: implementation
            });
        });

        frappe.call({
            method: "phamos.phamos.doctype.implementation.implementation.get_gitlab_issues_count",
            args: { implementation: implementation },
            callback: r => {
                const c = cint(r.message);
                $count.toggleClass("hidden", !c).text(c > 99 ? "99+" : c);  // ✅ $count
            },
            error: () => $count.addClass("hidden")
        });
    },
    render_gitlab_milestones_section(frm) {
        if (frm.is_new()) return;

        const implementation = frm.doc.name;
        const wrapper = frm.fields_dict.gitlab_milestones_html?.wrapper;
        if (!wrapper) return;

        $(wrapper).html(`
            <div class="gitlab-project-connection">
                <div class="document-link" data-doctype="GitLab Milestones">
                    <div class="document-link-badge">
                        <span class="count hidden"></span>
                        <a class="badge-link" href="#">${__("GitLab Milestones")}</a>
                    </div>
                    <button class="btn btn-new btn-secondary btn-xs icon-btn">
                        <svg class="icon icon-sm"><use href="#icon-add"></use></svg>
                    </button>
                </div>
            </div>
        `);

        const $link  = $(wrapper).find(".document-link");
        const $count = $link.find(".count");

        // ── open list ──────────────────────────────────────────────────
        $link.find(".badge-link").on("click", e => {
            e.preventDefault();

            frappe.call({
                method: "frappe.client.get_list",
                args: {
                    doctype: "GitLab Project",
                    filters: { implementation: implementation },
                    fields: ["name"],
                    limit: 0
                },
                callback: r => {
                    const projects = (r.message || []).map(d => d.name);

                    if (!projects.length) {
                        frappe.msgprint(__("Koi GitLab Project linked nahi hai."));
                        return;
                    }

                    frappe.route_options = { gitlab_project: ["in", projects] };
                    frappe.set_route("List", "GitLab Milestones", "List");
                }
            });
        });

        // ── new doc ────────────────────────────────────────────────────
        $link.find(".btn-new").on("click", e => {
            e.preventDefault();
            frappe.new_doc("GitLab Milestones", {
                implementation: implementation
            });
        });

        frappe.call({
            method: "phamos.phamos.doctype.implementation.implementation.get_gitlab_milestones_count",
            args: { implementation: implementation },
            callback: r => {
                const c = cint(r.message);
                $count.toggleClass("hidden", !c).text(c > 99 ? "99+" : c);
            },
            error: () => $count.addClass("hidden")
        });
    },
    render_gitlab_projects_section(frm) {
        if (frm.is_new()) return;

        const implementation = frm.doc.name;
        const wrapper = frm.fields_dict.gitlab_projects_html?.wrapper;

        if (!wrapper) return;

        // clear old
        $(wrapper).empty();

        // UI block (same style feel)
        $(wrapper).html(`
            <div class="gitlab-project-connection">
                <div class="document-link" data-doctype="GitLab Project">
                    <div class="document-link-badge">
                        <span class="count hidden"></span>
                        <a class="badge-link">${__("GitLab Project")}</a>
                    </div>
                    <button class="btn btn-new btn-secondary btn-xs icon-btn">
                        <svg class="icon icon-sm"><use href="#icon-add"></use></svg>
                    </button>
                </div>
            </div>
        `);

        const $link = $(wrapper).find(".document-link");
        const $count = $link.find(".count");

        // open list
        $link.find(".badge-link").on("click", e => {
            e.preventDefault();
            frappe.route_options = {
                    implementation: implementation
            };
            frappe.set_route("List", "GitLab Project", "List");
        });

        // new
        $link.find(".btn-new").on("click", e => {
            e.preventDefault();
            frappe.new_doc("GitLab Project", {
                implementation: implementation
            });
        });

        // count
        frappe.call({
            method: "phamos.phamos.doctype.implementation.implementation.get_gitlab_projects_count",
            args: {
                implementation: implementation
            },
            callback: r => {
                const c = cint(r.message);
                $count.toggleClass("hidden", !c).text(c > 99 ? "99+" : c || "0");
            }
        });
    },
    render_auto_email_reports_section(frm) {
        if (frm.is_new() || !frm.dashboard) return;

        const user = frm.doc.user_with_permission;
        const $parent = frm.dashboard.parent;
        const $transactions = $parent
            .find(".form-dashboard-section.form-links .section-body .transactions .form-documents")
            .first();

        if (!$transactions.length) {
            if (!frm.__auto_email_render_retry_scheduled) {
                frm.__auto_email_render_retry_scheduled = true;
                setTimeout(() => {
                    frm.__auto_email_render_retry_scheduled = false;
                    frm.trigger("render_auto_email_reports_section");
                }, 250);
            }
            return;
        }

        $parent.find(".auto-email-reports-section").remove();
        $transactions.find(".auto-email-report-connection").remove();

        let $row = $transactions.find(".row").filter(function () {
            return $(this).children(".col-md-4").length < 3;
        }).first();

        if (!$row.length) $row = $('<div class="row"></div>').appendTo($transactions);

        $row.append(`
            <div class="col-md-4 auto-email-report-connection">
                <div class="document-link" data-doctype="Auto Email Report">
                    <div class="document-link-badge">
                        <span class="count hidden"></span>
                        <a class="badge-link">${__("Auto Email Report")}</a>
                    </div>
                    <button class="btn btn-new btn-secondary btn-xs icon-btn">
                        <svg class="icon icon-sm"><use href="#icon-add"></use></svg>
                    </button>
                </div>
            </div>
        `);

        const $link = $row.find(".auto-email-report-connection .document-link").last();
        const $count = $link.find(".count");

        const needUser = () =>
            frappe.msgprint(__("Set User With Permission to see Auto Email Reports."));

        $link.find(".badge-link").on("click", e => {
            e.preventDefault();
            user ? (
                frappe.route_options = { user },
                frappe.set_route("List", "Auto Email Report", "List")
            ) : needUser();
        });

        $link.find(".btn-new").on("click", e => {
            e.preventDefault();
            user ? frappe.new_doc("Auto Email Report", { user }) : needUser();
        });

        if (!user) return $count.addClass("hidden").text("0");

        frappe.call({
            method: "phamos.phamos.doctype.implementation.implementation.get_auto_email_reports",
            args: { user_email: user },
            callback: r => {
                const c = cint(r.message);
                $count.toggleClass("hidden", !c).text(c > 99 ? "99+" : c || "0");
            }
        });
    },
    render_risk_overview_section(frm) {
        if (frm.is_new()) return;

        const wrapper = frm.fields_dict.risk_overview_html?.wrapper;
        if (!wrapper) return;

        frappe.call({
            method: "frappe.client.get_list",
            args: {
                doctype: "Risk Register Entry",
                filters: {
                    implementation: frm.doc.name,
                    status: ["!=", "Closed"],
                    close_date: ["is", "not set"]
                },
                fields: ["name", "risk_description", "implementation_risk_level", "risk_rating", "status"],
                order_by: "implementation_risk_level desc",
                limit_page_length: 5
            },
            callback: r => {
                const risks = r.message || [];

                if (!risks.length) {
                    $(wrapper).html(`<div class="text-muted">${__("No open risks.")}</div>`);
                    return;
                }

                const ratingColors = {
                    Extreme: "#e03131",
                    High: "#e8590c",
                    Moderate: "#f2b705",
                    Low: "#2f9e44"
                };
                const statusColors = {
                    Escalated: "#e03131",
                    "In Progress": "#1c7ed6",
                    Accepted: "#2f9e44",
                    "Not Started": "#868e96"
                };
                const pill = (text, colors) =>
                    `<span class="risk-overview-pill" style="background:${colors[text] || "#868e96"}">${frappe.utils.escape_html(text || "")}</span>`;
                const truncate = (text, max = 28) =>
                    text && text.length > max ? `${text.slice(0, max - 1)}…` : (text || "");

                const rows = risks.map(risk => `
                    <tr>
                        <td title="${frappe.utils.escape_html(risk.risk_description || "")}">
                            <a href="/app/risk-register-entry/${encodeURIComponent(risk.name)}">${frappe.utils.escape_html(truncate(risk.risk_description))}</a>
                        </td>
                        <td class="risk-level">${frappe.utils.escape_html(risk.implementation_risk_level ?? "")}</td>
                        <td>${pill(risk.risk_rating, ratingColors)}</td>
                        <td>${pill(risk.status, statusColors)}</td>
                    </tr>
                `).join("");

                $(wrapper).html(`
                    <div style="overflow-x: auto;">
                        <table class="risk-overview-table">
                            <thead>
                                <tr>
                                    <th>${__("Risk Description")}</th>
                                    <th>${__("Risk Level")}</th>
                                    <th>${__("Risk Rating")}</th>
                                    <th>${__("Status")}</th>
                                </tr>
                            </thead>
                            <tbody>${rows}</tbody>
                        </table>
                    </div>
                `);
            }
        });
    },
    render_review_cadence_indicator(frm) {
        if (frm.is_new() || !frm.doc.review_cadence || !frm.doc.next_review_due) return;

        const is_overdue = frappe.datetime.get_diff(frappe.datetime.get_today(), frm.doc.next_review_due) > 0;
        const due_label = frappe.datetime.str_to_user(frm.doc.next_review_due);

        frm.dashboard.add_indicator(
            is_overdue ? __("Review Overdue since {0}", [due_label]) : __("Next Review Due {0}", [due_label]),
            is_overdue ? "red" : "blue"
        );
    },
    render_rank_html_section(frm) {
        if (frm.is_new()) return;

        const wrapper = frm.fields_dict.rank_html?.wrapper;

        frappe.call({
            method: "phamos.phamos.doctype.implementation.implementation.recompute_implementation_stats",
            args: { name: frm.doc.name },
            callback: function (r) {
                if (!r.message) return;

                // Keep the on-screen stat fields fresh on every view, without
                // marking the form dirty (this is a read-time background sync).
                ["total_time_implementation_life", "total_time_last_12_months",
                 "total_time_last_6_months", "total_time_last_3_months",
                 "predicted_time_next_3_months"].forEach(fieldname => {
                    if (fieldname in r.message) {
                        frm.doc[fieldname] = r.message[fieldname];
                        frm.refresh_field(fieldname);
                    }
                });

                if (wrapper) {
                    const rankHtml = r.message.rank_html || `<div class="text-muted">${__("No ranking available.")}</div>`;
                    $(wrapper).html(rankHtml);
                }
            }
        });
    },
    append_implementation_chapters_to_modules(frm) {
        if (frm.is_new() || !frm.doc.name) return;
        if (frm.__chapter_sync_in_progress) return;

        frm.__chapter_sync_in_progress = true;

        frappe.call({
            method: "phamos.phamos.doctype.implementation.implementation.sync_modules_with_implementation_chapters",
            args: {
                name: frm.doc.name,
            },
            callback: (r) => {
                const addedCount = cint(r.message?.added_count || 0);
                if (addedCount > 0) {
                    frm.reload_doc();
                }
            },
            always: () => {
                frm.__chapter_sync_in_progress = false;
            }
        });
    },
    on_form_unload(frm) {
        if (frm.__implementation_theme_observer) {
            frm.__implementation_theme_observer.disconnect();
            frm.__implementation_theme_observer = null;
        }
        if (frm.__implementation_theme_redraw_timer) {
            clearTimeout(frm.__implementation_theme_redraw_timer);
            frm.__implementation_theme_redraw_timer = null;
        }
    }
});

function populate_auto_email_reports(frm) {
    if (!frm.doc.user_with_permission) return;

    // safety check for child table
    if (!frm.fields_dict.auto_email_report_record) {
        frappe.msgprint("Child Table 'auto_email_report_record' not found!");
        return;
    }

    frappe.call({
        method: "phamos.phamos.doctype.implementation.implementation.get_auto_email_reports_for_users",
        args: {
            user_list: frm.doc.user_with_permission
        },
        callback: function(r) {
            const incoming = (r.message || []).map(row => ({
                recipients: row.recipient || "",
                templates: row.template || "",
                frequency: row.frequency || ""
            }));

            const existing = (frm.doc.auto_email_report_record || []).map(row => ({
                recipients: row.recipients || "",
                templates: row.templates || "",
                frequency: row.frequency || ""
            }));

            if (JSON.stringify(existing) === JSON.stringify(incoming)) {
                return;
            }

            frm.clear_table("auto_email_report_record");

            incoming.forEach(function(row) {
                let child = frm.add_child("auto_email_report_record");
                child.recipients = row.recipients;
                child.templates = row.templates;
                child.frequency = row.frequency;
            });

            frm.refresh_field("auto_email_report_record");
            // Background reconciliation on load shouldn't mark the form as having unsaved changes.
            frm.doc.__unsaved = 0;
            frm.toolbar && frm.toolbar.show_title_as_dirty();
        }
    });
}
function load_module_chapter_titles(frm, callback) {
    const chapter_names = [
        ...new Set(
            (frm.doc.modules || [])
                .map(row => (row.implementation_chapter || "").trim())
                .filter(Boolean)
        ),
    ];

    frm.__chapter_titles = frm.__chapter_titles || {};
    const missing = chapter_names.filter(name => !(name in frm.__chapter_titles));

    if (!missing.length) {
        callback();
        return;
    }

    frappe.call({
        method: "frappe.client.get_list",
        args: {
            doctype: "Implementation Chapter",
            filters: { name: ["in", missing] },
            fields: ["name", "chapter_title"],
            limit_page_length: 0,
        },
        callback: r => {
            (r.message || []).forEach(chapter => {
                frm.__chapter_titles[chapter.name] = chapter.chapter_title;
            });
            callback();
        },
    });
}

function render_module_chart(frm, canvasId) {
    const labels = [];
    const currentLevels = [];
    const targetLevels = [];
    const chapter_titles = frm.__chapter_titles || {};

    (frm.doc.modules || []).forEach(row => {
        if (row.is_required) {
            const chapter_name = (row.implementation_chapter || "").trim();
            const baseLabel =
                (chapter_titles[chapter_name] || "").trim() ||
                chapter_name ||
                (row.module_description || "").trim() ||
                row.module;
            let label = baseLabel;

            const duplicateCount = labels.filter(l => l.startsWith(baseLabel)).length;

            if (duplicateCount > 0 && row.stage) {
                label = `${baseLabel} (${row.stage})`;
            } else if (duplicateCount > 0) {
                label = `${baseLabel} (${duplicateCount + 1})`;
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
    if (!frm.doc.customer || !frm.doc.name) {
        frm.clear_table("sales_order_status_information");
        frm.refresh_field("sales_order_status_information");
        return;
    }

    frappe.call({
        method: "phamos.phamos.doctype.implementation.implementation.get_financial_snapshot",
        args: {
            customer: frm.doc.customer,
            name: frm.doc.name,
        },
        callback: function (response) {
            const salesOrders = response.message?.sales_order_status_information || [];

            const incoming = salesOrders.map(order => ({
                sales_order: order.sales_order || "",
                so_title: order.so_title || "",
                total_hrs: order.total_hrs || 0,
                status: order.status || "",
                delivered_total_hrs: order.delivered_total_hrs || 0,
                remaining_hrs: order.remaining_hrs || 0,
            }));

            const existing = (frm.doc.sales_order_status_information || []).map(row => ({
                sales_order: row.sales_order || "",
                so_title: row.so_title || "",
                total_hrs: row.total_hrs || 0,
                status: row.status || "",
                delivered_total_hrs: row.delivered_total_hrs || 0,
                remaining_hrs: row.remaining_hrs || 0,
            }));

            if (JSON.stringify(existing) === JSON.stringify(incoming)) {
                return;
            }

            frm.clear_table("sales_order_status_information");

            salesOrders.forEach(order => {
                let row = frm.add_child("sales_order_status_information");
                row.sales_order = order.sales_order;
                row.so_title = order.so_title;
                row.total_hrs = order.total_hrs;
                row.status = order.status;
                row.delivered_total_hrs = order.delivered_total_hrs;
                row.remaining_hrs = order.remaining_hrs;
            });

            frm.refresh_field("sales_order_status_information");
            // Background reconciliation on refresh shouldn't mark the form as having unsaved changes.
            frm.doc.__unsaved = 0;
            frm.toolbar && frm.toolbar.show_title_as_dirty();
        }
    });
}

function sort_resource_planning_by_month_desc(frm) {
    const rows = frm.doc.resource_planning || [];
    if (rows.length < 2 || !frm.fields_dict.resource_planning) return;

    const normalizeMonth = value => (value ? String(value).trim() : "");
    const sortedRows = [...rows].sort((a, b) =>
        normalizeMonth(b.month_and_year).localeCompare(normalizeMonth(a.month_and_year))
    );

    const isOrderChanged = rows.some((row, idx) => row.name !== sortedRows[idx]?.name);
    if (!isOrderChanged) return;

    frm.doc.resource_planning = sortedRows;
    frm.refresh_field("resource_planning");
}

function get_implementation_theme_signature() {
    const html = document.documentElement;
    const body = document.body;
    const extractThemeClasses = (className) => {
        if (!className) return "";

        return className
            .split(/\s+/)
            .filter(cls => /theme|dark|light/i.test(cls))
            .sort()
            .join(" ");
    };

    const htmlClass = extractThemeClasses(html?.className || "");
    const bodyClass = extractThemeClasses(body?.className || "");
    const dataTheme = html?.getAttribute("data-theme") || "";
    const dataThemeMode = html?.getAttribute("data-theme-mode") || "";

    return [htmlClass, bodyClass, dataTheme, dataThemeMode].join("|");
}

function setup_implementation_theme_watcher(frm) {
    const redrawCharts = () => {
        const usePredictionFilter = !!(frm.doc.prediction_from_date || frm.doc.prediction_to_date);
        render_resource_planning_graph(frm, usePredictionFilter);

        load_module_chapter_titles(frm, () => {
            if (frm.fields_dict.module_chart?.$wrapper?.find("canvas").length) {
                render_module_chart(frm, "radar-chart-1");
            }
            if (frm.fields_dict.modules_overview?.$wrapper?.find("canvas").length) {
                render_module_chart(frm, "radar-chart-2");
            }
        });
    };

    if (frm.__implementation_theme_observer) {
        frm.__implementation_theme_signature = get_implementation_theme_signature();
        return;
    }

    frm.__implementation_theme_signature = get_implementation_theme_signature();

    const observer = new MutationObserver(() => {
        if (frm.__implementation_theme_redraw_timer) {
            clearTimeout(frm.__implementation_theme_redraw_timer);
        }

        frm.__implementation_theme_redraw_timer = setTimeout(() => {
            const nextSignature = get_implementation_theme_signature();
            if (nextSignature === frm.__implementation_theme_signature) return;

            frm.__implementation_theme_signature = nextSignature;
            redrawCharts();
        }, 120);
    });

    observer.observe(document.documentElement, {
        attributes: true,
        attributeFilter: ["class", "data-theme", "data-theme-mode"],
    });

    if (document.body) {
        observer.observe(document.body, {
            attributes: true,
            attributeFilter: ["class"],
        });
    }

    frm.__implementation_theme_observer = observer;
}

function render_resource_planning_graph(frm, usePredictionFilter = false) {
    if (typeof Highcharts === "undefined") {
        ["resource_chart", "total_time_spend"].forEach(fieldname => {
            const wrapper = frm.fields_dict[fieldname]?.$wrapper;
            if (wrapper) {
                wrapper.html('<div class="text-muted">Chart unavailable (Highcharts failed to load).</div>');
            }
        });
        return;
    }

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

    const htmlClass = (document.documentElement.className || "").toLowerCase();
    const bodyClass = (document.body ? document.body.className : "").toLowerCase();
    const dataTheme = (document.documentElement.getAttribute("data-theme") || "").toLowerCase();
    const dataThemeMode = (document.documentElement.getAttribute("data-theme-mode") || "").toLowerCase();
    const themeHints = [htmlClass, bodyClass, dataTheme, dataThemeMode].join(" ");

    const parseRgb = (color) => {
        if (!color) return null;
        const match = color.match(/rgba?\((\d+),\s*(\d+),\s*(\d+)/i);
        if (!match) return null;
        return {
            r: parseInt(match[1], 10),
            g: parseInt(match[2], 10),
            b: parseInt(match[3], 10),
        };
    };

    const getLuminance = (rgb) => {
        if (!rgb) return 255;
        return (0.2126 * rgb.r) + (0.7152 * rgb.g) + (0.0722 * rgb.b);
    };

    const bodyBg = document.body ? window.getComputedStyle(document.body).backgroundColor : "";
    const pageBg = window.getComputedStyle(document.documentElement).backgroundColor;
    const effectiveBg = bodyBg && bodyBg !== "rgba(0, 0, 0, 0)" ? bodyBg : pageBg;
    const bgLuminance = getLuminance(parseRgb(effectiveBg));

    const isDarkTheme = themeHints.includes("dark") || bgLuminance < 140;

    const chartPalette = isDarkTheme
        ? {
            textColor: "#e7edf3",
            mutedColor: "#b8c2cc",
            borderColor: "rgba(255, 255, 255, 0.22)",
            tooltipBg: "rgba(17, 24, 39, 0.96)",
            nonBillable: "#ffb84d",
            billable: "#66b3ff",
            prediction: "#58d68d",
            averagePrediction: "#ff6b6b",
        }
        : {
            textColor: "#2f3a45",
            mutedColor: "#6b7682",
            borderColor: "#d7dee5",
            tooltipBg: "rgba(255, 255, 255, 0.98)",
            nonBillable: "#ff9933",
            billable: "#3399ff",
            prediction: "#28a745",
            averagePrediction: "#d62828",
        };

    // ---- Maturity level & Escalation phase bands (derived from Status History) ----
    const statusHistory = (frm.doc.status_updates || [])
        .filter(row => row.date)
        .slice()
        .sort((a, b) => new Date(a.date) - new Date(b.date));

    function forwardFillByMonth(field) {
        let ptr = 0;
        let current = null;
        return categories.map(month => {
            while (ptr < statusHistory.length && statusHistory[ptr].date.slice(0, 7) <= month) {
                if (statusHistory[ptr][field]) current = statusHistory[ptr][field];
                ptr++;
            }
            return current;
        });
    }

    function buildRuns(values) {
        if (!values.length) return [];
        const runs = [];
        let start = 0;
        let currentVal = values[0];
        const END = Symbol('end');
        for (let idx = 1; idx <= values.length; idx++) {
            const val = idx < values.length ? values[idx] : END;
            if (val !== currentVal) {
                runs.push({ value: currentVal, from: start, to: idx - 1 });
                start = idx;
                currentVal = val;
            }
        }
        return runs;
    }

    const maturityLevelColors = {
        1: '231, 76, 60',   // Inception
        2: '243, 156, 18',  // Initial Development
        3: '241, 196, 15',  // Development
        4: '46, 204, 113',  // Go Live
        5: '52, 152, 219',  // Live Development
        6: '155, 89, 182',  // Support
    };

    function maturityLevelNumber(label) {
        const match = /^(\d+)/.exec(String(label || '').trim());
        return match ? parseInt(match[1], 10) : null;
    }

    function maturityShortLabel(label) {
        const match = /^\d+\s*-\s*([^.]+)/.exec(String(label || '').trim());
        return match ? match[1].trim() : (label || '');
    }

    const maturityBands = buildRuns(forwardFillByMonth('maturity_level'))
        .filter(run => run.value)
        .map(run => {
            const rgb = maturityLevelColors[maturityLevelNumber(run.value)] || '148, 163, 184';
            return {
                from: run.from - 0.5,
                to: run.to + 0.5,
                color: `rgba(${rgb}, ${isDarkTheme ? 0.28 : 0.18})`,
                zIndex: 0,
                label: {
                    text: maturityShortLabel(run.value),
                    style: { color: chartPalette.textColor, fontSize: '10px', fontWeight: '600' },
                    align: 'center',
                    verticalAlign: 'top',
                    y: 18
                }
            };
        });

    const escalationBands = buildRuns(forwardFillByMonth('status'))
        .filter(run => run.value === 'Escalated')
        .map(run => ({
            from: run.from - 0.5,
            to: run.to + 0.5,
            color: 'transparent',
            borderColor: isDarkTheme ? '#f70808' : '#aa0404',
            borderWidth: 2,
            zIndex: 5,
            label: {
                text: 'Escalated',
                style: { color: isDarkTheme ? '#f70808' : '#aa0404', fontSize: '10px', fontWeight: '600' },
                align: 'center',
                verticalAlign: 'top',
                y: 36
            }
        }));

    const phaseBands = [...maturityBands, ...escalationBands];

    // Function to render chart in any field
    function renderChartInField(fieldname, containerId, height = 400, width = 400, bands = []) {
        const wrapper = frm.fields_dict[fieldname].$wrapper;
        wrapper.empty();
        wrapper.append(`<div id="${containerId}" style="height:${height}px; width:${width}px;"></div>`);

        Highcharts.chart(containerId, {
            chart: {
                zoomType: 'xy',
                backgroundColor: 'transparent',
                style: { color: chartPalette.textColor }
            },
            title: {
                text: 'Billable vs Non-Billable Time with Prediction',
                style: { color: chartPalette.textColor, fontWeight: '600' }
            },
            xAxis: {
                categories,
                title: { text: 'Month', style: { color: chartPalette.mutedColor } },
                labels: { style: { color: chartPalette.mutedColor } },
                lineColor: chartPalette.borderColor,
                tickColor: chartPalette.borderColor,
                gridLineColor: chartPalette.borderColor,
                plotBands: bands
            },
            yAxis: {
                title: { text: 'Time (hrs)', style: { color: chartPalette.mutedColor } },
                labels: { style: { color: chartPalette.mutedColor } },
                gridLineColor: chartPalette.borderColor
            },
            tooltip: {
                shared: true,
                valueSuffix: ' hrs',
                backgroundColor: chartPalette.tooltipBg,
                borderColor: chartPalette.borderColor,
                style: { color: chartPalette.textColor }
            },
            legend: {
                itemStyle: {
                    fontSize: '10px',
                    color: chartPalette.textColor
                },
                itemHoverStyle: {
                    color: chartPalette.textColor
                },
                itemHiddenStyle: {
                    color: chartPalette.mutedColor
                }
            },
            plotOptions: {
                area: { stacking: 'normal', marker: { enabled: false } },
                line: { marker: { enabled: true, radius: 4 } }
            },
            series: [
                { name: 'Non-Billable Time', type: 'area', data: nonBillable, color: chartPalette.nonBillable },
                { name: 'Billable Time', type: 'area', data: billable, color: chartPalette.billable },
                {
                    name: 'Prediction', type: 'scatter', data: predictionPoints, color: chartPalette.prediction,
                    marker: { symbol: 'circle', radius: 5 },
                    tooltip: { pointFormat: '<span style="color:{series.color}">●</span> {series.name}: <b>{point.y} hrs</b><br/>' }
                },
                {
                    name: 'Average Prediction', type: 'line', data: averagePredictions, color: chartPalette.averagePrediction,
                    dashStyle: 'ShortDash',
                    marker: { enabled: true, symbol: 'diamond', radius: 4 },
                    tooltip: { pointFormat: '<span style="color:{series.color}">●</span> {series.name}: <b>{point.y:.2f} hrs</b><br/>' }
                }
            ]
        });
    }


    // Render in both fields (phase bands only on the main chart - the small one has no room for labels)
    renderChartInField('resource_chart', 'resource-planning-highchart-1', 400, 1000, phaseBands);
    renderChartInField('total_time_spend', 'resource-planning-highchart-2', 300, 300);

}



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
