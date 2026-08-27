// Copyright (c) 2026, phamos.eu and contributors
// For license information, please see license.txt

function _mis_hint_reload_timesheets(frm) {
	if (frm.is_new() || cint(frm.doc.docstatus) !== 0) {
		return;
	}
	frappe.show_alert({
		message: __("Save to reload the Timesheets table for the selected month and year."),
		indicator: "blue",
	});
}

function _mis_has_workflow(frm) {
	return !!frappe.workflow.get_state_fieldname(frm.doc.doctype);
}

// ── Grid selection buttons ──────────────────────────────────────────────────

/**
 * Inject a button into a child table's heading row that shows only when
 * at least one qualifying row is checked. The button is re-created on each
 * call so duplicate entries are prevented.
 */
function _mis_inject_grid_button(grid, css_class, label, should_show_fn, click_fn) {
	grid.wrapper.find("." + css_class).remove();
	const $btn = $(`<button class="btn btn-default btn-xs ${css_class}" style="margin-left:6px;">${label}</button>`);
	$btn.hide();

	// Place below the grid body, next to the "Add Row" button if present
	const $add_row = grid.wrapper.find(".grid-add-row").first();
	if ($add_row.length) {
		$add_row.after($btn);
	} else {
		const $footer = grid.wrapper.find(".grid-footer").first();
		if ($footer.length) {
			$footer.append($('<span>').append($btn));
		} else {
			grid.wrapper.append(
				$('<div class="mis-grid-btn-area" style="padding:4px 0 2px;">').append($btn)
			);
		}
	}

	function update() {
		const selected = grid.get_selected_children() || [];
		$btn.toggle(should_show_fn(selected));
	}

	grid.wrapper.off("change." + css_class + " click." + css_class);
	grid.wrapper.on("change." + css_class, ".grid-row-check", update);
	grid.wrapper.on("click." + css_class, ".check-run-all", function() { setTimeout(update, 50); });
	$btn.off("click." + css_class).on("click." + css_class, function() {
		const selected = grid.get_selected_children() || [];
		click_fn(selected);
	});
}

function _mis_setup_so_table_create_dn_btn(frm) {
	const field = frm.fields_dict.sales_order_status_information;
	if (!field || !field.grid) return;

	_mis_inject_grid_button(
		field.grid,
		"mis-create-dn-btn",
		__("Create Delivery Note"),
		function(selected) {
			return !frm.is_new() && !frm.is_dirty() &&
				selected.some(r => ["To Deliver", "To Deliver and Bill"].includes(r.status));
		},
		function(selected) {
			const deliverable = selected
				.filter(r => ["To Deliver", "To Deliver and Bill"].includes(r.status))
				.map(r => r.sales_order);
			if (!deliverable.length) {
				frappe.show_alert({ message: __("No Sales Orders with deliverable status selected."), indicator: "orange" });
				return;
			}
			_mis_create_dns_for_sos(frm, deliverable);
		}
	);
}

function _mis_setup_dn_table_create_si_btn(frm) {
	const field = frm.fields_dict.mis_delivery_notes;
	if (!field || !field.grid) return;

	_mis_inject_grid_button(
		field.grid,
		"mis-create-si-btn",
		__("Create Sales Invoice"),
		function(selected) {
			return !frm.is_new() && !frm.is_dirty() &&
				selected.some(r => r.delivery_note && r.status === "To Bill");
		},
		function(selected) {
			const dns = selected
				.filter(r => r.delivery_note && r.status === "To Bill")
				.map(r => r.delivery_note);
			if (!dns.length) {
				frappe.show_alert({ message: __("No eligible Delivery Notes selected (must have status 'To Bill')."), indicator: "orange" });
				return;
			}
			_mis_create_si_for_dns(frm, dns);
		}
	);
}

function _mis_setup_dn_table_submit_btn(frm) {
	const field = frm.fields_dict.mis_delivery_notes;
	if (!field || !field.grid) return;

	_mis_inject_grid_button(
		field.grid,
		"mis-submit-dn-btn",
		__("Submit Delivery Note(s)"),
		function(selected) {
			return !frm.is_new() && !frm.is_dirty() &&
				selected.some(r => r.delivery_note && r.status === "Draft");
		},
		function(selected) {
			const draft_dns = selected
				.filter(r => r.delivery_note && r.status === "Draft")
				.map(r => r.delivery_note);
			if (!draft_dns.length) {
				frappe.show_alert({ message: __("No draft Delivery Notes selected."), indicator: "orange" });
				return;
			}
			_mis_submit_dns_from_table(frm, draft_dns);
		}
	);
}

function _mis_setup_si_table_submit_btn(frm) {
	const field = frm.fields_dict.mis_sales_invoices;
	if (!field || !field.grid) return;

	_mis_inject_grid_button(
		field.grid,
		"mis-submit-si-btn",
		__("Submit Sales Invoice(s)"),
		function(selected) {
			return !frm.is_new() && !frm.is_dirty() &&
				selected.some(r => r.sales_invoice && r.status === "Draft");
		},
		function(selected) {
			const draft_sis = selected
				.filter(r => r.sales_invoice && r.status === "Draft")
				.map(r => r.sales_invoice);
			if (!draft_sis.length) {
				frappe.show_alert({ message: __("No draft Sales Invoices selected."), indicator: "orange" });
				return;
			}
			_mis_submit_sis_from_table(frm, draft_sis);
		}
	);
}

