// Copyright (c) 2026, phamos.eu and contributors
// For license information, please see license.txt

frappe.ui.form.on("Lead Data Import", {
    refresh(frm) {
        if (frm.doc.status === "Ready") {
            frm.add_custom_button(__("Re-Extract"), () => {
                frappe.call({
                    method: "phamos.phamos.doctype.lead_data_import.lead_data_import.re_enrich_incomplete",
                    args: { lead_data_import_name: frm.doc.name },
                    callback(r) {
                        if (r.message && r.message.ok) {
                            frappe.msgprint(r.message.message);
                            frm.reload_doc();
                        }
                    }
                });
            });
        }
        _setup_extract_button(frm);
        _show_summary(frm);

        // If a background job is running, keep polling until it finishes
        if (frm.doc.status === "Processing") {
            _start_polling(frm);
        }
    },

    input_type(frm) {
        _toggle_source_fields(frm);
    },

    onload(frm) {
        _toggle_source_fields(frm);
    },
});

function _setup_extract_button(frm) {
    frm.add_custom_button(__("Extract Leads"), () => {
        // Validate required fields before saving + calling
        if (frm.doc.input_type === "URL" && !frm.doc.source_url) {
            frappe.msgprint(__("Please enter a Source URL before extracting."));
            return;
        }
        if ((frm.doc.input_type === "Screenshot" || frm.doc.input_type === "PDF") && !frm.doc.upload_file) {
            frappe.msgprint(__("Please upload a file before extracting."));
            return;
        }

        if (_should_preview_screenshot(frm)) {
            _extract_screenshot_with_preview(frm);
            return;
        }

        frappe.confirm(
            __("This will clear any existing extracted leads and start fresh. Continue?"),
            () => {
                // Save first, then trigger extraction
                frm.save()
                    .then(() => {
                        frappe.call({
                            method: "phamos.phamos.doctype.lead_data_import.lead_data_import.extract_leads",
                            args: { lead_data_import_name: frm.doc.name },
                            freeze: true,
                            freeze_message: __("Starting extraction..."),
                            callback(r) {
                                if (r.message && r.message.ok) {
                                    frappe.show_alert({
                                        message: __("Extraction started. The page will refresh automatically."),
                                        indicator: "blue",
                                    });
                                    frm.reload_doc();
                                    _start_polling(frm);
                                } else {
                                    frappe.msgprint({
                                        title: __("Error"),
                                        message: (r.message && r.message.message) || __("Failed to start extraction."),
                                        indicator: "red",
                                    });
                                }
                            },
                        });
                    });
            }
        );
    }).addClass("btn-primary");
}

function _extract_screenshot_with_preview(frm) {
    _save_then(frm, () => {
        frappe.call({
            method: "phamos.phamos.doctype.lead_data_import.lead_data_import.preview_screenshot_leads",
            args: { lead_data_import_name: frm.doc.name },
            freeze: true,
            freeze_message: __("Reading screenshot..."),
            callback(r) {
                if (!r.message || !r.message.ok) {
                    frappe.msgprint({
                        title: __("Error"),
                        message: (r.message && r.message.message) || __("Could not extract screenshot data."),
                        indicator: "red",
                    });
                    return;
                }
                _show_screenshot_preview_dialog(frm, r.message);
            },
        });
    });
}

function _should_preview_screenshot(frm) {
    const input_type = frm.doc.input_type || "";
    const upload_file = frm.doc.upload_file || "";
    return input_type === "Screenshot" || /\.(png|jpe?g|webp)$/i.test(upload_file);
}

function _save_then(frm, action) {
    const run = () => {
        try {
            action();
        } catch (e) {
            frappe.msgprint({
                title: __("Error"),
                message: e && e.message ? e.message : String(e),
                indicator: "red",
            });
        }
    };

    if (!frm.is_new() && !frm.is_dirty()) {
        run();
        return;
    }

    const save_result = frm.save();
    if (save_result && typeof save_result.then === "function") {
        save_result.then(run).catch((e) => {
            frappe.msgprint({
                title: __("Could not save"),
                message: e && e.message ? e.message : __("Please fix the form errors and try again."),
                indicator: "red",
            });
        });
    } else {
        setTimeout(run, 500);
    }
}

function _show_screenshot_preview_dialog(frm, preview) {
    const leads = preview.leads || [];
    const image_url = preview.image_url || "";

    if (leads.length <= 1) {
        _show_single_lead_preview_dialog(frm, preview, leads[0] || {});
        return;
    }

    const dialog = new frappe.ui.Dialog({
        title: __("Review Screenshot Extraction"),
        size: "extra-large",
        fields: [
            {
                fieldname: "preview_html",
                fieldtype: "HTML",
                options:
                    "<div style=\"display:grid;grid-template-columns:1fr 1fr;gap:16px;\">" +
                    "<div><label class=\"control-label\">" + __("Screenshot") + "</label>" +
                    "<img src=\"" + _escape_html(image_url) + "\" style=\"width:100%;max-height:520px;object-fit:contain;border:1px solid var(--border-color);border-radius:6px;background:#f8f8f8;\" /></div>" +
                    "<div><label class=\"control-label\">" + __("Extracted Data") + "</label>" +
                    "<pre style=\"white-space:pre-wrap;max-height:520px;overflow:auto;border:1px solid var(--border-color);border-radius:6px;padding:12px;background:#f8f8f8;\">" +
                    _escape_html(preview.lead_data_text || "") +
                    "</pre></div></div>",
            },
            {
                fieldname: "leads_json",
                fieldtype: "Code",
                label: __("Editable Lead JSON"),
                options: "JSON",
                default: JSON.stringify(leads, null, 2),
            },
        ],
        primary_action_label: __("Accept and Create Lead Data"),
        primary_action(values) {
            _create_leads_from_preview(frm, dialog, values.leads_json);
        },
        secondary_action_label: __("Cancel"),
        secondary_action() {
            dialog.hide();
        },
    });

    dialog.show();
}

