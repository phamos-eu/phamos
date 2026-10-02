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
			_mis_show_create_dn_dialog(frm, deliverable);
		}
	);
}

function _mis_setup_ts_table_create_dn_btn(frm) {
	const field = frm.fields_dict.timesheets_table;
	if (!field || !field.grid) return;

	_mis_inject_grid_button(
		field.grid,
		"mis-ts-create-dn-btn",
		__("Create Delivery Note"),
		function(selected) {
			return !frm.is_new() && !frm.is_dirty() && selected.length > 0;
		},
		function(selected) {
			const timesheets = selected.map(r => r.timesheet).filter(Boolean);
			if (!timesheets.length) {
				frappe.show_alert({ message: __("Selected rows have no Timesheet."), indicator: "orange" });
				return;
			}
			_mis_show_create_dn_dialog(frm, null, timesheets);
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
	_mis_setup_ts_table_create_dn_btn(frm);
	_mis_setup_dn_table_submit_btn(frm);
	_mis_setup_si_table_submit_btn(frm);
}

function _mis_setup_status_buttons(frm) {
	if (!frm.has_perm("submit")) return;
	if (frm.doc.status === "Closed") {
		frm.add_custom_button(__("Re-open"), function() {
			frappe.call({
				method: "phamos.phamos.doctype.monthly_implementation_summary.monthly_implementation_summary.set_mis_open_status",
				args: { docname: frm.doc.name, closed: 0 },
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
						method: "phamos.phamos.doctype.monthly_implementation_summary.monthly_implementation_summary.set_mis_open_status",
						args: { docname: frm.doc.name, closed: 1 },
						freeze: true,
						callback: function() { frm.reload_doc(); },
					});
				}
			);
		}, __("Status"));
	}
}

// ── DN creation ─────────────────────────────────────────────────────────────