function _mis_setup_grid_action_buttons(frm) {
	_mis_setup_so_table_create_dn_btn(frm);
	_mis_setup_dn_table_submit_btn(frm);
	_mis_setup_dn_table_create_si_btn(frm);
	_mis_setup_si_table_submit_btn(frm);
}

// ── DN creation ─────────────────────────────────────────────────────────────

function _mis_create_dns_for_sos(frm, sales_orders) {
	if (!sales_orders || !sales_orders.length) return;
	frappe.confirm(
		__("Create Delivery Note(s) for {0} Sales Order(s)?", [sales_orders.length]),
		function() {
			let promise = Promise.resolve();
			sales_orders.forEach(function(so) {
				promise = promise.then(function() {
					return new Promise(function(resolve) {
						frappe.call({
							method: "phamos.phamos.doctype.monthly_implementation_summary.monthly_implementation_summary.create_delivery_note",
							args: {
								docname: frm.doc.name,
								sales_order: so,
								delivery_note_item: []
							},
							freeze: true,
							freeze_message: __("Creating Delivery Note for {0}...", [so]),
							callback: function(r) {
								if (r.exc) {
									frappe.msgprint({ title: __("Error for {0}", [so]), message: r.exc[0] || __("Failed."), indicator: "red" });
								} else if (r.message && r.message.dn_name) {
									frappe.show_alert({ message: __("Created {0}", [r.message.dn_name]), indicator: "green" });
								}
								resolve();
							}
						});
					});
				});
			});
			promise.then(function() { frm.reload_doc(); });
		}
	);
}

// ── SI creation ─────────────────────────────────────────────────────────────

function _mis_create_si_for_dns(frm, delivery_notes) {
	if (!delivery_notes || !delivery_notes.length) return;
	frappe.confirm(
		__("Create Sales Invoice(s) for {0} Delivery Note(s)?", [delivery_notes.length]),
		function() {
			let promise = Promise.resolve();
			delivery_notes.forEach(function(dn) {
				promise = promise.then(function() {
					return new Promise(function(resolve) {
						frappe.call({
							method: "phamos.phamos.doctype.monthly_implementation_summary.monthly_implementation_summary.create_sales_invoice_from_mis",
							args: { docname: frm.doc.name, delivery_note: dn },
							freeze: true,
							freeze_message: __("Creating Sales Invoice for {0}...", [dn]),
							callback: function(r) {
								if (r.exc) {
									frappe.msgprint({ title: __("Error for {0}", [dn]), message: r.exc[0] || __("Failed."), indicator: "red" });
								} else if (r.message && r.message.sales_invoice) {
									frappe.show_alert({ message: __("Created {0}", [r.message.sales_invoice]), indicator: "green" });
								}
								resolve();
							}
						});
					});
				});
			});
			promise.then(function() { frm.reload_doc(); });
		}
	);
}

function _mis_submit_dns_from_table(frm, delivery_notes) {
	if (!delivery_notes || !delivery_notes.length) return;
	frappe.confirm(
		__("{0} Delivery Note(s) will be submitted. Continue?", [delivery_notes.length]),
		function() {
			frappe.call({
				method: "phamos.phamos.doctype.monthly_implementation_summary.monthly_implementation_summary.submit_delivery_notes_in_mis",
				args: { docname: frm.doc.name, delivery_notes: delivery_notes },
				freeze: true,
				freeze_message: __("Submitting Delivery Note(s)..."),
				callback: function(r) {
					if (r.exc) {
						frappe.msgprint({ title: __("Error"), message: r.exc[0] || __("Failed."), indicator: "red" });
						return;
					}
					const d = r.message || {};
					if (d.failed_details && d.failed_details.length) {
						frappe.msgprint({
							title: __("Some submissions failed"),
							indicator: "orange",
							message: d.failed_details
								.map(item => `${_mis_escape(item.delivery_note || "")} : ${_mis_escape(item.error || "")}` )
								.join("<br>"),
						});
					}
					frappe.show_alert({
						message: __("Submitted: {0}, Skipped: {1}, Failed: {2}", [
							cint(d.submitted || 0), cint(d.already_submitted || 0), cint(d.failed || 0)
						]),
						indicator: cint(d.failed || 0) ? "orange" : "green",
					});
					frm.reload_doc();
				}
			});
		}
	);
}