function _show_single_lead_preview_dialog(frm, preview, lead) {
    const image_url = preview.image_url || "";
    const dialog = new frappe.ui.Dialog({
        title: __("Review Screenshot Extraction"),
        size: "extra-large",
        fields: [
            { fieldtype: "Section Break", label: __("Extracted Lead Data") },
            { fieldname: "company_name", fieldtype: "Data", label: __("Company Name"), default: lead.company_name || "" },
            { fieldname: "website", fieldtype: "Data", label: __("Website"), default: lead.website || "" },
            { fieldname: "emails", fieldtype: "Small Text", label: __("Emails"), default: (lead.emails || []).join("\n") },
            { fieldname: "phones", fieldtype: "Small Text", label: __("Phones"), default: (lead.phones || []).join("\n") },
            { fieldname: "contact_persons", fieldtype: "Small Text", label: __("Contact Persons"), default: (lead.contact_persons || []).join("\n") },
            { fieldname: "addresses", fieldtype: "Small Text", label: __("Addresses"), default: (lead.addresses || []).join("\n") },
            { fieldname: "job_title", fieldtype: "Data", label: __("Job Title"), default: lead.job_title || "" },
            { fieldtype: "Column Break" },
            {
                fieldname: "image_preview",
                fieldtype: "HTML",
                options:
                    "<label class=\"control-label\">" + __("Screenshot") + "</label>" +
                    "<img src=\"" + _escape_html(image_url) + "\" style=\"width:100%;max-height:70vh;object-fit:contain;border:1px solid var(--border-color);border-radius:6px;background:#f8f8f8;\" />",
            },
        ],
        primary_action_label: __("Accept and Create Lead Data"),
        primary_action(values) {
            if (!values) return;
            const payload = [{
                company_name: values.company_name || "",
                website: values.website || "",
                emails: _split_lines(values.emails),
                phones: _split_lines(values.phones),
                contact_persons: _split_lines(values.contact_persons),
                addresses: _split_multiline(values.addresses),
                job_title: values.job_title || "",
                source_attachment: image_url,
            }];
            _create_leads_from_preview(frm, dialog, JSON.stringify(payload));
        },
        secondary_action_label: __("Cancel"),
        secondary_action() {
            dialog.hide();
        },
    });

    dialog.show();
}

function _create_leads_from_preview(frm, dialog, leads_json) {
    frappe.call({
        method: "phamos.phamos.doctype.lead_data_import.lead_data_import.create_leads_from_preview",
        args: {
            lead_data_import_name: frm.doc.name,
            leads_json: leads_json,
            replace_existing: 1,
        },
        freeze: true,
        freeze_message: __("Creating lead data..."),
        callback(r) {
            if (r.message && r.message.ok) {
                dialog.hide();
                frappe.msgprint(r.message.message);
                frm.reload_doc();
            }
        },
    });
}

function _split_lines(value) {
    return String(value || "")
        .split(/\n|,/)
        .map((item) => item.trim())
        .filter(Boolean);
}

function _split_multiline(value) {
    return String(value || "")
        .split(/\n/)
        .map((item) => item.trim())
        .filter(Boolean);
}

function _escape_html(value) {
    return String(value || "")
        .replace(/&/g, "&amp;")
        .replace(/</g, "&lt;")
        .replace(/>/g, "&gt;")
        .replace(/"/g, "&quot;")
        .replace(/'/g, "&#039;");
}

let _poll_timer = null;

function _start_polling(frm) {
    if (_poll_timer) return; // Already polling

    _poll_timer = setInterval(() => {
        // Stop polling if the form is closed or navigated away
        if (!frm.doc || !frm.doc.name) {
            clearInterval(_poll_timer);
            _poll_timer = null;
            return;
        }

        frappe.db.get_value("Lead Data Import", frm.doc.name, ["status", "status_log"])
            .then((r) => {
                const status = (r.message || {}).status;
                const status_log = (r.message || {}).status_log;

                // Update log in real time without full reload
                if (status_log && status_log !== frm.doc.status_log) {
                    frm.set_value("status_log", status_log);
                }

                // Stop polling once extraction is done
                if (status !== "Processing") {
                    clearInterval(_poll_timer);
                    _poll_timer = null;
                    frm.reload_doc();
                    frappe.show_alert({
                        message: __("Extraction complete!"),
                        indicator: "green",
                    });
                }
            });
    }, 3000); // Poll every 3 seconds
}

// UI helpers

function _toggle_source_fields(frm) {
    const is_url = frm.doc.input_type === "URL";
    const is_file = frm.doc.input_type === "Screenshot" || frm.doc.input_type === "PDF";

    frm.toggle_display("source_url", is_url);
    frm.toggle_display("upload_file", is_file);
}

function _show_summary(frm) {
    const rows = frm.doc.leads_preview || [];
    if (!rows.length) return;

    const total = rows.length;
    const created = rows.filter((r) => r.lead_status === "Created").length;
    const pending = rows.filter((r) => r.lead_status === "Pending").length;
    const errors = rows.filter((r) => r.lead_status === "Error").length;

    let color = "blue";
    if (created === total) color = "green";
    if (errors > 0) color = "orange";

    frm.dashboard.add_indicator(
        __("{0} total | {1} pending | {2} created | {3} errors", [total, pending, created, errors]),
        color
    );
}