function _mis_run_create_dn_allocation(frm, allocations, submit_after_create, timesheets, project) {
	const non_zero = allocations.filter(a => (a.items || []).length);
	if (!non_zero.length) {
		frappe.show_alert({ message: __("No hours were allocated to any Sales Order."), indicator: "orange" });
		return Promise.resolve();
	}
	const has_timesheets = timesheets && timesheets.length;
	const method = has_timesheets ? "create_dns_from_timesheet_allocations" : "create_dns_from_allocations";
	const args = has_timesheets
		? { docname: frm.doc.name, timesheets: timesheets, project: project, allocations: non_zero }
		: { docname: frm.doc.name, project: project, allocations: non_zero };
	return new Promise(function(resolve) {
		frappe.call({
			method: `phamos.phamos.doctype.monthly_implementation_summary.monthly_implementation_summary.${method}`,
			args: args,
			freeze: true,
			freeze_message: __("Creating Delivery Note(s)..."),
			callback: function(r) {
				if (r.exc) {
					frappe.msgprint({ title: __("Error"), message: r.exc[0] || __("Failed to create Delivery Note(s)."), indicator: "red" });
					resolve();
					return;
				}
				const created = (r.message && r.message.created) || [];
				created.forEach(dn => frappe.show_alert({ message: __("Created {0}", [dn]), indicator: "green" }));
				if (submit_after_create && created.length) {
					frappe.call({
						method: "phamos.phamos.doctype.monthly_implementation_summary.monthly_implementation_summary.submit_delivery_notes_in_mis",
						args: { docname: frm.doc.name, delivery_notes: created },
						freeze: true,
						freeze_message: __("Submitting Delivery Note(s)..."),
						callback: function(sr) {
							const d = sr.message || {};
							if (d.failed_details && d.failed_details.length) {
								frappe.msgprint({
									title: __("Some submissions failed"),
									indicator: "orange",
									message: d.failed_details
										.map(item => `${_mis_escape(item.delivery_note || "")} : ${_mis_escape(item.error || "")}`)
										.join("<br>"),
								});
							}
							frm.reload_doc();
							resolve();
						}
					});
					return;
				}
				frm.reload_doc();
				resolve();
			}
		});
	});
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

function _mis_build_so_items_map(rows) {
	const map = {};
	rows.forEach(r => {
		map[r.sales_order] = { project: r.project || "", items: r.items || [] };
	});
	return map;
}

function _mis_default_allocation_row(sales_order, so_items_map) {
	const entry = so_items_map[sales_order] || { project: "", items: [] };
	return {
		sales_order,
		project: entry.project,
		so_remaining_hrs: flt(entry.items.reduce((s, i) => s + flt(i.remaining_qty), 0), 2),
		hours: flt(entry.items.reduce((s, i) => s + flt(i.allocated_hours || 0), 0), 2),
	};
}

function _mis_split_hours_across_items(items, hours) {
	let left = flt(hours);
	const out = [];
	for (const item of items) {
		if (left <= 0) break;
		const alloc = flt(Math.min(flt(item.remaining_qty), left), 2);
		if (alloc > 0) {
			out.push({ so_detail: item.so_detail, hours: alloc });
			left = flt(left - alloc, 2);
		}
	}
	return out;
}

function _mis_reset_dn_allocation_row(dialog, rows_data, idx, so_items_map) {
	const row = rows_data.find(r => r.idx === idx);
	if (!row) return;
	Object.assign(row, _mis_default_allocation_row(row.sales_order, so_items_map));
	dialog.fields_dict.allocations.grid.refresh();
}

function _mis_load_dn_allocation_rows(frm, dialog, project, preset_sales_orders, timesheets, state) {
	if (!project) return;
	const method = state.has_timesheets ? "get_dn_allocation_preview_for_timesheets" : "get_dn_allocation_preview";
	const args = state.has_timesheets
		? { docname: frm.doc.name, project: project, timesheets: timesheets }
		: { docname: frm.doc.name, project: project, sales_orders: preset_sales_orders && preset_sales_orders.length ? preset_sales_orders : null };
	frappe.call({
		method: `phamos.phamos.doctype.monthly_implementation_summary.monthly_implementation_summary.${method}`,
		args: args,
		freeze: true,
		callback: function(r) {
			const data = r.message || {};
			const rows = data.rows || [];
			const pool = state.has_timesheets ? flt(data.selected_hours) : flt(data.remaining_hours);

			state.so_items_map = _mis_build_so_items_map(rows);
			state.draft_hours_by_so = {};
			rows.forEach(row => { state.draft_hours_by_so[row.sales_order] = flt(row.existing_draft_hours); });
			dialog.__mis_state = { project, pool };

			state.rows_data.length = 0;
			rows.forEach(row => state.rows_data.push(_mis_default_allocation_row(row.sales_order, state.so_items_map)));
			dialog.fields_dict.allocations.grid.refresh();

			const note = state.has_timesheets
				? `<br>${__("If the selected hours exceed a Sales Order's remaining hours, a separate Delivery Note will be created for the remainder.")}`
				: "";
			dialog.get_field("pool_html").$wrapper.html(
				`<div class="small text-muted">${state.pool_label}: <strong>${_mis_number(pool)}</strong>${note}</div>`
			);
		}
	});
}

function _mis_show_create_dn_dialog(frm, preset_sales_orders, timesheets) {
	const has_timesheets = timesheets && timesheets.length;
	frappe.call({
		method: "phamos.phamos.doctype.monthly_implementation_summary.monthly_implementation_summary.get_dn_allocation_project_summary",
		args: { docname: frm.doc.name, timesheets: has_timesheets ? timesheets : null },
		freeze: true,
		callback: function(r) {
			const projects = (r.message && r.message.rows) || [];
			if (!projects.length) {
				frappe.show_alert({ message: __("No Project hours available for delivery."), indicator: "orange" });
				return;
			}

			const state = {
				rows_data: [],
				so_items_map: {},
				draft_hours_by_so: {},
				has_timesheets: has_timesheets,
				pool_label: has_timesheets ? __("Selected Timesheet hours") : __("Remaining billable hours"),
			};

			const dialog = new frappe.ui.Dialog({
				title: __("Create Delivery Note(s)"),
				size: "large",
				fields: [
					{
						fieldname: "project",
						fieldtype: "Link",
						options: "Project",
						label: __("Project"),
						reqd: 1,
						get_query: () => ({ filters: { name: ["in", projects.map(p => p.project)] } }),
						onchange: function() {
							_mis_load_dn_allocation_rows(frm, dialog, this.value, preset_sales_orders, timesheets, state);
						},
					},
					{ fieldname: "pool_html", fieldtype: "HTML" },
					{
						fieldname: "allocations",
						fieldtype: "Table",
						label: __("Sales Orders"),
						cannot_add_rows: true,
						cannot_delete_rows: true,
						in_place_edit: false,
						reqd: 1,
						data: state.rows_data,
						get_data: () => state.rows_data,
						fields: [
							{
								fieldname: "sales_order",
								fieldtype: "Link",
								options: "Sales Order",
								label: __("Sales Order"),
								in_list_view: 1,
								reqd: 1,
								get_query: () => ({ filters: { name: ["in", Object.keys(state.so_items_map)] } }),
								onchange: function() {
									_mis_reset_dn_allocation_row(dialog, state.rows_data, this.doc.idx, state.so_items_map);
								},
							},
							{ fieldname: "project", fieldtype: "Data", label: __("Project"), in_list_view: 1, read_only: 1 },
							{ fieldname: "so_remaining_hrs", fieldtype: "Float", label: __("Remaining Hrs"), in_list_view: 1, read_only: 1, precision: 2 },
							{ fieldname: "hours", fieldtype: "Float", label: __("Hours to Deliver"), in_list_view: 1, reqd: 1, precision: 2 },
						],
					},
				],
				primary_action_label: __("Create"),
				primary_action: function() {
					const dstate = dialog.__mis_state;
					if (!dstate || !dstate.project) {
						frappe.show_alert({ message: __("Select a Project first."), indicator: "orange" });
						return;
					}
					const items_by_so = {};
					let total = 0;
					let invalid = null;

					state.rows_data.forEach(row => {
						if (!row.sales_order) return;
						const hours = flt(row.hours);
						if (hours <= 0) return;
						if (hours > flt(row.so_remaining_hrs) + 0.0001) {
							invalid = row.sales_order;
							return;
						}
						const entry = state.so_items_map[row.sales_order] || { items: [] };
						total += hours;
						items_by_so[row.sales_order] = _mis_split_hours_across_items(entry.items, hours);
					});

					if (invalid) {
						frappe.show_alert({
							message: __("Hours for {0} must be between 0 and its remaining hours.", [invalid]),
							indicator: "orange",
						});
						return;
					}
					if (total > dstate.pool + 0.0001) {
						frappe.show_alert({
							message: __("Total allocated hours ({0}) exceed remaining hours for this Project ({1}).", [total, dstate.pool]),
							indicator: "orange",
						});
						return;
					}
					const allocations = Object.keys(items_by_so).map(so => ({ sales_order: so, items: items_by_so[so] }));
					if (!allocations.length) {
						frappe.show_alert({ message: __("Assign hours to at least one Sales Order."), indicator: "orange" });
						return;
					}

					const draft_conflicts = Object.keys(items_by_so)
						.filter(so => flt(state.draft_hours_by_so[so]) > 0)
						.map(so => ({ sales_order: so, draft_hrs: flt(state.draft_hours_by_so[so]) }));

					const proceed = function() {
						dialog.hide();
						_mis_run_create_dn_allocation(frm, allocations, false, timesheets, dstate.project);
					};

					if (draft_conflicts.length) {
						const list = draft_conflicts
							.map(c => __("{0} (existing draft: {1} hrs)", [c.sales_order, _mis_number(c.draft_hrs)]))
							.join(", ");
						frappe.confirm(
							__("Draft Delivery Note(s) already exist for: {0}. Create new Delivery Note(s) anyway?", [list]),
							proceed
						);
						return;
					}

					proceed();
				},
			});

			dialog.show();
			dialog.set_value("project", projects[0].project);
		}
	});
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

function _mis_get_selected_timesheets(dialog) {
	return dialog.fields_dict.timesheet_approval.grid
		.get_selected_children()
		.map((row) => row.timesheet)
		.filter(Boolean);
}

function _mis_get_billable_updates(dialog) {
	const originals = dialog.__mis_ts_original_billable || {};
	return dialog.__mis_ts_rows
		.filter((row) => row.timesheet && Math.abs(flt(row.billable_hours) - flt(originals[row.timesheet])) >= 0.0001)
		.map((row) => ({ timesheet: row.timesheet, billable_hours: flt(row.billable_hours) }));
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
function _mis_fit_ts_column_widths(grid) {
	const shown = grid.docfields.filter((df) => cint(df.in_list_view));
	shown.forEach((df) => { df.columns = df.default_columns; });
	let total = shown.reduce((sum, df) => sum + df.columns, 0);
	// The grid drops columns once widths add up to more than 10
	while (total > 10) {
		const widest = shown.reduce((a, b) => (b.columns > a.columns ? b : a));
		if (widest.columns <= 1) break;
		widest.columns -= 1;
		total -= 1;
	}
}

function _mis_setup_ts_column_picker(grid) {
	grid.docfields.forEach((df) => { df.default_columns = df.columns; });
	const open_picker = () => {
		const picker = new frappe.ui.Dialog({
			title: __("Pick Columns"),
			fields: [{
				fieldname: "columns",
				fieldtype: "MultiCheck",
				columns: 2,
				options: grid.docfields.map((df) => ({
					label: df.label,
					value: df.fieldname,
					checked: cint(df.in_list_view),
				})),
			}],
			primary_action_label: __("Update"),
			primary_action: (values) => {
				const chosen = values.columns || [];
				if (!chosen.length) return;
				grid.docfields.forEach((df) => { df.in_list_view = chosen.includes(df.fieldname) ? 1 : 0; });
				_mis_fit_ts_column_widths(grid);
				grid.reset_grid();
				picker.hide();
			},
		});
		picker.show();
	};

	// The native gear cell is empty for grids outside a form, so the gear is placed in it after each header build
	const make_head = grid.make_head.bind(grid);
	grid.make_head = function () {
		make_head();
		const $cell = grid.header_row && grid.header_row.configure_columns_button;
		if (!$cell || $cell.children().length) return;
		$cell
			.css({ cursor: "pointer", display: "flex", justifyContent: "center" })
			.attr("title", __("Pick Columns"))
			.html(`<a>${frappe.utils.icon("setting-gear", "sm", "", "filter: opacity(0.5)")}</a>`)
			.on("click", open_picker);
	};
	grid.refresh();
}

function _mis_bind_ts_header_sort(grid, rows) {
	let sort = {};
	grid.wrapper.on("click", ".grid-heading-row .grid-row:not(.filter-row) [data-fieldname]", function () {
		const df = $(this).data("df");
		if (!df) return;
		const direction = sort.fieldname === df.fieldname && sort.direction === "asc" ? "desc" : "asc";
		sort = { fieldname: df.fieldname, direction };
		const factor = direction === "asc" ? 1 : -1;
		const is_number = df.fieldtype === "Float";
		rows.sort((a, b) =>
			factor * (is_number
				? flt(a[df.fieldname]) - flt(b[df.fieldname])
				: String(a[df.fieldname] || "").localeCompare(String(b[df.fieldname] || "")))
		);
		grid.refresh();
	});
}

function _mis_load_timesheet_approval_rows(frm, dialog) {
	return frappe.call({
		method: "phamos.phamos.doctype.monthly_implementation_summary.monthly_implementation_summary.get_timesheet_approval_rows",
		args: {
			docname: frm.doc.name,
		},
		freeze: false,
	}).then((r) => {
		const rows = (r && r.message) || [];
		dialog.__mis_ts_original_billable = {};
		rows.forEach((row) => {
			if (row.timesheet) {
				dialog.__mis_ts_original_billable[row.timesheet] = flt(row.billable_hours);
			}
		});
		dialog.__mis_ts_rows.length = 0;
		rows.sort((a, b) => flt(b.billable_hours) - flt(a.billable_hours));
		rows.forEach((row) => dialog.__mis_ts_rows.push(row));
		dialog.fields_dict.timesheet_approval.grid.refresh();
	});
}

function _mis_show_timesheet_approval_dialog(frm) {
	const rows = [];
	const dialog = new frappe.ui.Dialog({
		title: __("Timesheet Approval"),
		size: "extra-large",
		fields: [
			{
				fieldname: "timesheet_approval",
				fieldtype: "Table",
				label: __("Timesheets"),
				description: __("Review and submit pending timesheets for this MIS period."),
				cannot_add_rows: true,
				cannot_delete_rows: true,
				in_place_edit: false,
				data: rows,
				get_data: () => rows,
				fields: [
					{ fieldname: "timesheet", fieldtype: "Link", options: "Timesheet", label: __("Timesheet"), in_list_view: 1, read_only: 1, columns: 2 },
					{ fieldname: "date", fieldtype: "Date", label: __("Date"), in_list_view: 1, read_only: 1, columns: 1 },
					{ fieldname: "employee_name", fieldtype: "Data", label: __("Employee"), in_list_view: 1, read_only: 1, columns: 2 },
					{ fieldname: "project", fieldtype: "Data", label: __("Project"), in_list_view: 1, read_only: 1, columns: 1 },
					{ fieldname: "total_hours", fieldtype: "Float", label: __("Total"), in_list_view: 1, read_only: 1, precision: 2, columns: 1 },
					{ fieldname: "billable_hours", fieldtype: "Float", label: __("Billable"), in_list_view: 1, precision: 2, columns: 1 },
					{ fieldname: "description", fieldtype: "Data", label: __("Description"), in_list_view: 1, read_only: 1, columns: 2 },
					{ fieldname: "rating", fieldtype: "Data", label: __("Rating"), read_only: 1, columns: 1 },
					{ fieldname: "delivery_note", fieldtype: "Link", options: "Delivery Note", label: __("Delivery Note"), read_only: 1, columns: 2 },
				],
			},
		],
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

	dialog.__mis_ts_rows = rows;
	dialog.__mis_ts_original_billable = {};
	const grid = dialog.fields_dict.timesheet_approval.grid;
	// A grid inside a dialog has no meta; this shows the column search row at any row count
	grid.meta = { editable_grid: 1, rows_threshold_for_grid_search: 1 };
	_mis_bind_ts_header_sort(grid, rows);
	_mis_setup_ts_column_picker(grid);
	dialog.show();
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
		if (cint(frm.doc.docstatus) === 1 || cint(frm.doc.docstatus) === 0) {
			_mis_setup_status_buttons(frm);
			const not_closed = frm.doc.status !== "Closed";
			const has_deliverable_so = not_closed && (frm.doc.sales_order_status_information || []).some(
				r => r.sales_order && ["To Deliver", "To Deliver and Bill"].includes(r.status)
			);
			if (has_deliverable_so) {
				frm.add_custom_button(__("Delivery Note"), function() {
					_mis_show_create_dn_dialog(frm);
				}, __("Create"));
			}
			const has_billable_dns = not_closed && (frm.doc.mis_delivery_notes || []).some(
				r => r.delivery_note && r.status === "To Bill"
			);
			if (has_billable_dns) {
				frm.add_custom_button(__("Sales Invoice"), function() {
					_mis_show_create_si_dialog(frm);
				}, __("Create"));
			}
		}
		_mis_maybe_open_timesheet_approval_dialog(frm);
	},
	on_submit: function(frm) {
		frm.reload_doc();
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