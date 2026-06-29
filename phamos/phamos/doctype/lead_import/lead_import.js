// Copyright (c) 2026, phamos.eu and contributors
// For license information, please see license.txt

frappe.ui.form.on("Lead Import", {
    refresh(frm) {
        if (frm.doc.status === "Ready") {
            frm.add_custom_button(__("Re-Extract"), () => {
                frappe.call({
                    method: "phamos.phamos.doctype.lead_import.lead_import.re_enrich_incomplete",
                    args: { lead_import_name: frm.doc.name },
                    callback(r) {
                        if (r.message?.ok) {
                            frappe.msgprint(r.message.message);
                            frm.reload_doc();
                        }
                    }
                });
            })
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
            console.log("Extract button clicked");

        // Validate required fields before saving + calling
        if (frm.doc.input_type === "URL" && !frm.doc.source_url) {
            frappe.msgprint(__("Please enter a Source URL before extracting."));
            return;
        }
        if ((frm.doc.input_type === "Screenshot" || frm.doc.input_type === "PDF") && !frm.doc.upload_file) {
            frappe.msgprint(__("Please upload a file before extracting."));
            return;
        }

        frappe.confirm(
            __("This will clear any existing extracted leads and start fresh. Continue?"),
            () => {
                // Save first, then trigger extraction
                frm.save()
                    .then(() => {
                    });
                    frappe.call({
                        method: "phamos.phamos.doctype.lead_import.lead_import.extract_leads",
                        args: { lead_import_name: frm.doc.name },
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
                                    message: r.message?.message || __("Failed to start extraction."),
                                    indicator: "red",
                                });
                            }
                        },
                    });
            }
        );
    }).addClass("btn-primary");
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

        frappe.db.get_value("Lead Import", frm.doc.name, ["status", "status_log"])
            .then((r) => {
                const { status, status_log } = r.message || {};

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
