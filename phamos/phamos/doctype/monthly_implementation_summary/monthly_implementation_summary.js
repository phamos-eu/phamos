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
	create_delivery_note: function(frm) {
		frappe.call({
			method: "phamos.phamos.doctype.monthly_implementation_summary.monthly_implementation_summary.create_delivery_note",
			args: {
				docname: frm.doc.name,
				sales_order: frm.doc.sales_order || null,
				delivery_note_item: frm.doc.delivery_note_item || []
			},
			freeze: true,
			freeze_message: __("Creating delivery note..."),
			callback: function(r) {
				if (r.exc) {
					frappe.msgprint({
						title: __("Error"),
						message: r.exc[0] || __("Failed to create delivery note."),
						indicator: "red"
					});
					return;
				}
				const msg = r.message && r.message.dn_name;
				if (msg) {
					frappe.msgprint({
						title: __('Success'),
						indicator: 'green',
						message: __('Delivery Note {0} created and items synced to Delivery Note Item table.', [msg])
					});
					frm.reload_doc();
				} else {
					frappe.msgprint(__("Failed to create Delivery Note. Please try again."));
				}
			}
		});
	},
	refresh: function(frm) {
		if (frm.doc.delivery_note) {
            add_custom_links("delivery_note", "Delivery Note", frm.doc.delivery_note);
        }
		if (frm.is_new()) {
			frm.doc.delivery_note='';
			frm.refresh_field('delivery_note');
			const d = new Date();
			const months = ["January", "February", "March", "April", "May", "June", "July", "August", "September", "October", "November", "December"];
			const defaults = {
				sales_order: null,
				delivery_note: null,
				year: String(d.getFullYear()),
				month: months[d.getMonth()],
				delivery_note_item: [],
				timesheets_table: [],
				total_hours: 0,
				billable_hours: 0
			};
			Object.keys(defaults).forEach(k => { frm.set_value(k, defaults[k]); });
			return;
		}
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