function _mis_submit_sis_from_table(frm, sales_invoices) {
	if (!sales_invoices || !sales_invoices.length) return;
	frappe.confirm(
		__("{0} Sales Invoice(s) will be submitted. Continue?", [sales_invoices.length]),
		function() {
			frappe.call({
				method: "phamos.phamos.doctype.monthly_implementation_summary.monthly_implementation_summary.submit_sales_invoices_in_mis",
				args: { docname: frm.doc.name, sales_invoices: sales_invoices },
				freeze: true,
				freeze_message: __("Submitting Sales Invoice(s)..."),
				callback: function(r) {
					if (r.exc) {
						frappe.msgprint({ title: __("Error"), message: r.exc[0] || __("Failed."), indicator: "red" });
						return;
					}
					const d = r.message || {};
					if (d.failed_details && d.failed_details.length) {
						frappe.msgprint({
							title: __("Some submissions failed"),
							indicator: "orange",
							message: d.failed_details
								.map(item => `${_mis_escape(item.sales_invoice || "")} : ${_mis_escape(item.error || "")}` )
								.join("<br>"),
						});
					}
					frappe.show_alert({
						message: __("Submitted: {0}, Skipped: {1}, Failed: {2}", [
							cint(d.submitted || 0), cint(d.already_submitted || 0), cint(d.failed || 0)
						]),
						indicator: cint(d.failed || 0) ? "orange" : "green",
					});
					frm.reload_doc();
				}
			});
		}
	);
}

function _mis_show_create_si_dialog(frm) {
	const eligible = (frm.doc.mis_delivery_notes || []).filter(
		r => r.delivery_note && !r.sales_invoice && r.status === "To Bill"
	);
	if (!eligible.length) {
		frappe.show_alert({ message: __("No Delivery Notes available for invoicing."), indicator: "orange" });
		return;
	}

	const rows_html = eligible.map(r => `
		<tr>
			<td style="width:36px; text-align:center;">
				<input type="checkbox" class="mis-si-dn-check" data-dn="${_mis_escape(r.delivery_note)}" checked>
			</td>
			<td><a href="/app/delivery-note/${encodeURIComponent(r.delivery_note || "")}" target="_blank">${_mis_escape(r.delivery_note)}</a></td>
			<td>${_mis_escape(r.sales_order || "")}</td>
			<td style="text-align:right;">${_mis_number(r.grand_total)}</td>
		</tr>
	`).join("");

	const dialog = new frappe.ui.Dialog({
		title: __("Create Sales Invoice"),
		fields: [{ fieldname: "dn_list_html", fieldtype: "HTML" }],
		primary_action_label: __("Create"),
		primary_action: function() {
			const selected = [];
			dialog.$wrapper.find(".mis-si-dn-check:checked").each(function() {
				const dn = $(this).attr("data-dn");
				if (dn) selected.push(dn);
			});
			if (!selected.length) {
				frappe.show_alert({ message: __("Select at least one Delivery Note."), indicator: "orange" });
				return;
			}
			dialog.hide();
			_mis_create_si_for_dns(frm, selected);
		},
	});

	dialog.get_field("dn_list_html").$wrapper.html(`
		<table class="table table-bordered table-hover" style="margin-bottom:0;">
			<thead>
				<tr>
					<th style="width:36px;"><input type="checkbox" id="mis-si-select-all" checked></th>
					<th>${__("Delivery Note")}</th>
					<th>${__("Sales Order")}</th>
					<th style="text-align:right;">${__("Grand Total")}</th>
				</tr>
			</thead>
			<tbody>${rows_html}</tbody>
		</table>
	`);

	dialog.$wrapper.on("change", "#mis-si-select-all", function() {
		dialog.$wrapper.find(".mis-si-dn-check").prop("checked", $(this).is(":checked"));
	});

	dialog.show();
}


function _mis_is_timesheet_pending(row) {
	if (!row) return false;
	if (Object.prototype.hasOwnProperty.call(row, "is_pending")) {
		return cint(row.is_pending) === 1;
	}
	if (cint(row.docstatus) === 2) return false;
	if (cint(row.docstatus) === 1) return false;
	const workflow_state = (row.workflow_state || "").toLowerCase();
	const status = (row.status || "").toLowerCase();
	if (["approved", "submitted", "completed", "billed"].includes(workflow_state)) {
		return false;
	}
	if (["submitted", "completed", "billed"].includes(status)) {
		return false;
	}
	return true;
}

function _mis_escape(value) {
	return frappe.utils.escape_html(value || "");
}

function _mis_number(value) {
	return _mis_escape(format_number(flt(value || 0), null, 2));
}

function _mis_get_active_filters_summary_html(filters) {
	const parts = [];
	if (filters.employee) {
		parts.push(`${__("Employee")}: <strong>${_mis_escape(filters.employee)}</strong>`);
	}
	if (filters.project) {
		parts.push(`${__("Project")}: <strong>${_mis_escape(filters.project)}</strong>`);
	}
	if (filters.date_from || filters.date_to) {
		const from_label = filters.date_from ? _mis_escape(filters.date_from) : "-";
		const to_label = filters.date_to ? _mis_escape(filters.date_to) : "-";
		parts.push(`${__("Date")}: <strong>${from_label}</strong> - <strong>${to_label}</strong>`);
	}
	if (!parts.length) {
		return `<div class="mis-ts-filters text-muted">${__("Active filters: None")}</div>`;
	}
	return `<div class="mis-ts-filters">${__("Active filters")}: ${parts.join(" | ")}</div>`;
}

