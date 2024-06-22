// Copyright (c) 2023, phamos.eu and contributors
// For license information, please see license.txt

frappe.ui.form.on("Accounting Receipt", {
    refresh(frm) {
        if (frm.doc.docstatus===0 && !frm.doc.__islocal) {
            frm.add_custom_button(__("Fetch Timesheet"), function() {
                let d = new frappe.ui.Dialog({
                    title: __("Fetch Timesheet"),
                    fields: [
                        {
                            "label" : __("From"),
                            "fieldname": "from_time",
                            "fieldtype": "Date",
                            "reqd": 1,
                        },
                        {
                            fieldtype: "Column Break",
                            fieldname: "col_break_1",
                        },
                        {
                            "label" : __("To"),
                            "fieldname": "to_time",
                            "fieldtype": "Date",
                            "reqd": 1,
                        },
                        {
                            "label" : __("Project"),
                            "fieldname": "project",
                            "fieldtype": "Link",
                            "options": "Project"
                        },
                    ],
                    primary_action: function() {
                        const data = d.get_values();
                        frm.events.add_timesheet_data(frm, {
                            from_time: data.from_time,
                            to_time: data.to_time,
                            project: data.project
                        });
                        d.hide();
                    },
                    primary_action_label: __("Get Timesheets")
                });
                d.show();
            });
        }
        if (frm.doc.docstatus === 1) {
                frm.add_custom_button(
                    __("Purchase Invoice"),
                    function () {
                        frm.events.make_purchase_invoice(frm);
                    }, __("Create")
                );
                frm.page.set_inner_btn_group_as_primary(__("Create"));
        }

        // Hide PDF Preview if no attachment available or display it onload of document 
        frm.toggle_display("pdf_preview", false);
        frm.trigger("attachment");
    },

    attachment: function (frm) {
        /* on attachment of PDF document in attachment field in doclevel
            system will generate a preview of the attached document
        */
        let $preview = "";
        let file_extension = frm.events.getFileExtension(frm.doc.attachment);

        if (file_extension === "pdf") {
            $preview = $(`<div class="img_preview">
                <h2 style="
                        font-size: var(--text-lg);   
                        font-weight: var(--weight-semibold);
                        letter-spacing: .015em;
                        color: var(--text-color);
                        cursor: default;"> PDF Preview</h2>
				<object style="background:#323639;" width="100%">
					<embed
						style="background:#323639;"
						width="100%"
						height="600px"
						src="${frappe.utils.escape_html(frm.doc.attachment)}" type="application/pdf"
					>
				</object>
			</div>`);
        }

        if ($preview) {
            frm.toggle_display("pdf_preview", true);
            frm.get_field("pdf_preview").$wrapper.html($preview);
        }
    },

    getFileExtension: function (filename) {
        // Get extension of the file
        return filename.split('.').pop();
    },

    make_purchase_invoice: function (frm) {
        return frappe.call({
            method: "make_purchase_invoice",
            doc: frm.doc,
            callback: function (r) {
                var doc = frappe.model.sync(r.message);
                frappe.set_route("Form", doc[0].doctype, doc[0].name);
            },
        });
    },
    async add_timesheet_data(frm, kwargs) {
        const timesheets = await frm.events.get_timesheet_data(frm, kwargs);
        return frm.events.set_timesheet_data(frm, timesheets);
    },

    async get_timesheet_data(frm, kwargs) {
        return frappe.call({
            method: "erpnext.projects.doctype.timesheet.timesheet.get_projectwise_timesheet_data",
            args: kwargs
        }).then(r => {
            if (!r.exc && r.message.length > 0) {
                return r.message
            } else {
                return []
            }
        });
    },

    set_timesheet_data: function(frm, timesheets) {
        // Set timesheet data for the selected timeframe and project, avoid duplicates
        timesheets.forEach(async (timesheet) => {
            const timesheet_exists = frm.doc.timesheets.find(i => i.time_sheet === timesheet.time_sheet);
            if (!timesheet_exists) {
                if (frm.doc.currency != timesheet.currency) {
                    const exchange_rate = await frm.events.get_exchange_rate(
                        frm, timesheet.currency, frm.doc.currency
                    )
                    frm.events.append_time_log(frm, timesheet, exchange_rate)
                } else {
                    frm.events.append_time_log(frm, timesheet, 1.0);
                }
            }
        });
        frm.refresh_field("timesheets");
        frm.trigger("calculate_timesheet_totals");
    },

    async get_exchange_rate(frm, from_currency, to_currency) {
        if (
            frm.exchange_rates
            && frm.exchange_rates[from_currency]
            && frm.exchange_rates[from_currency][to_currency]
        ) {
            return frm.exchange_rates[from_currency][to_currency];
        }

        return frappe.call({
            method: "erpnext.setup.utils.get_exchange_rate",
            args: {
                from_currency,
                to_currency
            },
            callback: function(r) {
                if (r.message) {
                    // cache exchange rates
                    frm.exchange_rates = frm.exchange_rates || {};
                    frm.exchange_rates[from_currency] = frm.exchange_rates[from_currency] || {};
                    frm.exchange_rates[from_currency][to_currency] = r.message;
                }
            }
        });
    },

    append_time_log: function(frm, time_log, exchange_rate) {
        const row = frm.add_child("timesheets");
        row.activity_type = time_log.activity_type;
        row.description = time_log.description;
        row.time_sheet = time_log.time_sheet;
        row.from_time = time_log.from_time;
        row.to_time = time_log.to_time;
        row.billing_hours = time_log.billing_hours;
        row.billing_amount = flt(time_log.billing_amount) * flt(exchange_rate);
        row.timesheet_detail = time_log.name;
        row.project_name = time_log.project_name;
    },

    calculate_timesheet_totals: function(frm) {
        // Calculate and set values for billing amount and billing hour
        frm.set_value("total_billing_amount",
            frm.doc.timesheets.reduce((a, b) => a + (b["billing_amount"] || 0.0), 0.0));
        frm.set_value("total_billing_hours",
            frm.doc.timesheets.reduce((a, b) => a + (b["billing_hours"] || 0.0), 0.0));
    }
});

frappe.ui.form.on("Accounting Receipt Timesheet", {
    // if timesheet is removed, recalculate values
    timesheets_remove(frm) {
        frm.trigger("calculate_timesheet_totals");
    }
});

var set_timesheet_detail_rate = function(cdt, cdn, currency, timelog) {
    // set billing amount on timesheet child table
    frappe.call({
        method: "erpnext.projects.doctype.timesheet.timesheet.get_timesheet_detail_rate",
        args: {
            timelog: timelog,
            currency: currency
        },
        callback: function(r) {
            if (!r.exc && r.message) {
                frappe.model.set_value(cdt, cdn, 'billing_amount', r.message);
            }
        }
    });
}

