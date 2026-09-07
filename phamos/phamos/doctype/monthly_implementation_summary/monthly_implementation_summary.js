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
	if (frm.doc.status === "Closed") return;
	_mis_setup_so_table_create_dn_btn(frm);
	_mis_setup_dn_table_submit_btn(frm);
	_mis_setup_dn_table_create_si_btn(frm);
	_mis_setup_si_table_submit_btn(frm);
}

function _mis_setup_status_buttons(frm) {
	if (!frm.has_perm("submit")) return;
	if (frm.doc.status === "Closed") {
		frm.add_custom_button(__("Re-open"), function() {
			frappe.call({
				method: "phamos.phamos.doctype.monthly_implementation_summary.monthly_implementation_summary.reopen_monthly_implementation_summary",
				args: { docname: frm.doc.name },
				freeze: true,
				callback: function() { frm.reload_doc(); },
			});
		}, __("Status"));
	} else {
		frm.add_custom_button(__("Close"), function() {
			frappe.confirm(
				__("Close this Monthly Implementation Summary? It will be excluded from Sales Order / Delivery Note update logic until re-opened."),
				function() {
					frappe.call({
						method: "phamos.phamos.doctype.monthly_implementation_summary.monthly_implementation_summary.close_monthly_implementation_summary",
						args: { docname: frm.doc.name },
						freeze: true,
						callback: function() { frm.reload_doc(); },
					});
				}
			);
		}, __("Status"));
	}
}

// ── DN creation ─────────────────────────────────────────────────────────────

function _mis_run_create_dns(frm, sales_orders, submit_after_create) {
	const created = [];
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
							created.push(r.message.dn_name);
							frappe.show_alert({ message: __("Created {0}", [r.message.dn_name]), indicator: "green" });
						}
						resolve();
					}
				});
			});
		});
	});
	return promise
		.then(function() {
			if (!submit_after_create || !created.length) return;
			return new Promise(function(resolve) {
				frappe.call({
					method: "phamos.phamos.doctype.monthly_implementation_summary.monthly_implementation_summary.submit_delivery_notes_in_mis",
					args: { docname: frm.doc.name, delivery_notes: created },
					freeze: true,
					freeze_message: __("Submitting Delivery Note(s)..."),
					callback: function(r) {
						const d = r.message || {};
						if (d.failed_details && d.failed_details.length) {
							frappe.msgprint({
								title: __("Some submissions failed"),
								indicator: "orange",
								message: d.failed_details
									.map(item => `${_mis_escape(item.delivery_note || "")} : ${_mis_escape(item.error || "")}`)
									.join("<br>"),
							});
						}
						resolve();
					}
				});
			});
		})
		.then(function() { frm.reload_doc(); });
}

function _mis_create_dns_for_sos(frm, sales_orders) {
	if (!sales_orders || !sales_orders.length) return;
	const dialog = new frappe.ui.Dialog({
		title: __("Create Delivery Note(s)"),
		fields: [
			{
				fieldname: "info",
				fieldtype: "HTML",
				options: `<p>${__("Create Delivery Note(s) for {0} Sales Order(s)?", [sales_orders.length])}</p>`,
			},
			{
				fieldname: "submit_after_create",
				fieldtype: "Check",
				label: __("Submit Delivery Note(s) after creation"),
				default: 0,
			},
		],
		primary_action_label: __("Create"),
		primary_action: function(values) {
			dialog.hide();
			_mis_run_create_dns(frm, sales_orders, values.submit_after_create);
		},
	});
	dialog.show();
}

// ── SI creation ─────────────────────────────────────────────────────────────