function _mis_timesheet_row_html(row) {
	const pending = _mis_is_timesheet_pending(row);
	const can_select = pending && row.timesheet;
	const badge_class = pending ? "orange" : "green";
	const badge_label = pending ? __("Pending") : __("Approved");
	const billable_value = flt(row.billable_hours || 0);

	return `
		<tr>
			<td class="mis-ts-col-check">
				<input type="checkbox" class="mis-ts-select" data-timesheet="${_mis_escape(row.timesheet)}" ${can_select ? "" : "disabled"}>
			</td>
			<td><a href="/app/timesheet/${encodeURIComponent(row.timesheet || "")}" target="_blank">${_mis_escape(row.timesheet)}</a></td>
			<td>${_mis_escape(row.date)}</td>
			<td>${_mis_escape(row.employee_name)}</td>
			<td>${_mis_escape(row.project)}</td>
			<td class="mis-ts-col-num">${_mis_number(row.total_hours)}</td>
			<td class="mis-ts-col-num">
				<input
					type="text"
					inputmode="decimal"
					class="mis-ts-billable-input"
					data-timesheet="${_mis_escape(row.timesheet)}"
					value="${billable_value}"
					style="width:92px; text-align:right;"
				>
			</td>
			<td><span class="indicator-pill ${badge_class}">${badge_label}</span></td>
		</tr>
	`;
}

function _mis_render_timesheet_approval_table(dialog, rows) {
	const html_field = dialog.get_field("timesheet_approval_html");
	if (!html_field || !html_field.$wrapper) return;

	const filters = dialog.__mis_ts_filters || {};
	const filters_summary_html = _mis_get_active_filters_summary_html(filters);

	// Sort by billable hours: highest to lowest
	const sorted_rows = [...(rows || [])].sort((a, b) => {
		return flt(b.billable_hours || 0) - flt(a.billable_hours || 0);
	});

	const table_rows = sorted_rows.map(_mis_timesheet_row_html).join("");

	html_field.$wrapper.html(`
		<style>
			.mis-ts-wrap .mis-ts-note { margin-bottom: 8px; }
			.mis-ts-wrap .mis-ts-filters { margin-bottom: 10px; font-size: 12px; }
			.mis-ts-wrap .mis-ts-toolbar { display:flex; justify-content:space-between; align-items:center; gap:8px; margin-bottom:10px; }
			.mis-ts-wrap .mis-ts-actions { display:flex; gap:8px; align-items:center; }
			.mis-ts-wrap .mis-ts-select-all { margin:0; display:flex; align-items:center; gap:8px; font-weight:500; }
			.mis-ts-wrap .mis-ts-table-wrap { max-height: 58vh; overflow: auto; border: 1px solid var(--border-color); border-radius: 8px; }
			.mis-ts-wrap .mis-ts-col-check { width: 36px; text-align: center; }
			.mis-ts-wrap .mis-ts-col-num { text-align: right; }
			.mis-ts-wrap table { margin-bottom: 0; }
			.mis-ts-wrap thead th { position: sticky; top: 0; background: var(--bg-color); z-index: 1; }
		</style>
		<div class="mis-ts-wrap">
		<div class="small text-muted mis-ts-note">
			${__("Review and approve pending timesheets for this MIS period.")}
		</div>
		${filters_summary_html}
		<div class="mis-ts-toolbar">
			<div class="mis-ts-actions">
				<button class="btn btn-default btn-sm" type="button" id="mis-ts-filter-btn">${__("Filter")}</button>
				<button class="btn btn-light btn-sm" type="button" id="mis-ts-clear-filter-btn">${__("Clear")}</button>
			</div>
			<label class="mis-ts-select-all">
				<input type="checkbox" id="mis-ts-select-all"> ${__("Select all pending")}
			</label>
		</div>
		<div class="mis-ts-table-wrap">
			<table class="table table-bordered table-hover">
				<thead>
					<tr>
						<th class="mis-ts-col-check"></th>
						<th>${__("Timesheet")}</th>
						<th>${__("Date")}</th>
						<th>${__("Employee")}</th>
						<th>${__("Project")}</th>
						<th class="mis-ts-col-num">${__("Total")}</th>
						<th class="mis-ts-col-num">${__("Billable")}</th>
						<th>${__("Status")}</th>
					</tr>
				</thead>
				<tbody>
					${table_rows || `<tr><td colspan="8" class="text-muted text-center">${__("No timesheets found for the current filter.")}</td></tr>`}
				</tbody>
			</table>
		</div>
		</div>
	`);
}


function _mis_render_timesheet_loading_state(dialog) {
	const html_field = dialog.get_field("timesheet_approval_html");
	if (!html_field || !html_field.$wrapper) return;
	html_field.$wrapper.html(
		`<div class="small text-muted" style="padding:16px 6px;">${__("Loading timesheets...")}</div>`
	);
}

function _mis_get_selected_timesheets(dialog) {
	const selected = [];
	dialog.$wrapper.find(".mis-ts-select:checked").each(function () {
		const ts = $(this).attr("data-timesheet");
		if (ts) selected.push(ts);
	});
	return selected;
}

