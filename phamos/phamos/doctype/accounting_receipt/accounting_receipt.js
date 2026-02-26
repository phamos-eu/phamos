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
                
                // Add DATEV Send button
                frm.events.add_datev_send_button(frm);
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
                        frm.events.show_extract_review_dialog(frm, res.fields, res.extracted, frm.doc.attachment);
                    },
                });
            });
        }
    },

    show_extract_review_dialog: function (frm, fields, extracted, pdf_url) {
        pdf_url = pdf_url || (frm && frm.doc && frm.doc.attachment) || "";
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
                frm.events._build_and_show_review_dialog(frm, fields, missing_by_fieldname, resolved_name_by_fieldname, extracted || {}, pdf_url);
            }
        });
    },

    _apply_review_dialog_layout: function (d) {
        if (!d.$wrapper || !d.$wrapper.hasClass("review-ar-dialog")) return;
        var $body = d.$wrapper.find(".modal-body");
        var $formLayout = $body.find(".form-layout");
        if (!$formLayout.length) return;
        var $formPage = $formLayout.find(".form-page");
        var $sectionBody = $formPage.find(".section-body");
        var $columns = $formPage.find(".form-column");
        if ($sectionBody.length === 0 || $columns.length < 2) return;
        var $content = d.$wrapper.find(".modal-content");
        var $bodyInner = $body.children().first();
        // Tall popup (88vh) so left column scrolls and PDF gets full height
        $content.css({ "height": "88vh", "max-height": "88vh", "min-height": "520px", "display": "flex", "flex-direction": "column" });
        $body.css({ "flex": "1 1 0", "min-height": "0", "overflow": "hidden", "display": "flex", "flex-direction": "column" });
        $bodyInner.css({ "flex": "1 1 0", "min-height": "0", "overflow": "hidden", "display": "flex", "flex-direction": "column" });
        $formLayout.css({ "flex": "1 1 0", "min-height": "0", "overflow": "hidden", "display": "flex", "flex-direction": "column" });
        $formPage.css({ "flex": "1 1 0", "min-height": "0", "overflow": "hidden", "display": "flex", "flex-direction": "column" });
        $formPage.find(".form-section, .row").css({ "flex": "1 1 0", "min-height": "0", "overflow": "hidden", "display": "flex", "flex-direction": "column" });
        // Force row height so both columns get a fixed height (left scrolls, right fills)
        var bodyHeight = "calc(88vh - 130px)";
        $sectionBody.css({
            "flex": "1 1 0",
            "min-height": "0",
            "height": bodyHeight,
            "max-height": bodyHeight,
            "overflow": "hidden",
            "display": "flex",
            "align-items": "stretch"
        });
        // Left: explicit max-height so overflow-y: auto always shows scrollbar when needed
        $columns.eq(0).css({
            "flex": "1 1 0",
            "min-height": "0",
            "max-height": bodyHeight,
            "min-width": "0",
            "overflow-y": "auto",
            "overflow-x": "hidden",
            "padding-right": "8px",
            "padding-bottom": "20px",
            "WebkitOverflowScrolling": "touch"
        });
        // Right: full height for PDF preview
        $columns.eq(1).css({
            "flex": "1 1 0",
            "min-height": "0",
            "height": bodyHeight,
            "min-width": "0",
            "overflow": "hidden",
            "display": "flex",
            "flex-direction": "column",
            "padding-bottom": "16px"
        });
        $columns.eq(1).find(".review-pdf-column").css({ "flex": "1", "min-height": "0", "display": "flex", "flex-direction": "column" });
        $columns.eq(1).find(".review-pdf-iframe").css({ "flex": "1", "min-height": "72vh", "height": "100%" });
    },

    _build_and_show_review_dialog: function (frm, fields, missing_by_fieldname, resolved_name_by_fieldname, extracted, pdf_url) {
        extracted = extracted || {};
        resolved_name_by_fieldname = resolved_name_by_fieldname || {};
        pdf_url = pdf_url || (frm && frm.doc && frm.doc.attachment) || "";
        // Hide from popup: Sent to DATEV, Uploaded by, Company, Payment Date; Project and Cost Center optional (no Create UI).
        fields = fields.filter(function (f) {
            if (f.fieldname === "sent_to_datev" || f.fieldname === "uploaded_by" || f.fieldname === "company" || f.fieldname === "payment_date") return false;
            return !(f.fieldtype === "Link" && (f.options === "Project" || f.options === "Cost Center"));
        });
        var dialog_fields = [];
        // Left column: section header + all extracted fields (single column, structured)
        dialog_fields.push({
            fieldtype: "HTML",
            fieldname: "extracted_header",
            options: "<div class=\"control-label\" style=\"font-weight: 600; margin-bottom: 10px; font-size: 12px; color: var(--text-color);\">" + __("Extracted content") + "</div>"
        });
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
        });
        // Column break: then right column = PDF preview
        dialog_fields.push({ fieldtype: "Column Break", fieldname: "pdf_review_col_break" });
        if (pdf_url && String(pdf_url).toLowerCase().endsWith(".pdf")) {
            var pdf_src = pdf_url.indexOf("/") === 0 ? (window.location.origin + pdf_url) : pdf_url;
            var pdf_html = "<div class=\"review-pdf-column\" style=\"display:flex;flex-direction:column;height:100%;min-height:72vh;\">" +
                "<label class=\"control-label\" style=\"font-weight: 600; margin-bottom: 8px; display: block; font-size: 12px; flex-shrink: 0;\">" + __("Attached PDF") + "</label>" +
                "<iframe src=\"" + frappe.utils.escape_html(pdf_src) + "\" type=\"application/pdf\" class=\"review-pdf-iframe\" " +
                "style=\"width:100%;flex:1;min-height:72vh;border:1px solid var(--border-color);border-radius: 6px;background:#f5f5f5;\"></iframe>" +
                "</div>";
            dialog_fields.push({ fieldtype: "HTML", fieldname: "pdf_preview_review", options: pdf_html });
        }
        var d = new frappe.ui.Dialog({
            title: __("Review Accounting Receipt"),
            size: "extra-large",
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
        d.$wrapper.addClass("review-ar-dialog");
        d.show();
        // Apply layout after form is rendered (delay so DOM is ready)
        setTimeout(function () {
            frm.events._apply_review_dialog_layout(d);
        }, 350);
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
                        // When currency changes due to supplier, update exchange rate and base sum
                        frm.events.update_exchange_and_base_sum(frm);
                    }
                }
            });
        }
    },

    posting_date: function(frm) {
        // Recompute exchange rate and base sum when transaction date changes
        frm.events.update_exchange_and_base_sum(frm);
    },

    currency: function(frm) {
        // Recompute when currency changes manually
        frm.events.update_exchange_and_base_sum(frm);
    },

    sum: function(frm) {
        // Recompute base sum when original sum changes
        frm.events.update_exchange_and_base_sum(frm);
    },

    async update_exchange_and_base_sum(frm) {
        // Determine company currency
        const company = frm.doc.company || frappe.defaults.get_user_default("company");
        if (!company || !frm.doc.currency) {
            return;
        }

        const company_currency = await frappe.call({
            method: "frappe.client.get_value",
            args: {
                doctype: "Company",
                filters: { name: company },
                fieldname: ["default_currency"]
            }
        }).then(r => (r.message && r.message.default_currency) ? r.message.default_currency : null);

        if (!company_currency) {
            return;
        }

        // If same currency, conversion rate is 1 and base sum equals sum
        if (company_currency === frm.doc.currency) {
            if (frm.doc.conversion_rate !== 1) {
                frm.set_value("conversion_rate", 1);
            }
            if (frm.doc.sum) {
                frm.set_value("sum_in_company_currency", frm.doc.sum);
            }
            return;
        }

        // Fetch exchange rate for the posting date
        const rate = await frappe.call({
            method: "erpnext.setup.utils.get_exchange_rate",
            args: {
                from_currency: frm.doc.currency,
                to_currency: company_currency,
                transaction_date: frm.doc.posting_date || frappe.datetime.get_today()
            }
        }).then(r => r.message || null);

        if (rate) {
            // Update conversion_rate and computed base sum (EUR)
            frm.set_value("conversion_rate", rate);
            if (frm.doc.sum) {
                frm.set_value("sum_in_company_currency", flt(frm.doc.sum) * flt(rate));
            }
        }
    },

    add_datev_send_button: function(frm) {
        // Only show button if document is submitted
        if (frm.doc.docstatus !== 1) {
            return;
        }
        
        // Determine button label based on whether already sent
        const button_label = frm.doc.sent_to_datev ? __("Resend to DATEV") : __("Send to DATEV");
        
        frm.add_custom_button(button_label, function() {
            frm.events.show_datev_send_dialog(frm);
        });
    },

    show_datev_send_dialog: function(frm) {
        // Fetch info needed for confirmation dialog
        frappe.call({
            method: "phamos.phamos.doctype.accounting_receipt.accounting_receipt.get_datev_send_info",
            args: { accounting_receipt_name: frm.doc.name },
            callback: function(r) {
                if (!r.message || !r.message.ok) {
                    frappe.msgprint({
                        title: __("Error"),
                        indicator: "red",
                        message: r.message ? r.message.message : __("Failed to get DATEV send information")
                    });
                    return;
                }
                
                const info = r.message;
                
                // Validate recipient
                if (!info.recipient) {
                    frappe.msgprint({
                        title: __("Configuration Error"),
                        indicator: "red",
                        message: __("DATEV recipient email is not configured. Please contact system administrator.")
                    });
                    return;
                }
                
                // Validate PDF
                if (!info.pdf_name || !info.pdf_url) {
                    frappe.msgprint({
                        title: __("Missing PDF"),
                        indicator: "red",
                        message: __("PDF attachment is missing. Please attach a PDF file using:<br><br>• The <strong>Attachment</strong> field in the form, OR<br>• The <strong>Attachments</strong> sidebar (📎 icon)<br><br>Then try again.")
                    });
                    return;
                }
                
                // Build dialog message
                let dialog_message = `
                    <div style="margin-bottom: 15px;">
                        <p><strong>${__("Recipient")}:</strong> ${info.recipient}</p>
                        <p><strong>${__("PDF File")}:</strong> ${info.pdf_name}</p>
                    </div>
                `;
                
                if (info.already_sent) {
                    dialog_message += `
                        <div style="padding: 10px; background-color: #fff3cd; border: 1px solid #ffc107; border-radius: 4px; margin-bottom: 15px;">
                            <p style="margin: 0; color: #856404;">
                                <strong>${__("Warning")}:</strong> ${__("This document was already sent on")} 
                                ${frappe.datetime.str_to_user(info.sent_at)} ${__("by")} ${info.sent_by}.
                            </p>
                            ${info.email_queue_ref ? `<p style="margin: 5px 0 0 0; font-size: 12px; color: #856404;">
                                ${__("Email Queue")}: ${info.email_queue_ref}
                            </p>` : ''}
                        </div>
                    `;
                }
                
                dialog_message += `<p>${__("Are you sure you want to send this document to DATEV?")}</p>`;
                
                // Show confirmation dialog
                frappe.confirm(
                    dialog_message,
                    function() {
                        // User confirmed - send email
                        frm.events.send_to_datev_now(frm);
                    },
                    function() {
                        // User cancelled
                    }
                );
            }
        });
    },

    send_to_datev_now: function(frm) {
        frappe.call({
            method: "phamos.phamos.doctype.accounting_receipt.accounting_receipt.send_to_datev",
            args: { accounting_receipt_name: frm.doc.name },
            freeze: true,
            freeze_message: __("Sending to DATEV..."),
            callback: function(r) {
                if (!r.message) {
                    frappe.msgprint({
                        title: __("Error"),
                        indicator: "red",
                        message: __("No response from server")
                    });
                    return;
                }
                
                const result = r.message;
                
                if (result.ok) {
                    // Success
                    frappe.show_alert({
                        message: result.message || __("Email sent successfully"),
                        indicator: "green"
                    }, 5);
                    
                    // Reload form to show updated fields
                    frm.reload_doc();
                } else {
                    // Error
                    frappe.msgprint({
                        title: __("Failed to Send"),
                        indicator: "red",
                        message: result.message || __("Unknown error occurred")
                    });
                }
            }
        });
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
