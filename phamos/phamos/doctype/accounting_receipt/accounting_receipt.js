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

        // Fetch PDF (Mistral) - show review popup, then apply on Proceed
        if (!frm.doc.__islocal && frm.doc.attachment && frm.doc.attachment.toLowerCase().endsWith(".pdf")) {
            frm.add_custom_button(__("Fetch PDF"), function () {
                frm.dashboard.clear_headline();
                frappe.call({
                    method: "phamos.phamos.doctype.accounting_receipt.mistral_pdf.extract_from_pdf_for_review",
                    args: { accounting_receipt_name: frm.doc.name },
                    freeze: true,
                    callback: function (r) {
                        if (r.exc) {
                            frappe.msgprint({ title: __("Error"), indicator: "red", message: r.exc });
                            return;
                        }
                        var res = r.message;
                        if (!res.ok) {
                            var msg = res.reason || "Unknown";
                            if (res.message) msg += ": " + res.message;
                            if (res.hint) msg += " " + res.hint;
                            frappe.msgprint({ title: __("Extract failed"), indicator: "red", message: msg });
                            return;
                        }
                        if (!res.fields || res.fields.length === 0) {
                            frappe.msgprint({ title: __("No data"), indicator: "blue", message: __("No extractable data found in the PDF.") });
                            return;
                        }
                        frm.events.show_extract_review_dialog(frm, res.fields, res.extracted);
                    },
                });
            });
        }
    },

    show_extract_review_dialog: function (frm, fields, extracted) {
        // Resolve link values (by doc name or by supplier_name/company_name/cost_center_name) for auto-select
        var link_list = [];
        fields.forEach(function (f) {
            if (f.fieldtype === "Link" && f.options && f.value) {
                link_list.push({ fieldname: f.fieldname, doctype: f.options, value: f.value });
            }
        });
        frappe.call({
            method: "phamos.phamos.doctype.accounting_receipt.data_extract.resolve_link_values",
            args: { link_list: link_list },
            callback: function (r) {
                var resolved = (r.message || {});
                var missing_by_fieldname = {};
                var resolved_name_by_fieldname = {};
                link_list.forEach(function (lf) {
                    var name = resolved[lf.fieldname];
                    if (name) {
                        resolved_name_by_fieldname[lf.fieldname] = name;
                    } else {
                        missing_by_fieldname[lf.fieldname] = {
                            fieldname: lf.fieldname,
                            doctype: lf.doctype,
                            label: (function () {
                                var f = fields.filter(function (x) { return x.fieldname === lf.fieldname; })[0];
                                return f ? f.label : lf.doctype;
                            })(),
                            value: lf.value
                        };
                    }
                });
                frm.events._build_and_show_review_dialog(frm, fields, missing_by_fieldname, resolved_name_by_fieldname, extracted || {});
            }
        });
    },

    _build_and_show_review_dialog: function (frm, fields, missing_by_fieldname, resolved_name_by_fieldname, extracted) {
        extracted = extracted || {};
        resolved_name_by_fieldname = resolved_name_by_fieldname || {};
        // Hide from popup: Sent to DATEV, Uploaded by, Company, Payment Date; Project and Cost Center optional (no Create UI).
        fields = fields.filter(function (f) {
            if (f.fieldname === "sent_to_datev" || f.fieldname === "uploaded_by" || f.fieldname === "company" || f.fieldname === "payment_date") return false;
            return !(f.fieldtype === "Link" && (f.options === "Project" || f.options === "Cost Center"));
        });
        var dialog_fields = [];
        fields.forEach(function (f, idx) {
            var default_val = "";
            if (f.fieldtype === "Link" && f.options && missing_by_fieldname[f.fieldname]) {
                default_val = "";
            } else {
                default_val = (resolved_name_by_fieldname[f.fieldname] != null)
                    ? resolved_name_by_fieldname[f.fieldname]
                    : (f.value != null ? f.value : "");
            }
            var df = {
                fieldname: f.fieldname,
                label: f.label,
                fieldtype: f.fieldtype === "Text Editor" ? "Small Text" : (f.fieldtype === "Currency" ? "Float" : f.fieldtype),
                default: default_val
            };
            if (f.options) df.options = f.options;
            dialog_fields.push(df);
            // If this Link field's value does not exist, show extracted name + "Create" button only for required/supported types (Project, Cost Center are optional — no Create UI)
            var link_doctypes_with_create = ["Supplier", "Company"];
            if (f.fieldtype === "Link" && f.options && missing_by_fieldname[f.fieldname] && link_doctypes_with_create.indexOf(f.options) !== -1) {
                var lf = missing_by_fieldname[f.fieldname];
                var extracted_name = frappe.utils.escape_html(lf.value || "");
                var not_in_system = __("not in system");
                var btn_label = __("Create {0}", [__(lf.doctype)]);
                var html = "<div class=\"link-create-below\" style=\"margin-top:4px;font-size:12px;color:var(--text-muted);\">" +
                    "<span class=\"extracted-name\" title=\"" + not_in_system + "\">" + (extracted_name ? (__("Extracted: ") + "<strong>" + extracted_name + "</strong> — " + not_in_system) : not_in_system) + "</span>" +
                    " <button type=\"button\" class=\"btn btn-default btn-xs\" data-doctype=\"" + frappe.utils.escape_html(lf.doctype) + "\" data-fieldname=\"" + frappe.utils.escape_html(lf.fieldname) + "\">" + frappe.utils.escape_html(btn_label) + "</button>" +
                    "</div>";
                dialog_fields.push({ fieldtype: "HTML", fieldname: "create_btn_" + f.fieldname, options: html });
            }
            // Exactly two fields per row: Column Break after 1st, Section Break after 2nd
            if (idx % 2 === 0 && idx < fields.length - 1) {
                dialog_fields.push({ fieldtype: "Column Break", fieldname: "col_break_" + idx });
            } else if (idx % 2 === 1 && idx < fields.length - 1) {
                dialog_fields.push({ fieldtype: "Section Break", fieldname: "section_break_" + idx });
            }
        });
        var d = new frappe.ui.Dialog({
            title: __("Review Accounting Receipt"),
            size: "large",
            fields: dialog_fields,
            primary_action_label: __("Proceed"),
            primary_action: function () {
                var values = d.get_values();
                if (!values) return;
                d.hide();
                frappe.call({
                    method: "phamos.phamos.doctype.accounting_receipt.data_extract.apply_extracted_data",
                    args: {
                        accounting_receipt_name: frm.doc.name,
                        extracted_data: values
                    },
                    freeze: true,
                    callback: function (r) {
                        if (r.exc) {
                            frappe.msgprint({ title: __("Error"), indicator: "red", message: r.exc });
                            return;
                        }
                        var updated = r.message && r.message.updated ? r.message.updated : [];
                        var msg = updated.length
                            ? __("Updated fields: {0}", [updated.join(", ")])
                            : __("Data applied.");
                        frappe.show_alert({ message: msg, indicator: "green" }, 5);
                        frm.reload_doc();
                    }
                });
            },
            secondary_action_label: __("Cancel"),
            secondary_action: function () {
                d.hide();
            }
        });
        d.extracted = extracted;
        d.show();
        d.$wrapper.find(".link-create-below button[data-doctype]").on("click", function () {
            var doctype = $(this).attr("data-doctype");
            var fieldname = $(this).attr("data-fieldname");
            var ext = d.extracted || {};
            if (doctype === "Supplier") {
                frm.events._show_create_supplier_with_address_dialog(d, fieldname, ext);
            } else {
                var extracted_val = ext[fieldname] || "";
                var initial_doc = frm.events._prefill_doc_for_link_doctype(doctype, fieldname, extracted_val, ext);
                frappe.ui.form.make_quick_entry(doctype, function (doc) {
                    d.set_value(fieldname, doc.name);
                }, null, initial_doc || undefined, true);
            }
        });
    },

    _show_create_supplier_with_address_dialog: function (review_dialog, fieldname, extracted) {
        var ext = extracted || {};
        var get = function (k) { return (ext[k] != null && ext[k] !== "") ? ext[k] : ""; };
        var dialog_fields = [
            { fieldname: "supplier_name", fieldtype: "Data", label: __("Supplier Name"), reqd: 1, default: get("supplier") || get("supplier_name") },
            { fieldname: "tax_category", fieldtype: "Link", label: __("Tax Category"), options: "Tax Category", reqd: 1 },
            { fieldtype: "Section Break", fieldname: "addr_section", label: __("Address (optional)") },
            { fieldname: "address_line1", fieldtype: "Data", label: __("Address Line 1"), default: get("address_line1") },
            { fieldname: "address_line2", fieldtype: "Data", label: __("Address Line 2"), default: get("address_line2") },
            { fieldtype: "Column Break" },
            { fieldname: "city", fieldtype: "Data", label: __("City"), default: get("city") },
            { fieldname: "state", fieldtype: "Data", label: __("State"), default: get("state") },
            { fieldname: "country", fieldtype: "Link", label: __("Country"), options: "Country", default: get("country") },
            { fieldname: "pincode", fieldtype: "Data", label: __("Postal Code"), default: get("pincode") }
        ];
        var create_d = new frappe.ui.Dialog({
            title: __("Create Supplier"),
            size: "large",
            fields: dialog_fields,
            primary_action_label: __("Create"),
            primary_action: function () {
                var values = create_d.get_values();
                if (!values || !values.supplier_name) return;
                if (!values.tax_category) {
                    frappe.msgprint({ title: __("Required"), indicator: "orange", message: __("Tax Category is required.") });
                    return;
                }
                create_d.hide();
                var address_data = {
                    address_line1: values.address_line1,
                    address_line2: values.address_line2,
                    city: values.city,
                    state: values.state,
                    country: values.country,
                    pincode: values.pincode
                };
                frappe.call({
                    method: "phamos.phamos.doctype.accounting_receipt.data_extract.create_supplier_with_address",
                    args: { supplier_name: values.supplier_name, tax_category: values.tax_category, address_data: address_data },
                    freeze: true,
                    callback: function (r) {
                        if (r.exc) {
                            frappe.msgprint({ title: __("Error"), indicator: "red", message: r.exc });
                            return;
                        }
                        if (r.message) {
                            review_dialog.set_value(fieldname, r.message);
                            frappe.show_alert({ message: __("Supplier and address created"), indicator: "green" }, 4);
                        }
                    }
                });
            },
            secondary_action_label: __("Cancel"),
            secondary_action: function () { create_d.hide(); }
        });
        create_d.show();
    },

    _prefill_doc_for_link_doctype: function (doctype, fieldname, extracted_val, extracted) {
        var val = (extracted && extracted[fieldname]) || extracted_val || "";
        if (!val && extracted) {
            var k = fieldname === "supplier" ? "supplier_name" : fieldname;
            val = extracted[k] || extracted[fieldname] || "";
        }
        var initial = {};
        if (doctype === "Supplier") {
            initial.supplier_name = val;
        } else if (doctype === "Company") {
            initial.company_name = val;
        } else if (doctype === "Cost Center") {
            initial.cost_center_name = val;
        } else {
            initial.name = val;
        }
        return Object.keys(initial).length ? initial : null;
    },

    _has_address_data: function (extracted) {
        if (!extracted) return false;
        var keys = ["address_line1", "address_line2", "city", "state", "country", "pincode"];
        return keys.some(function (k) {
            var v = extracted[k];
            return v != null && String(v).trim() !== "";
        });
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
    },

    supplier: function(frm) {
        // Auto-fetch currency from supplier when supplier is selected or changed
        if (frm.doc.supplier) {
            frappe.call({
                method: "frappe.client.get_value",
                args: {
                    doctype: "Supplier",
                    filters: { name: frm.doc.supplier },
                    fieldname: ["default_currency"]
                },
                callback: function(r) {
                    if (r.message && r.message.default_currency) {
                        frm.set_value("currency", r.message.default_currency);
                    }
                }
            });
        }
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