function _mis_get_billable_updates(dialog) {
	const updates = [];
	const originals = dialog.__mis_ts_original_billable || {};
	dialog.$wrapper.find(".mis-ts-billable-input").each(function () {
		const timesheet = ($(this).attr("data-timesheet") || "").trim();
		const billable = flt($(this).val() || 0);
		const original = flt(originals[timesheet] || 0);
		if (!timesheet) return;
		if (Math.abs(billable - original) < 0.0001) return;
		updates.push({
			timesheet,
			billable_hours: billable,
		});
	});
	return updates;
}

function _mis_save_billable_changes(frm, dialog) {
	const rows = _mis_get_billable_updates(dialog);
	if (!rows.length) {
		frappe.show_alert({
			message: __("No billable changes to save."),
			indicator: "blue",
		});
		return Promise.resolve();
	}

	return frappe.call({
		method: "phamos.phamos.doctype.monthly_implementation_summary.monthly_implementation_summary.save_timesheet_billable_in_mis",
		args: {
			docname: frm.doc.name,
			rows,
		},
		freeze: true,
		freeze_message: __("Saving billable hours..."),
	}).then((r) => {
		const data = (r && r.message) || {};
		const updated_names = Array.isArray(data.updated_timesheets) ? data.updated_timesheets : [];
		frappe.show_alert({
			message: updated_names.length
				? __("Saved: {0} ({1}), Failed: {2}", [
					cint(data.updated || 0),
					updated_names.join(", "),
					cint(data.failed || 0),
				])
				: __("Saved: {0}, Failed: {1}", [cint(data.updated || 0), cint(data.failed || 0)]),
			indicator: cint(data.failed || 0) ? "orange" : "green",
		});

		if (data.failed_details && data.failed_details.length) {
			frappe.msgprint({
				title: __("Some updates failed"),
				indicator: "orange",
				message: data.failed_details
					.map((item) => `${_mis_escape(item.timesheet || "")} : ${_mis_escape(item.error || "")}`)
					.join("<br>"),
			});
		}

		return frm.reload_doc().then(() => _mis_load_timesheet_approval_rows(frm, dialog));
	});
}