function _mis_run_create_si(frm, delivery_notes, submit_after_create) {
	const created = [];
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
							created.push(r.message.sales_invoice);
							frappe.show_alert({ message: __("Created {0}", [r.message.sales_invoice]), indicator: "green" });
						}
						resolve();
					}
				});
			});
		});
	});
	return promise
		.then(function() {
			if (!submit_after_create || !created.length) return;
			return new Promise(function(resolve) {
				frappe.call({
					method: "phamos.phamos.doctype.monthly_implementation_summary.monthly_implementation_summary.submit_sales_invoices_in_mis",
					args: { docname: frm.doc.name, sales_invoices: created },
					freeze: true,
					freeze_message: __("Submitting Sales Invoice(s)..."),
					callback: function(r) {
						const d = r.message || {};
						if (d.failed_details && d.failed_details.length) {
							frappe.msgprint({
								title: __("Some submissions failed"),
								indicator: "orange",
								message: d.failed_details
									.map(item => `${_mis_escape(item.sales_invoice || "")} : ${_mis_escape(item.error || "")}`)
									.join("<br>"),
							});
						}
						resolve();
					}
				});
			});
		})
		.then(function() { frm.reload_doc(); });
}

function _mis_create_si_for_dns(frm, delivery_notes) {
	if (!delivery_notes || !delivery_notes.length) return;
	const dialog = new frappe.ui.Dialog({
		title: __("Create Sales Invoice(s)"),
		fields: [
			{
				fieldname: "info",
				fieldtype: "HTML",
				options: `<p>${__("Create Sales Invoice(s) for {0} Delivery Note(s)?", [delivery_notes.length])}</p>`,
			},
			{
				fieldname: "submit_after_create",
				fieldtype: "Check",
				label: __("Submit Sales Invoice(s) after creation"),
				default: 0,
			},
		],
		primary_action_label: __("Create"),
		primary_action: function(values) {
			dialog.hide();
			_mis_run_create_si(frm, delivery_notes, values.submit_after_create);
		},
	});
	dialog.show();
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

function _mis_show_create_dn_dialog(frm) {
	const eligible = (frm.doc.sales_order_status_information || []).filter(
		r => r.sales_order && ["To Deliver", "To Deliver and Bill"].includes(r.status)
	);
	if (!eligible.length) {
		frappe.show_alert({ message: __("No Sales Orders available for delivery."), indicator: "orange" });
		return;
	}

	const rows_html = eligible.map(r => `
		<tr>
			<td style="width:36px; text-align:center;">
				<input type="checkbox" class="mis-dn-so-check" data-so="${_mis_escape(r.sales_order)}" checked>
			</td>
			<td><a href="/app/sales-order/${encodeURIComponent(r.sales_order || "")}" target="_blank">${_mis_escape(r.sales_order)}</a></td>
			<td>${_mis_escape(r.status || "")}</td>
			<td style="text-align:right;">${_mis_number(r.remaining_hrs)}</td>
		</tr>
	`).join("");

	const dialog = new frappe.ui.Dialog({
		title: __("Create Delivery Note"),
		fields: [
			{ fieldname: "so_list_html", fieldtype: "HTML" },
			{
				fieldname: "submit_after_create",
				fieldtype: "Check",
				label: __("Submit Delivery Note(s) after creation"),
				default: 0,
			},
		],
		primary_action_label: __("Create"),
		primary_action: function(values) {
			const selected = [];
			dialog.$wrapper.find(".mis-dn-so-check:checked").each(function() {
				const so = $(this).attr("data-so");
				if (so) selected.push(so);
			});
			if (!selected.length) {
				frappe.show_alert({ message: __("Select at least one Sales Order."), indicator: "orange" });
				return;
			}
			dialog.hide();
			_mis_run_create_dns(frm, selected, values.submit_after_create);
		},
	});

	dialog.get_field("so_list_html").$wrapper.html(`
		<table class="table table-bordered table-hover" style="margin-bottom:0;">
			<thead>
				<tr>
					<th style="width:36px;"><input type="checkbox" id="mis-dn-select-all" checked></th>
					<th>${__("Sales Order")}</th>
					<th>${__("Status")}</th>
					<th style="text-align:right;">${__("Remaining Hrs")}</th>
				</tr>
			</thead>
			<tbody>${rows_html}</tbody>
		</table>
	`);

	dialog.$wrapper.on("change", "#mis-dn-select-all", function() {
		dialog.$wrapper.find(".mis-dn-so-check").prop("checked", $(this).is(":checked"));
	});

	dialog.show();
}

function _mis_show_create_si_dialog(frm) {
	const eligible = (frm.doc.mis_delivery_notes || []).filter(
		r => r.delivery_note && r.status === "To Bill"
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
		fields: [
			{ fieldname: "dn_list_html", fieldtype: "HTML" },
			{
				fieldname: "submit_after_create",
				fieldtype: "Check",
				label: __("Submit Sales Invoice(s) after creation"),
				default: 0,
			},
		],
		primary_action_label: __("Create"),
		primary_action: function(values) {
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
			_mis_run_create_si(frm, selected, values.submit_after_create);
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


const _MIS_TS_COLUMNS = [
	{
		key: "timesheet",
		label: () => __("Timesheet"),
		sortable: true,
		locked: true,
		html: (row) => `<a href="/app/timesheet/${encodeURIComponent(row.timesheet || "")}" target="_blank">${_mis_escape(row.timesheet)}</a>`,
		sort_value: (row) => (row.timesheet || "").toLowerCase(),
		filter_value: (row) => row.timesheet || "",
	},
	{
		key: "date",
		label: () => __("Date"),
		sortable: true,
		html: (row) => _mis_escape(row.date),
		sort_value: (row) => row.date || "",
		filter_value: (row) => row.date || "",
	},
	{
		key: "employee_name",
		label: () => __("Employee"),
		sortable: true,
		html: (row) => _mis_escape(row.employee_name),
		sort_value: (row) => (row.employee_name || "").toLowerCase(),
		filter_value: (row) => row.employee_name || "",
	},
	{
		key: "project",
		label: () => __("Project"),
		sortable: true,
		html: (row) => _mis_escape(row.project),
		sort_value: (row) => (row.project || "").toLowerCase(),
		filter_value: (row) => row.project || "",
	},
	{
		key: "total_hours",
		label: () => __("Total"),
		sortable: true,
		numeric: true,
		html: (row) => _mis_number(row.total_hours),
		sort_value: (row) => flt(row.total_hours || 0),
		filter_value: (row) => String(row.total_hours || ""),
	},
	{
		key: "billable_hours",
		label: () => __("Billable"),
		sortable: true,
		numeric: true,
		is_billable_input: true,
		sort_value: (row, dialog) => flt(_mis_get_billable_override(dialog, row.timesheet, row.billable_hours)),
		filter_value: (row, dialog) => String(_mis_get_billable_override(dialog, row.timesheet, row.billable_hours)),
	},
	{
		key: "description",
		label: () => __("Description"),
		sortable: true,
		default_hidden: true,
		html: (row) => _mis_escape(row.description),
		sort_value: (row) => (row.description || "").toLowerCase(),
		filter_value: (row) => row.description || "",
	},
	{
		key: "rating",
		label: () => __("Rating"),
		sortable: true,
		default_hidden: true,
		html: (row) => _mis_escape(row.rating),
		sort_value: (row) => (row.rating || "").toLowerCase(),
		filter_value: (row) => row.rating || "",
	},
	{
		key: "status",
		label: () => __("Status"),
		sortable: true,
		is_status: true,
		sort_value: (row) => (row.status || "").toLowerCase(),
		filter_value: (row) => row.status || "",
	},
];

function _mis_ts_col_is_visible(dialog, col) {
	if (col.locked) return true;
	const visible = dialog.__mis_ts_visible_columns || {};
	if (Object.prototype.hasOwnProperty.call(visible, col.key)) return !!visible[col.key];
	return !col.default_hidden;
}

function _mis_visible_ts_columns(dialog) {
	return _MIS_TS_COLUMNS.filter((col) => _mis_ts_col_is_visible(dialog, col));
}

function _mis_get_billable_override(dialog, timesheet, fallback) {
	const overrides = (dialog && dialog.__mis_ts_billable_overrides) || {};
	if (Object.prototype.hasOwnProperty.call(overrides, timesheet)) {
		return overrides[timesheet];
	}
	return flt(fallback || 0);
}

function _mis_timesheet_row_html(dialog, row, columns) {
	const pending = _mis_is_timesheet_pending(row);
	const can_select = pending && row.timesheet;
	const badge_class = pending ? "orange" : "green";
	const badge_label = pending ? __("Pending") : __("Approved");
	const selected = (dialog.__mis_ts_selected || new Set()).has(row.timesheet);

	const cells = columns
		.map((col) => {
			const css = col.numeric ? ' class="mis-ts-col-num"' : "";
			if (col.is_billable_input) {
				const value = _mis_get_billable_override(dialog, row.timesheet, row.billable_hours);
				return `<td${css} data-column="${col.key}">
					<input
						type="text"
						inputmode="decimal"
						class="mis-ts-billable-input"
						data-timesheet="${_mis_escape(row.timesheet)}"
						value="${_mis_escape(value)}"
						style="width:92px; text-align:right;"
					>
				</td>`;
			}
			if (col.is_status) {
				return `<td data-column="${col.key}"><span class="indicator-pill ${badge_class}">${badge_label}</span></td>`;
			}
			return `<td${css} data-column="${col.key}">${col.html(row)}</td>`;
		})
		.join("");

	return `
		<tr>
			<td class="mis-ts-col-check">
				<input type="checkbox" class="mis-ts-select" data-timesheet="${_mis_escape(row.timesheet)}" ${can_select ? "" : "disabled"} ${selected ? "checked" : ""}>
			</td>
			${cells}
			<td class="mis-ts-col-gear"></td>
		</tr>
	`;
}

function _mis_render_timesheet_approval_table(dialog, rows) {
	const html_field = dialog.get_field("timesheet_approval_html");
	if (!html_field || !html_field.$wrapper) return;

	const columns = _mis_visible_ts_columns(dialog);
	const sort = dialog.__mis_ts_sort || {};

	let display_rows = [...(rows || [])];
	if (sort.column) {
		const col = _MIS_TS_COLUMNS.find((c) => c.key === sort.column);
		if (col) {
			display_rows.sort((a, b) => {
				const av = col.sort_value(a, dialog);
				const bv = col.sort_value(b, dialog);
				if (av < bv) return sort.direction === "desc" ? 1 : -1;
				if (av > bv) return sort.direction === "desc" ? -1 : 1;
				return 0;
			});
		}
	} else {
		display_rows.sort(
			(a, b) =>
				flt(_mis_get_billable_override(dialog, b.timesheet, b.billable_hours)) -
				flt(_mis_get_billable_override(dialog, a.timesheet, a.billable_hours))
		);
	}

	const table_rows = display_rows.map((row) => _mis_timesheet_row_html(dialog, row, columns)).join("");

	const header_cells = columns
		.map((col) => {
			const css = col.numeric ? ' class="mis-ts-col-num"' : "";
			if (!col.sortable) {
				return `<th${css}>${col.label()}</th>`;
			}
			const arrow = sort.column === col.key ? (sort.direction === "desc" ? " &#9660;" : " &#9650;") : "";
			return `<th${css} data-sort-column="${col.key}" style="cursor:pointer; user-select:none;">${col.label()}${arrow}</th>`;
		})
		.join("");

	const filters = dialog.__mis_ts_column_filters || {};
	const filter_cells = columns
		.map(
			(col) => `
				<th>
					<input
						type="text"
						class="form-control input-sm mis-ts-column-filter"
						data-column="${col.key}"
						value="${_mis_escape(filters[col.key] || "")}"
					>
				</th>
			`
		)
		.join("");

	const gear_options = _MIS_TS_COLUMNS.filter((c) => !c.locked)
		.map((col) => {
			const checked = _mis_ts_col_is_visible(dialog, col) ? "checked" : "";
			return `
				<label class="mis-ts-gear-option">
					<input type="checkbox" class="mis-ts-column-toggle" data-column="${col.key}" ${checked}>
					${col.label()}
				</label>
			`;
		})
		.join("");

	html_field.$wrapper.html(`
		<style>
			.mis-ts-wrap .mis-ts-note { margin-bottom: 8px; }
			.mis-ts-wrap .mis-ts-col-check { width: 36px; text-align: center; }
			.mis-ts-wrap .mis-ts-col-num { text-align: right; }
			.mis-ts-wrap .mis-ts-col-gear { width: 34px; text-align: center; position: relative; }
			.mis-ts-wrap table { margin-bottom: 0; border: 1px solid var(--border-color); }
			.mis-ts-wrap .mis-ts-column-filter-row th { background: var(--bg-color); padding: 4px; }
			.mis-ts-wrap .mis-ts-column-filter { width: 100%; font-size: 12px; }
			.mis-ts-wrap .mis-ts-gear-btn {
				display: inline-flex;
				align-items: center;
				justify-content: center;
				width: 22px;
				height: 22px;
				border-radius: 4px;
				cursor: pointer;
				color: var(--text-muted);
			}
			.mis-ts-wrap .mis-ts-gear-btn:hover { background: var(--bg-color); color: var(--text-color); }
			.mis-ts-wrap .mis-ts-gear-panel {
				display: none;
				position: absolute;
				right: 0;
				top: 100%;
				z-index: 10;
				text-align: left;
				background: var(--fg-color, var(--bg-color));
				border: 1px solid var(--border-color);
				border-radius: 6px;
				padding: 6px 4px;
				box-shadow: var(--shadow-md, 0 2px 8px rgba(0,0,0,.25));
				min-width: 170px;
			}
			.mis-ts-wrap .mis-ts-gear-panel-title {
				font-size: 11px;
				text-transform: uppercase;
				color: var(--text-muted);
				padding: 4px 10px;
			}
			.mis-ts-wrap .mis-ts-gear-option {
				display: flex;
				align-items: center;
				gap: 8px;
				font-weight: 400;
				padding: 5px 10px;
				margin: 0;
				border-radius: 4px;
				cursor: pointer;
			}
			.mis-ts-wrap .mis-ts-gear-option:hover { background: var(--bg-color); }
		</style>
		<div class="mis-ts-wrap">
		<div class="small text-muted mis-ts-note">
			${__("Review and submit pending timesheets for this MIS period.")}
		</div>
		<table class="table table-bordered table-hover">
			<thead>
				<tr>
					<th class="mis-ts-col-check"><input type="checkbox" id="mis-ts-select-all"></th>
					${header_cells}
					<th class="mis-ts-col-gear">
						<span class="mis-ts-gear-btn" id="mis-ts-gear-btn" title="${__("Pick Columns")}">${frappe.utils.icon("setting-gear", "sm")}</span>
						<div class="mis-ts-gear-panel" id="mis-ts-gear-panel" style="${dialog.__mis_ts_gear_open ? "display:block;" : ""}">
							<div class="mis-ts-gear-panel-title">${__("Pick Columns")}</div>
							${gear_options}
						</div>
					</th>
				</tr>
				<tr class="mis-ts-column-filter-row">
					<th></th>
					${filter_cells}
					<th></th>
				</tr>
			</thead>
			<tbody>
				${table_rows || `<tr><td colspan="${columns.length + 2}" class="text-muted text-center">${__("No timesheets found.")}</td></tr>`}
			</tbody>
		</table>
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
function _mis_apply_ts_column_filters(dialog) {
	const filters = dialog.__mis_ts_column_filters || {};
	const active_columns = Object.keys(filters).filter((k) => filters[k]);

	dialog.$wrapper.find(".mis-ts-wrap tbody tr").each(function () {
		const $row = $(this);
		if (!$row.find(".mis-ts-select").length) return;

		const matches = active_columns.every((column) => {
			let value;
			if (column === "billable_hours") {
				value = String($row.find(".mis-ts-billable-input").val() || "");
			} else {
				value = String($row.find(`td[data-column="${column}"]`).text() || "");
			}
			return value.trim().toLowerCase().includes(filters[column]);
		});

		$row.toggle(matches);
	});
}

function _mis_rerender_ts_table(frm, dialog) {
	_mis_render_timesheet_approval_table(dialog, dialog.__mis_ts_rows);
	_mis_bind_timesheet_approval_dialog_events(frm, dialog);
	_mis_apply_ts_column_filters(dialog);
}

function _mis_bind_timesheet_approval_dialog_events(frm, dialog) {

	dialog.$wrapper.off("change", "#mis-ts-select-all");
	dialog.$wrapper.on("change", "#mis-ts-select-all", function () {
		const checked = !!$(this).is(":checked");
		dialog.__mis_ts_selected = dialog.__mis_ts_selected || new Set();
		dialog.$wrapper.find(".mis-ts-select:not(:disabled)").filter(":visible").each(function () {
			$(this).prop("checked", checked);
			const ts = $(this).attr("data-timesheet");
			if (!ts) return;
			if (checked) dialog.__mis_ts_selected.add(ts);
			else dialog.__mis_ts_selected.delete(ts);
		});
	});

	dialog.$wrapper.off("change", ".mis-ts-select");
	dialog.$wrapper.on("change", ".mis-ts-select", function () {
		const ts = $(this).attr("data-timesheet");
		if (!ts) return;
		dialog.__mis_ts_selected = dialog.__mis_ts_selected || new Set();
		if ($(this).is(":checked")) dialog.__mis_ts_selected.add(ts);
		else dialog.__mis_ts_selected.delete(ts);
	});

	dialog.$wrapper.off("input", ".mis-ts-billable-input");
	dialog.$wrapper.on("input", ".mis-ts-billable-input", function () {
		const ts = $(this).attr("data-timesheet");
		if (!ts) return;
		dialog.__mis_ts_billable_overrides = dialog.__mis_ts_billable_overrides || {};
		dialog.__mis_ts_billable_overrides[ts] = $(this).val();
	});

	dialog.$wrapper.off("click", "[data-sort-column]");
	dialog.$wrapper.on("click", "[data-sort-column]", function () {
		const column = $(this).attr("data-sort-column");
		const current = dialog.__mis_ts_sort || {};
		let direction = "asc";
		if (current.column === column) {
			direction = current.direction === "asc" ? "desc" : current.direction === "desc" ? null : "asc";
		}
		dialog.__mis_ts_sort = direction ? { column, direction } : {};
		_mis_rerender_ts_table(frm, dialog);
	});


	dialog.$wrapper.off("input", ".mis-ts-column-filter");
	dialog.$wrapper.on("input", ".mis-ts-column-filter", function () {
		const column = $(this).attr("data-column");
		const value = String($(this).val() || "").trim().toLowerCase();
		dialog.__mis_ts_column_filters = dialog.__mis_ts_column_filters || {};
		if (value) dialog.__mis_ts_column_filters[column] = value;
		else delete dialog.__mis_ts_column_filters[column];
		_mis_apply_ts_column_filters(dialog);
	});


	dialog.$wrapper.off("click", "#mis-ts-gear-btn");
	dialog.$wrapper.on("click", "#mis-ts-gear-btn", function (e) {
		e.stopPropagation();
		dialog.__mis_ts_gear_open = !dialog.__mis_ts_gear_open;
		dialog.$wrapper.find("#mis-ts-gear-panel").toggle(dialog.__mis_ts_gear_open);
	});

	dialog.$wrapper.off("change", ".mis-ts-column-toggle");
	dialog.$wrapper.on("change", ".mis-ts-column-toggle", function () {
		const column = $(this).attr("data-column");
		dialog.__mis_ts_visible_columns = dialog.__mis_ts_visible_columns || {};
		dialog.__mis_ts_visible_columns[column] = $(this).is(":checked");
		dialog.__mis_ts_gear_open = true;
		_mis_rerender_ts_table(frm, dialog);
	});

	dialog.$wrapper.off("click.mis-ts-gear-outside");
	dialog.$wrapper.on("click.mis-ts-gear-outside", function (e) {
		if (!$(e.target).closest("#mis-ts-gear-btn, .mis-ts-gear-panel").length) {
			dialog.__mis_ts_gear_open = false;
			dialog.$wrapper.find("#mis-ts-gear-panel").hide();
		}
	});
}

function _mis_load_timesheet_approval_rows(frm, dialog) {
	_mis_render_timesheet_loading_state(dialog);
	return frappe.call({
		method: "phamos.phamos.doctype.monthly_implementation_summary.monthly_implementation_summary.get_timesheet_approval_rows",
		args: {
			docname: frm.doc.name,
		},
		freeze: false,
	}).then((r) => {
		dialog.__mis_ts_rows = (r && r.message) || [];
		dialog.__mis_ts_original_billable = {};
		dialog.__mis_ts_billable_overrides = {};
		dialog.__mis_ts_rows.forEach((row) => {
			if (row && row.timesheet) {
				dialog.__mis_ts_original_billable[row.timesheet] = flt(row.billable_hours || 0);
			}
		});
		_mis_rerender_ts_table(frm, dialog);
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
		secondary_action_label: __("Submit"),
		secondary_action: () => {
			_mis_submit_selected_timesheets(frm, dialog).then((ok) => {
				if (ok) dialog.hide();
			});
		},
		primary_action: () => {
			_mis_save_billable_changes(frm, dialog);
		},
	});

	dialog.__mis_ts_selected = new Set();
	dialog.__mis_ts_billable_overrides = {};
	dialog.__mis_ts_column_filters = {};
	dialog.__mis_ts_sort = {};
	dialog.__mis_ts_visible_columns = {};
	dialog.__mis_ts_gear_open = false;
	dialog.show();
	dialog.$wrapper.find(".modal-dialog").css("max-width", "1180px");
	const $footer = dialog.$wrapper.find(".modal-footer");
	const $action_btns = $footer.find(".btn-primary, .btn-secondary, .btn-default");
	$action_btns.css({
		background: "#111",
		color: "#fff",
		borderColor: "#111",
		fontWeight: "700",
	});
	_mis_load_timesheet_approval_rows(frm, dialog);
}

function _mis_maybe_open_timesheet_approval_dialog(frm) {
	if (frm.is_new() || !frm.doc.name) return;
	if (!Array.isArray(frm.doc.timesheets_table) || !frm.doc.timesheets_table.length) return;
	if (frm.__mis_timesheet_dialog_opened_for === frm.doc.name) return;
	frm.__mis_timesheet_dialog_opened_for = frm.doc.name;
	setTimeout(() => {
		_mis_show_timesheet_approval_dialog(frm);
	}, 250);
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
			_mis_setup_status_buttons(frm);
			const not_closed = frm.doc.status !== "Closed";
			const has_deliverable_so = not_closed && (frm.doc.sales_order_status_information || []).some(
				r => r.sales_order && ["To Deliver", "To Deliver and Bill"].includes(r.status)
			);
			if (has_deliverable_so) {
				frm.add_custom_button(__("Create Delivery Note"), function() {
					_mis_show_create_dn_dialog(frm);
				}, __("Actions"));
			}
			const has_billable_dns = not_closed && (frm.doc.mis_delivery_notes || []).some(
				r => r.delivery_note && r.status === "To Bill"
			);
			if (has_billable_dns) {
				frm.add_custom_button(__("Create Sales Invoice"), function() {
					_mis_show_create_si_dialog(frm);
				}, __("Actions"));
			}
		}
		_mis_maybe_open_timesheet_approval_dialog(frm);
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
