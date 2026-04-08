// Copyright (c) 2023, phamos.eu and contributors
// For license information, please see license.txt

frappe.ui.form.on('phamos Settings', {
    validate: function(frm) {
        // Filter out the enabled channels
        let enabled_channels = (frm.doc.mattermost_channel || []).filter(
            (channel) => channel.enable
        );

        // Check if more than one channel is enabled
        if (enabled_channels.length > 1) {
            frappe.msgprint(__('Only one Mattermost Channel can be enabled at a time.'));
            // Prevent the form from being saved
            frappe.validated = false;
        }
    },
    onload: function(frm) {
		// Set year options dynamically: last year, current year, next 2 years
		const currentYear = new Date().getFullYear();
		const years = [
			currentYear - 1,
			currentYear,
			currentYear + 1,
			currentYear + 2
		];
		frm.set_df_property('year', 'options', years.join('\n'));
	},
	refresh: function (frm) {
		const d = new Date();
		const months = [
			"January",
			"February",
			"March",
			"April",
			"May",
			"June",
			"July",
			"August",
			"September",
			"October",
			"November",
			"December",
		];
		const yStr = String(d.getFullYear());
		const curMonth = months[d.getMonth()];
		// Single DocType: is_new() is never true — default only when fields are empty.
		if (!frm.doc.month) {
			frm.set_value("month", curMonth);
		}
		if (!frm.doc.year) {
			frm.set_value("year", yStr);
		} else if (typeof frm.doc.year === "number") {
			frm.set_value("year", String(frm.doc.year));
		}
	},
	execute_scheduled_job: function (frm) {
		if (!frm.doc.month || !frm.doc.year) {
			frappe.msgprint(__("Please select Month and Year"));
			return;
		}
		frappe.confirm(
			__(
				"Create Monthly Implementation Summaries for open Implementations that have timesheets in {0} {1}?",
				[frm.doc.month, frm.doc.year]
			),
			() => {
				frappe.call({
					method:
						"phamos.phamos.doctype.monthly_implementation_summary.create_monthly_implementation_summaries.run_manual_mis_creation",
					args: {
						month: frm.doc.month,
						year: String(frm.doc.year),
					},
					freeze: true,
					freeze_message: __("Creating Monthly Implementation Summaries..."),
					callback: function (r) {
						if (r.exc) {
							return;
						}
						const m = r.message || {};
						let detailBlock = "";
						if (m.details && m.details.length) {
							const esc =
								frappe.utils && frappe.utils.escape_html
									? frappe.utils.escape_html
									: function (t) {
											const h = document.createElement("div");
											h.textContent = t == null ? "" : String(t);
											return h.innerHTML;
									  };
							const chunks = m.details.map(function (d) {
								const lines = [];
								if (d.implementation) {
									lines.push(
										"<strong>" +
											esc(__("Implementation")) +
											":</strong> " +
											esc(d.implementation)
									);
								}
								if (d.why_skipped) {
									lines.push(esc(d.why_skipped));
								}
								if (d.blocking_mis && d.blocking_mis.length) {
									const blk = d.blocking_mis
										.map(function (b) {
											return (
												esc(b.name) +
												" (" +
												esc(b.status != null ? b.status : b.docstatus) +
												")"
											);
										})
										.join(", ");
									lines.push(
										"<strong>" +
											esc(__("Blocking MIS")) +
											":</strong> " +
											blk
									);
								}
								if (!lines.length) {
									lines.push(esc(JSON.stringify(d)));
								}
								return '<div style="margin-bottom:12px">' + lines.join("<br>") + "</div>";
							});
							detailBlock =
								"<br><br><strong>" +
								__("Why implementations were skipped (if any)") +
								"</strong>" +
								'<div style="font-size:13px;max-height:320px;overflow:auto;margin-top:8px">' +
								chunks.join("") +
								"</div>";
						}
						frappe.msgprint({
							title: __("Job finished"),
							message: __(
								"Created: {0}<br>Skipped (already exists): {1}<br>Skipped (no timesheets in period): {2}<br>Errors: {3}<br><br>Server log: <code>logs/phamos.mis_creation.log</code> (under your site folder)",
								[
									m.created || 0,
									m.skipped_existing || 0,
									m.skipped_no_timesheets || 0,
									m.errors || 0,
								]
							) + detailBlock,
							indicator: m.errors ? "red" : "green",
						});
					},
				});
			}
		);
	},
});