function _mis_submit_selected_timesheets(frm, dialog) {
	const selected_timesheets = _mis_get_selected_timesheets(dialog);
	if (!selected_timesheets.length) {
		frappe.show_alert({
			message: __("Select at least one pending timesheet to submit."),
			indicator: "orange",
		});
		return Promise.resolve(false);
	}

	return frappe.call({
		method: "phamos.phamos.doctype.monthly_implementation_summary.monthly_implementation_summary.approve_timesheets_in_mis",
		args: {
			docname: frm.doc.name,
			timesheets: selected_timesheets,
		},
		freeze: true,
		freeze_message: __("Submitting selected timesheets..."),
	}).then((r) => {
		const data = (r && r.message) || {};
		frappe.show_alert({
			message: __("Submitted: {0}, Skipped: {1}, Failed: {2}", [
				cint(data.approved || 0),
				cint(data.already_approved || 0),
				cint(data.failed || 0),
			]),
			indicator: cint(data.failed || 0) ? "orange" : "green",
		});

		if (data.failed_details && data.failed_details.length) {
			frappe.msgprint({
				title: __("Some submissions failed"),
				indicator: "orange",
				message: data.failed_details
					.map((item) => `${_mis_escape(item.timesheet || "")} : ${_mis_escape(item.error || "")}`)
					.join("<br>"),
			});
		}

		return frm.reload_doc().then(() => true);
	});
}
function _mis_bind_timesheet_approval_dialog_events(frm, dialog) {
	dialog.$wrapper.off("change", "#mis-ts-select-all");
	dialog.$wrapper.on("change", "#mis-ts-select-all", function () {
		const checked = !!$(this).is(":checked");
		dialog.$wrapper.find(".mis-ts-select:not(:disabled)").prop("checked", checked);
	});

	dialog.$wrapper.off("click", "#mis-ts-filter-btn");
	dialog.$wrapper.on("click", "#mis-ts-filter-btn", function () {
		const filters = dialog.__mis_ts_filters || {};

		frappe.prompt(
			[
				{
					label: __("Employee"),
					fieldname: "employee",
					fieldtype: "Link",
					options: "Employee",
					default: filters.employee || "",
				},
				{
					label: __("Project"),
					fieldname: "project",
					fieldtype: "Link",
					options: "Project",
					default: filters.project || "",
				},
				{
					label: __("From Date"),
					fieldname: "date_from",
					fieldtype: "Date",
					default: filters.date_from || "",
				},
				{
					label: __("To Date"),
					fieldname: "date_to",
					fieldtype: "Date",
					default: filters.date_to || "",
				},
			],
			(values) => {
				dialog.__mis_ts_filters = {
					employee: values.employee || "",
					project: values.project || "",
					date_from: values.date_from || "",
					date_to: values.date_to || "",
				};

				_mis_load_timesheet_approval_rows(frm, dialog);
			},
			__("Filter Timesheets"),
			__("Apply")
		);
	});

	dialog.$wrapper.off("click", "#mis-ts-clear-filter-btn");
	dialog.$wrapper.on("click", "#mis-ts-clear-filter-btn", function () {
		dialog.__mis_ts_filters = {};
		dialog.$wrapper.find("#mis-ts-select-all").prop("checked", false);

		_mis_load_timesheet_approval_rows(frm, dialog);
	});

	// ---------------------------------------------------------
	// Create column search fields
	// ---------------------------------------------------------

	const $table = dialog.$wrapper.find(".mis-ts-table-wrap table");

	if ($table.length && !$table.find("thead .mis-ts-column-filter-row").length) {
		$table.find("thead").append(`
			<tr class="mis-ts-column-filter-row">
				<th></th>
				<th>
					<input
						type="text"
						class="form-control input-sm mis-ts-column-filter"
						data-column="timesheet"
						placeholder="${__("Search")}"
					>
				</th>
				<th>
					<input
						type="text"
						class="form-control input-sm mis-ts-column-filter"
						data-column="date"
						placeholder="${__("Search")}"
					>
				</th>
				<th>
					<input
						type="text"
						class="form-control input-sm mis-ts-column-filter"
						data-column="employee_name"
						placeholder="${__("Search")}"
					>
				</th>
				<th>
					<input
						type="text"
						class="form-control input-sm mis-ts-column-filter"
						data-column="project"
						placeholder="${__("Search")}"
					>
				</th>
				<th>
					<input
						type="text"
						class="form-control input-sm mis-ts-column-filter"
						data-column="total_hours"
						placeholder="${__("Search")}"
					>
				</th>
				<th>
					<input
						type="text"
						class="form-control input-sm mis-ts-column-filter"
						data-column="billable_hours"
						placeholder="${__("Search")}"
					>
				</th>
				<th>
					<input
						type="text"
						class="form-control input-sm mis-ts-column-filter"
						data-column="status"
						placeholder="${__("Search")}"
					>
				</th>
			</tr>
		`);

		$table.find("thead .mis-ts-column-filter-row th").css({
			padding: "4px",
			background: "var(--bg-color)",
		});

		$table.find(".mis-ts-column-filter").css({
			width: "100%",
			fontSize: "12px",
		});
	}

	// ---------------------------------------------------------
	// Column search functionality
	// ---------------------------------------------------------

	dialog.$wrapper.off("input", ".mis-ts-column-filter");
	dialog.$wrapper.on("input", ".mis-ts-column-filter", function () {
		const column_filters = {};

		dialog.$wrapper.find(".mis-ts-column-filter").each(function () {
			const column = $(this).attr("data-column");
			const value = String($(this).val() || "")
				.trim()
				.toLowerCase();

			if (column && value) {
				column_filters[column] = value;
			}
		});

		dialog.$wrapper
			.find(".mis-ts-table-wrap tbody tr")
			.each(function () {
				const $row = $(this);

				if (!$row.find(".mis-ts-select").length) {
					return;
				}

				const row_values = {
					timesheet: String(
						$row.find("td").eq(1).text() || ""
					)
						.trim()
						.toLowerCase(),

					date: String(
						$row.find("td").eq(2).text() || ""
					)
						.trim()
						.toLowerCase(),

					employee_name: String(
						$row.find("td").eq(3).text() || ""
					)
						.trim()
						.toLowerCase(),

					project: String(
						$row.find("td").eq(4).text() || ""
					)
						.trim()
						.toLowerCase(),

					total_hours: String(
						$row.find("td").eq(5).text() || ""
					)
						.trim()
						.toLowerCase(),

					billable_hours: String(
						$row.find(".mis-ts-billable-input").val() || ""
					)
						.trim()
						.toLowerCase(),

					status: String(
						$row.find("td").eq(7).text() || ""
					)
						.trim()
						.toLowerCase(),
				};

				const matches = Object.keys(column_filters).every(
					(column) => {
						return row_values[column].includes(
							column_filters[column]
						);
					}
				);

				$row.toggle(matches);
			});
	});
}


function _mis_load_timesheet_approval_rows(frm, dialog) {
	const filters = dialog.__mis_ts_filters || {};
	_mis_render_timesheet_loading_state(dialog);
	return frappe.call({
		method: "phamos.phamos.doctype.monthly_implementation_summary.monthly_implementation_summary.get_timesheet_approval_rows",
		args: {
			docname: frm.doc.name,
			employee: filters.employee || null,
			project: filters.project || null,
			date_from: filters.date_from || null,
			date_to: filters.date_to || null,
		},
		freeze: false,
	}).then((r) => {
		dialog.__mis_ts_rows = (r && r.message) || [];
		dialog.__mis_ts_original_billable = {};
		dialog.__mis_ts_rows.forEach((row) => {
			if (row && row.timesheet) {
				dialog.__mis_ts_original_billable[row.timesheet] = flt(row.billable_hours || 0);
			}
		});
		_mis_render_timesheet_approval_table(dialog, dialog.__mis_ts_rows);
		_mis_bind_timesheet_approval_dialog_events(frm, dialog);
	});
}

