// Copyright (c) 2026, phamos.eu and contributors
// For license information, please see license.txt

frappe.ui.form.on("Monthly Implementation Summery", {
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
	create_delivery_note: function(frm) {
		if (!frm.doc.sales_order) {
			frappe.msgprint(__("Please select a Sales Order before creating a Delivery Note."));
			return;
		}
		
		frappe.call({
			method: "phamos.phamos.doctype.monthly_implementation_summery.monthly_implementation_summery.create_delivery_note",
			args: {
				docname: frm.doc.name,
				sales_order: frm.doc.sales_order
			},
			callback: function(r) {
				if (r.message) {
					frappe.msgprint({
						title: __('Success'),
						indicator: 'green',
						message: __('Delivery Note {0} created successfully', [r.message])
					});
					setTimeout(() => {
						frm.reload_doc();
					}, 500);
				} else {
					frappe.msgprint(__("Failed to create Delivery Note. Please try again."));
				}
			}
		});
	},
	refresh: function(frm) {
		// Add Sales Orders to connections dashboard
		if (frm.doc.implementation) {
			frappe.db.get_list('Sales Order', {
				filters: {
					custom_implementation: frm.doc.implementation
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
	
	discount(frm) {
		// Validate discount is between 0 and 100
		if (frm.doc.discount !== undefined && frm.doc.discount !== null) {
			const discount = parseFloat(frm.doc.discount);
			if (isNaN(discount)) {
				frappe.msgprint(__("Discount must be a valid number."));
				frm.set_value("discount", null);
				return;
			}
			if (discount < 0) {
				frappe.msgprint(__("Discount cannot be negative. Please enter a value between 0 and 100."));
				frm.set_value("discount", 0);
				return;
			}
			if (discount > 100) {
				frappe.msgprint(__("Discount cannot exceed 100%. Please enter a value between 0 and 100."));
				frm.set_value("discount", 100);
				return;
			}
		}
		// Discount will be applied to billable_hours by server-side validate() method
		// The updated billable_hours will be shown after save/validation
	},
	before_workflow_action(frm) {
		if (frm.selected_workflow_action !== "Submit") return;

		frappe.dom.unfreeze();

		const has_delivery_note = !!frm.doc.delivery_note;
		const method = has_delivery_note
			? "phamos.phamos.doctype.monthly_implementation_summery.monthly_implementation_summery.update_delivery_note_from_summary"
			: "phamos.phamos.doctype.monthly_implementation_summery.monthly_implementation_summery.create_delivery_note_from_summary";

		return new Promise(function (resolve) {
			frappe.call({
				method,
				args: { docname: frm.doc.name },
				freeze: true,
				freeze_message: has_delivery_note ? __("Updating delivery note...") : __("Creating delivery note..."),
				callback: function (r) {
					if (r.exc) {
						frappe.msgprint({
							title: __("Error"),
							message: (r.exc[0] || (has_delivery_note ? __("Failed to update delivery note.") : __("Failed to create delivery note."))),
							indicator: "red"
						});
						// Allow workflow to proceed even if DN action failed
						resolve();
						return;
					}
					frm.reload_doc().then(resolve);
				}
			});
		});
	},
		
		// ...existing code...
	
});