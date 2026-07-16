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
            add_row_to_sales_order(frm)
                frappe.call({
                    method: "phamos.phamos.doctype.implementation.implementation.get_financial_history",
                    args: { 'name': frm.doc.name, 'customer': frm.doc.customer },
                    callback: function (r) {
                        if (r.message) {
                            frm.set_value('sales_order_total_hrs', r.message['sales_order_qty'])
                            set_parent_delivered_total_hrs_from_child(frm, r.message['dn_qty'])
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
        frm.trigger("render_auto_email_reports_section");
        frm.trigger("render_gitlab_projects_section");
        frm.trigger("render_gitlab_issues_section");
        frm.trigger("render_gitlab_milestones_section");

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

        // Sort resource_planning_prediction by date (descending - newest first)
        if (frm.doc.resource_planning_prediction && frm.doc.resource_planning_prediction.length > 0) {
            frm.doc.resource_planning_prediction.sort((a, b) => {
                let dateA = a.date ? new Date(a.date) : new Date(0);
                let dateB = b.date ? new Date(b.date) : new Date(0);
                return dateB - dateA; // Descending order (newest first)
            });
            frm.refresh_field('resource_planning_prediction');
        }
        
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
            render_module_chart(frm, 'radar-chart-1');
            render_module_chart(frm, 'radar-chart-2');
        });
        // radar chart ends
            frappe.call({
                method: "phamos.phamos.doctype.implementation.implementation.get_financial_history",
                args: { 'customer': frm.doc.customer, 'name': frm.doc.name },
                callback: function (r) {
                    if (r.message) {
                        const delivered_total_hrs = get_child_delivered_total_hrs(frm, r.message['dn_qty']);
                        set_parent_delivered_total_hrs_from_child(frm, r.message['dn_qty']);
                        if (r.message['sales_order_qty'] < r.message['timesheet_hrs']) {
                            let string1 = "TS Hrs exceeding Open SO Hrs"
                            let remaining_hrs = Math.abs(r.message['remaining_hrs']).toString();
                            let string2 = "TH"
                            let warning_label = r.message['sales_order_qty'] < r.message['timesheet_hrs'] ? '⚠️' + string1 : '';

                            let labels = ['DN Hrs', 'TS Hrs', warning_label];
                            let values = [delivered_total_hrs, r.message['timesheet_hrs'], 0];

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
                            let values = [delivered_total_hrs, r.message['timesheet_hrs'], r.message['remaining_hrs']];

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
                            let values = [delivered_total_hrs, r.message['timesheet_hrs'], r.message['remaining_hrs']];

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
            if (r.message) {
                // clear existing child table
                frm.clear_table("auto_email_report_record");

                r.message.forEach(function(row) {
                    let child = frm.add_child("auto_email_report_record");
                    child.recipients = row.recipient;
                    child.templates = row.template;
                    child.frequency = row.frequency;
                });

                frm.refresh_field("auto_email_report_record");

            }
        }
    });
}
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
            fields: ["name", "status", "total_qty", "customer_name"],
            order_by: "transaction_date desc",
        },
        callback: function (response) {
            if (response.message.length > 0) {
                frm.clear_table("sales_order_status_information"); // Clear existing data

                response.message.forEach(order => {
                    let row = frm.add_child("sales_order_status_information");
                    row.sales_order = order.name;
                    row.so_title = order.customer_name;
                    row.total_hrs = order.total_qty;
                    row.status = order.status;
                });
                frm.refresh_field("sales_order_status_information"); // Refresh child table
                set_parent_delivered_total_hrs_from_child(frm);
            }
        }
    });
}

function get_child_delivered_total_hrs(frm, fallback = 0) {
    const rows = frm.doc.sales_order_status_information || [];
    const total = rows.reduce((sum, row) => sum + flt(row.delivered_total_hrs), 0);
    return rows.length ? total : flt(fallback);
}

function set_parent_delivered_total_hrs_from_child(frm, fallback = 0) {
    frm.set_value("delivered_total_hrs", get_child_delivered_total_hrs(frm, fallback));
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
                        set_parent_delivered_total_hrs_from_child(frm, r.message['dn_qty'])
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