function _mis_show_timesheet_approval_dialog(frm) {
	const dialog = new frappe.ui.Dialog({
		title: __("Timesheet Approval"),
		fields: [{
			fieldname: "timesheet_approval_html",
			fieldtype: "HTML",
		}],
		primary_action_label: __("Save"),
		secondary_action_label: __("Approve"),
		secondary_action: () => {
			_mis_submit_selected_timesheets(frm, dialog).then((ok) => {
				if (ok) dialog.hide();
			});
		},
		primary_action: () => {
			_mis_save_billable_changes(frm, dialog);
		},
	});

	dialog.__mis_ts_filters = {};
	dialog.show();
	dialog.$wrapper.find(".modal-dialog").css("max-width", "1180px");
	const $footer = dialog.$wrapper.find(".modal-footer");
	$footer.find(".btn-primary").css({
		background: "#111",
		borderColor: "#111",
		fontWeight: "700",
	});
	$footer.find(".btn-secondary, .btn-default").first().css({
		background: "#111",
		color: "#fff",
		borderColor: "#111",
		fontWeight: "700",
	});
	_mis_load_timesheet_approval_rows(frm, dialog);
}

function _mis_maybe_open_timesheet_approval_dialog(frm) {
	if (frm.is_new() || !frm.doc.name) return;

	if (frm.__mis_timesheet_dialog_opened_for === frm.doc.name) return;

	frappe.call({
		method: "phamos.phamos.doctype.monthly_implementation_summary.monthly_implementation_summary.get_timesheet_approval_rows",
		args: {
			docname: frm.doc.name,
		},
		freeze: false,
	}).then((r) => {
		const rows = (r && r.message) || [];

		// Only open the dialog when at least one timesheet is pending
		const has_pending_timesheet = rows.some((row) =>
			_mis_is_timesheet_pending(row)
		);

		if (!has_pending_timesheet) {
			return;
		}

		frm.__mis_timesheet_dialog_opened_for = frm.doc.name;

		setTimeout(() => {
			_mis_show_timesheet_approval_dialog(frm);
		}, 250);
	});
}

frappe.ui.form.on("Monthly Implementation Summary", {
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
	month: function (frm) {
		_mis_hint_reload_timesheets(frm);
	},
	year: function (frm) {
		if (typeof frm.doc.year === "number") {
			frm.set_value("year", String(frm.doc.year));
		}
		_mis_hint_reload_timesheets(frm);
	},
	implementation: function (frm) {
		if (frm.is_new()) return;
		frm.save();
	},
	sales_order: function(frm) {
		// field removed — handler kept as no-op for compatibility
	},
	refresh: function(frm) {
		_mis_setup_grid_action_buttons(frm);
		if (frm.is_new()) {
			const d = new Date();
			const months = ["January", "February", "March", "April", "May", "June", "July", "August", "September", "October", "November", "December"];
			const defaults = {
				year: String(d.getFullYear()),
				month: months[d.getMonth()],
				mis_delivery_notes: [],
				delivery_note_item: [],
				timesheets_table: [],
				total_hours: 0,
				billable_hours: 0
			};
			Object.keys(defaults).forEach(k => { frm.set_value(k, defaults[k]); });
			return;
		}
		if (cint(frm.doc.docstatus) === 1) {
			const has_billable_dns = (frm.doc.mis_delivery_notes || []).some(
				r => r.delivery_note && r.status === "To Bill"
			);
			if (has_billable_dns) {
				frm.add_custom_button(__("Create Sales Invoice"), function() {
					_mis_show_create_si_dialog(frm);
				});
			}
		}
		_mis_maybe_open_timesheet_approval_dialog(frm);
		// Add Sales Orders to connections dashboard
		if (frm.doc.implementation) {
			frappe.db.get_list('Sales Order', {
				filters: {
					custom_implementation: frm.doc.implementation,
					status: ['!=', 'completed'],
					docstatus: 1
				},
				fields: ['name']
			}).then(records => {
				// Wait for sidebar to render
				setTimeout(() => {
					// Remove any existing Sales Order badges to avoid duplicates
					$('.document-link[data-doctype="Sales Order"]').remove();

					// Find the container
					let $container = $('.form-links');

					if ($container.length === 0) {
						$container = $('.form-dashboard-section.connections');
					}

					if ($container.length === 0) {
						$container = $('[data-doctype="Delivery Note"]').parent();
					}

					if ($container.length > 0) {
						let badge_html = `
							<div class="document-link" data-doctype="Sales Order">
								<div class="document-link-badge" data-doctype="Sales Order">
									${records.length > 0 ? `<span class="count">${records.length}</span>` : ''}
									<a class="badge-link">Sales Order</a>
								</div>
							</div>
						`;

						$container.append(badge_html);

						// Add click handler
						$('.document-link[data-doctype="Sales Order"] .badge-link').on('click', function(e) {
							e.preventDefault();
							if (records.length > 0) {
								let names = records.map(r => r.name);
								frappe.set_route('List', 'Sales Order', {name: ['in', names]});
							} else {
								frappe.set_route('List', 'Sales Order', {custom_implementation: frm.doc.implementation});
							}
						});
					}
				}, 1000);
			});
		}
	},
	on_submit: function(frm) {
		// Workflow submits use before_workflow_action; avoid double sync if standard Submit is still available.
		if (_mis_has_workflow(frm)) {
			return;
		}
		frappe.call({
				method: "phamos.phamos.doctype.monthly_implementation_summary.monthly_implementation_summary.submit_mis_dn_action",
				args: { docname: frm.doc.name },
				freeze: true,
				freeze_message: __("Syncing delivery note with this summary..."),
				callback: function (r) {
					if (r.exc) {
						frappe.msgprint({
							title: __("Error"),
							message: r.exc[0] || __("Failed to sync delivery note."),
							indicator: "red"
						});
						return;
					}
					frm.reload_doc();
				}
			});
	},

	before_workflow_action(frm) {
		if (!_mis_has_workflow(frm) || frm.selected_workflow_action !== "Submit") {
			return;
		}

		frappe.dom.unfreeze();

		return new Promise(function (resolve) {
			frappe.call({
				method: "phamos.phamos.doctype.monthly_implementation_summary.monthly_implementation_summary.submit_mis_dn_action",
				args: { docname: frm.doc.name },
				freeze: true,
				freeze_message: __("Syncing delivery note with this summary..."),
				callback: function (r) {
					if (r.exc) {
						frappe.msgprint({
							title: __("Error"),
							message: r.exc[0] || __("Failed to sync delivery note."),
							indicator: "red"
						});
						resolve();
						return;
					}
					frm.reload_doc().then(resolve);
				}
			});
		});
	},
});

function recalculate_totals_from_timesheets(frm) {
	if (!frm.doc.timesheets_table || !frm.doc.timesheets_table.length) return;
	let total_hours = 0;
	let billable_hours = 0;
	frm.doc.timesheets_table.forEach(row => {
		total_hours += flt(row.total_hours);
		billable_hours += flt(row.billable_hours);
	});
	frm.set_value('total_hours', flt(total_hours, 2));
	frm.set_value('billable_hours', flt(billable_hours, 2));
}

frappe.ui.form.on("Timesheets", {
	total_hours: function(frm, cdt, cdn) { recalculate_totals_from_timesheets(frm); },
	billable_hours: function(frm, cdt, cdn) { recalculate_totals_from_timesheets(frm); },
	rows_added: function(frm, cdt, cdn) { recalculate_totals_from_timesheets(frm); },
	rows_removed: function(frm, cdt, cdn) { recalculate_totals_from_timesheets(frm); },
});

// Delivery Note Item embedded in MIS does not load ERPNext TransactionController, so qty/rate do not
// recalculate amount. Mirror standard behaviour: amount = qty * rate; stock_qty = qty * conversion_factor.
function mis_recalculate_dn_item_row(frm, cdt, cdn) {
	if (frm.doc.doctype !== "Monthly Implementation Summary") return;
	var row = locals[cdt][cdn];
	if (!row) return;
	frappe.model.round_floats_in(row, ["qty", "rate", "conversion_factor"]);
	var cf = flt(row.conversion_factor) || 1;
	if (frappe.meta.get_docfield(cdt, "stock_qty")) {
		frappe.model.set_value(cdt, cdn, "stock_qty", flt(flt(row.qty) * cf, precision("stock_qty", row)));
	}
	var amount = flt(flt(row.qty) * flt(row.rate), precision("amount", row));
	frappe.model.set_value(cdt, cdn, "amount", amount);
}

// Fetch Item Name, UOM, UOM Conversion Factor when item_code is selected in MIS delivery_note_item
frappe.ui.form.on("Delivery Note Item", {
	item_code: function(frm, cdt, cdn) {
		if (frm.doc.doctype !== "Monthly Implementation Summary") return;
		var row = frappe.model.get_doc(cdt, cdn);
		if (!row.item_code) return;
		frappe.db.get_value("Item", row.item_code, ["item_name", "stock_uom"], function(r) {
			if (r) {
				frappe.model.set_value(cdt, cdn, "item_name", r.item_name);
				frappe.model.set_value(cdt, cdn, "stock_uom", r.stock_uom);
				frappe.model.set_value(cdt, cdn, "uom", r.stock_uom);
				frappe.model.set_value(cdt, cdn, "conversion_factor", 1);
				mis_recalculate_dn_item_row(frm, cdt, cdn);
			}
		});
	},
	qty: function(frm, cdt, cdn) {
		mis_recalculate_dn_item_row(frm, cdt, cdn);
	},
	rate: function(frm, cdt, cdn) {
		mis_recalculate_dn_item_row(frm, cdt, cdn);
	},
	conversion_factor: function(frm, cdt, cdn) {
		mis_recalculate_dn_item_row(frm, cdt, cdn);
	},
});

add_custom_links = (fieldname, doctype, docname) => {
  doctype_url = doctype.replace(/ /g, "-").toLowerCase();
  cur_frm.fields_dict[fieldname].$wrapper.html(
    `<div class="form-group">
        <div class="clearfix">
          <label class="control-label" style="padding-right: 0px;">${doctype}</label>
        </div>
        <div class="control-input-wrapper">
          <a class="control-value like-disabled-input" href="/app/${doctype_url}/${docname}">${docname}</a>
        </div>
      </div>`
  );
}
