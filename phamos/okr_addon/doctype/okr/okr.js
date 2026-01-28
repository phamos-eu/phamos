// Copyright (c) 2025, Phamos and contributors
// For license information, please see license.txt

frappe.ui.form.on("OKR", {
	onload: function(frm) {
		// Populate OKR Type from backend's allowed doctypes (in setting)
		frappe.call({
			method: "phamos.okr_addon.doctype.okr.okr.get_okr_type_options",
			callback: function(r) {
				if(r.message) {
					frm.set_df_property('okr_type', 'options', r.message ? r.message.join('\n') : '');
				}
			}
		});
		
		// Set query for parent_kra to filter based on parent_okr
		frm.set_query("parent_kra", function() {
			return {
				filters: {}
			};
		});
	},
	
	parent_okr: function(frm) {
		// When parent_okr changes, update parent_kra filter
		if (frm.doc.parent_okr) {
			// Get KRs from parent OKR's measurables
			frappe.call({
				method: "phamos.okr_addon.doctype.okr.okr.get_krs_from_parent_okr",
				args: {
					parent_okr: frm.doc.parent_okr
				},
				callback: function(r) {
					if (r.message && r.message.length > 0) {
						// Update parent_kra query to only show KRs from parent OKR
						frm.set_query("parent_kra", function() {
							return {
								filters: {
									"name": ["in", r.message]
								}
							};
						});
						
						// Clear parent_kra if current value is not in the filtered list
						if (frm.doc.parent_kra && !r.message.includes(frm.doc.parent_kra)) {
							frm.set_value("parent_kra", "");
						}
					} else {
						// No KRs found in parent OKR, disable parent_kra
						frm.set_query("parent_kra", function() {
							return {
								filters: {
									"name": ["in", []]  // Empty list - no options
								}
							};
						});
						if (frm.doc.parent_kra) {
							frm.set_value("parent_kra", "");
						}
					}
					frm.refresh_field("parent_kra");
				}
			});
		} else {
			// No parent_okr selected, show all KRs
			frm.set_query("parent_kra", function() {
				return {
					filters: {}
				};
			});
			frm.refresh_field("parent_kra");
		}
	},
	refresh(frm) {
		// Render measurable summary in the form
		render_measurable_summary_form(frm);
		
		// Add market-standard features
		addMarketStandardFeatures(frm);
		
		// Add Parent links to Connections (Parent KR and/or Parent OKR)
		if (frm.doc.parent_kra || frm.doc.parent_okr) {
			setTimeout(() => addParentLink(frm), 500);
		}
		
		// Set parent_kra filter if parent_okr exists
		if (frm.doc.parent_okr) {
			frappe.call({
				method: "phamos.okr_addon.doctype.okr.okr.get_krs_from_parent_okr",
				args: {
					parent_okr: frm.doc.parent_okr
				},
				callback: function(r) {
					if (r.message && r.message.length > 0) {
						frm.set_query("parent_kra", function() {
							return {
								filters: {
									"name": ["in", r.message]
								}
							};
						});
					} else {
						frm.set_query("parent_kra", function() {
							return {
								filters: {
									"name": ["in", []]
								}
							};
						});
					}
				}
			});
		}
		
		// Refresh measurables field to ensure percent_complete is visible
		if (!frm.is_new() && frm.doc.name) {
			frm.refresh_field('measurables');
		}
		
		// Add child KRA progress to measurable rows (in child table)
		if (!frm.is_new() && frm.doc.name) {
			setTimeout(() => addChildKRAProgressToMeasurables(frm), 500);
		}
		
		// Listen for when measurable rows are opened/edited
		setTimeout(() => {
			if (frm.fields_dict.measurables && frm.fields_dict.measurables.grid) {
				const grid = frm.fields_dict.measurables.grid;
				
				// Listen for when rows are toggled open
				grid.wrapper.on('click', '.grid-row', function() {
					if (!frm.is_new() && frm.doc.name) {
						setTimeout(() => addChildKRAProgressToMeasurables(frm), 400);
					}
				});
				
				// Also refresh when grid refreshes
				const originalRefresh = grid.refresh;
				grid.refresh = function() {
					const result = originalRefresh.apply(this, arguments);
					if (!frm.is_new() && frm.doc.name) {
						setTimeout(() => addChildKRAProgressToMeasurables(frm), 400);
					}
					return result;
				};
			}
		}, 300);
		
		// Render child OKRs in HTML field (with delay to ensure field is ready)
		setTimeout(() => renderChildOKRsInField(frm), 200);
		
	},
	
	measurables_add(frm, cdt, cdn) {
		// Handle when a new measurable is added
		let measurable = frm.get_doc(cdt, cdn);
		if (measurable) {
			// Set default values
			if (!measurable.percent_complete) {
				measurable.percent_complete = 0;
			}
		}
		frm.refresh_field('measurables');
		update_progress(frm);
		render_measurable_summary_form(frm);
	},
	
	measurables_form_render(frm, cdt, cdn) {
		// Triggered when a measurable row is opened in form view
		// Add child KRA progress when row is opened
		if (!frm.is_new() && frm.doc.name) {
			const measurable = locals[cdt][cdn];
			
			if (measurable && measurable.metric_name) {
				// Wait for form to be fully rendered
				setTimeout(() => {
					addChildKRAProgressToSpecificRow(frm, cdt, cdn);
				}, 800);
			}
		}
	},
	
	measurables_remove(frm, cdt, cdn) {
		// Handle when a measurable is removed
		frm.refresh_field('measurables');
		update_progress(frm);
		render_measurable_summary_form(frm);
	},
	
	measurables_percent_complete(frm, cdt, cdn) {
		// Update progress when percent complete changes
		update_progress(frm);
		render_measurable_summary_form(frm);
	},
	
	measurables_baseline_value(frm, cdt, cdn) {
		// Handle baseline value changes
		let measurable = locals[cdt][cdn];
		if (measurable && measurable.baseline_value && measurable.target_value) {
			validate_measurable_values(measurable);
		}
	},
	
	measurables_target_value(frm, cdt, cdn) {
		// Handle target value changes
		let measurable = locals[cdt][cdn];
		if (measurable && measurable.baseline_value && measurable.target_value) {
			validate_measurable_values(measurable);
		}
	}
});

// Add form handler for Measurable child table to ensure progress section is visible
frappe.ui.form.on('Measurable', {
	form_render(frm, cdt, cdn) {
		// Ensure progress_tracking_section is visible when the row is opened
		const measurable = locals[cdt][cdn];
		
		// Wait for form to be fully rendered
		setTimeout(() => {
			// Find the grid row wrapper
			const grid_row = frm.fields_dict.measurables.grid.grid_rows_by_docname[cdn];
			
			if (grid_row && grid_row.wrapper) {
				// Show the progress tracking section
				const progress_section = grid_row.wrapper.find('[data-fieldname="progress_tracking_section"]');
				if (progress_section && progress_section.length > 0) {
					progress_section.removeClass('hide-control');
					progress_section.show();
				}
				
				// Ensure all fields in progress section are visible
				const current_value_field = grid_row.wrapper.find('[data-fieldname="current_value"]');
				const percent_complete_field = grid_row.wrapper.find('[data-fieldname="percent_complete"]');
				const ref_link_field = grid_row.wrapper.find('[data-fieldname="ref_link"]');
				
				if (current_value_field && current_value_field.length > 0) {
					current_value_field.closest('.frappe-control').removeClass('hide-control');
					current_value_field.closest('.frappe-control').show();
				}
				if (percent_complete_field && percent_complete_field.length > 0) {
					percent_complete_field.closest('.frappe-control').removeClass('hide-control');
					percent_complete_field.closest('.frappe-control').show();
				}
				if (ref_link_field && ref_link_field.length > 0) {
					ref_link_field.closest('.frappe-control').removeClass('hide-control');
					ref_link_field.closest('.frappe-control').show();
				}
			}
			
			// Also call the child KRA progress function if applicable
			if (!frm.is_new() && frm.doc.name && measurable.metric_name) {
				setTimeout(() => {
					addChildKRAProgressToSpecificRow(frm, cdt, cdn);
				}, 300);
			}
		}, 100);
	}
});

// Function to update progress
function update_progress(frm) {
	frm.save('Update').then(() => {
		frm.refresh_field('progress');
	});
}

// Function to validate measurable values
function validate_measurable_values(measurable) {
	if (measurable.baseline_value && measurable.target_value) {
		if (measurable.baseline_value == measurable.target_value) {
			frappe.msgprint({
				title: __('Validation Error'),
				message: __('Baseline value cannot be equal to target value'),
				indicator: 'red'
			});
		}
	}
}

// Render measurable summary in the form
function render_measurable_summary_form(frm) {
	// Empty the form dashboard to prevent duplicates
	$('.measurable_summary').remove();
	
	let measurables = frm.doc.measurables || [];
	
	if (measurables.length === 0) {
		// Show empty state in dashboard
		let empty_html = `
			<div style="text-align: center; padding: 20px; color: #7f8c8d;">
				<div style="font-size: 2em; margin-bottom: 10px;">📊</div>
				<div style="font-weight: 600; margin-bottom: 5px;">No Measurables</div>
				<div style="font-size: 0.9em;">Add measurables to see progress summary</div>
			</div>
		`;
		frm.dashboard.add_section(
			__('📊 Measurable Summary (KR)'),
			empty_html,
			'measurable_summary'
		);
		return;
	}
	
	// Get enhanced summary from backend
	frappe.call({
		method: 'phamos.okr_addon.doctype.okr.okr.get_measurable_summary_for_frontend',
		args: { okr_name: frm.doc.name },
		callback: function(r) {
			if (r.message) {
				renderEnhancedSummary(frm, r.message);
			} else {
				// Fallback to basic calculation if backend method not available
				renderBasicSummary(frm, measurables);
			}
		}
	});
}

// Render enhanced summary with comprehensive metrics
function renderEnhancedSummary(frm, summary) {
	let card_html = `
		<div style="width: 100%; background: white; border-radius: 12px; box-shadow: 0 2px 8px rgba(0,0,0,0.1); overflow: hidden;">
			<div style="font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;">
				<!-- All 7 Circles in Single Flex Container -->
				<div style="display: flex; justify-content: space-around; align-items: center; padding: 30px 20px; background: #f8f9fa; flex-wrap: wrap; gap: 15px;">
					<!-- Total KRs Circle -->
					<div style="text-align: center; flex: 1; min-width: 80px;">
						<div style="position: relative; width: 70px; height: 70px; margin: 0 auto 8px;">
							<svg width="70" height="70" viewBox="0 0 70 70">
								<circle cx="35" cy="35" r="30" fill="none" stroke="#e9ecef" stroke-width="5"/>
								<circle cx="35" cy="35" r="30" fill="none" stroke="#2c3e50" stroke-width="5" 
									stroke-dasharray="${2 * Math.PI * 30}" stroke-dashoffset="${2 * Math.PI * 30 * (1 - 1)}" 
									transform="rotate(-90 35 35)" style="transition: stroke-dashoffset 0.5s ease;"/>
							</svg>
							<div style="position: absolute; top: 50%; left: 50%; transform: translate(-50%, -50%); font-size: 1em; font-weight: 700; color: #2c3e50;">${summary.total}</div>
						</div>
						<div style="color: #7f8c8d; font-size: 0.8em; font-weight: 500;">Total KRs</div>
					</div>
					
					<!-- Completed Circle -->
					<div style="text-align: center; flex: 1; min-width: 80px;">
						<div style="position: relative; width: 70px; height: 70px; margin: 0 auto 8px;">
							<svg width="70" height="70" viewBox="0 0 70 70">
								<circle cx="35" cy="35" r="30" fill="none" stroke="#e9ecef" stroke-width="5"/>
								<circle cx="35" cy="35" r="30" fill="none" stroke="#27ae60" stroke-width="5" 
									stroke-dasharray="${2 * Math.PI * 30}" stroke-dashoffset="${2 * Math.PI * 30 * (1 - (summary.completed / summary.total))}" 
									transform="rotate(-90 35 35)" style="transition: stroke-dashoffset 0.5s ease;"/>
							</svg>
							<div style="position: absolute; top: 50%; left: 50%; transform: translate(-50%, -50%); font-size: 1em; font-weight: 700; color: #27ae60;">${summary.completed}</div>
						</div>
						<div style="color: #27ae60; font-size: 0.8em; font-weight: 500;">✅ Completed</div>
					</div>
					
					<!-- In Progress Circle -->
					<div style="text-align: center; flex: 1; min-width: 80px;">
						<div style="position: relative; width: 70px; height: 70px; margin: 0 auto 8px;">
							<svg width="70" height="70" viewBox="0 0 70 70">
								<circle cx="35" cy="35" r="30" fill="none" stroke="#e9ecef" stroke-width="5"/>
								<circle cx="35" cy="35" r="30" fill="none" stroke="#f39c12" stroke-width="5" 
									stroke-dasharray="${2 * Math.PI * 30}" stroke-dashoffset="${2 * Math.PI * 30 * (1 - (summary.in_progress / summary.total))}" 
									transform="rotate(-90 35 35)" style="transition: stroke-dashoffset 0.5s ease;"/>
							</svg>
							<div style="position: absolute; top: 50%; left: 50%; transform: translate(-50%, -50%); font-size: 1em; font-weight: 700; color: #f39c12;">${summary.in_progress}</div>
						</div>
						<div style="color: #f39c12; font-size: 0.8em; font-weight: 500;">🔄 In Progress</div>
					</div>
					
					<!-- Not Started Circle -->
					<div style="text-align: center; flex: 1; min-width: 80px;">
						<div style="position: relative; width: 70px; height: 70px; margin: 0 auto 8px;">
							<svg width="70" height="70" viewBox="0 0 70 70">
								<circle cx="35" cy="35" r="30" fill="none" stroke="#e9ecef" stroke-width="5"/>
								<circle cx="35" cy="35" r="30" fill="none" stroke="#e74c3c" stroke-width="5" 
									stroke-dasharray="${2 * Math.PI * 30}" stroke-dashoffset="${2 * Math.PI * 30 * (1 - (summary.not_started / summary.total))}" 
									transform="rotate(-90 35 35)" style="transition: stroke-dashoffset 0.5s ease;"/>
							</svg>
							<div style="position: absolute; top: 50%; left: 50%; transform: translate(-50%, -50%); font-size: 1em; font-weight: 700; color: #e74c3c;">${summary.not_started}</div>
						</div>
						<div style="color: #e74c3c; font-size: 0.8em; font-weight: 500;">⏳ Not Started</div>
					</div>
					
					<!-- On Track Circle -->
					<div style="text-align: center; flex: 1; min-width: 80px;">
						<div style="position: relative; width: 70px; height: 70px; margin: 0 auto 8px;">
							<svg width="70" height="70" viewBox="0 0 70 70">
								<circle cx="35" cy="35" r="30" fill="none" stroke="#e9ecef" stroke-width="5"/>
								<circle cx="35" cy="35" r="30" fill="none" stroke="#27ae60" stroke-width="5" 
									stroke-dasharray="${2 * Math.PI * 30}" stroke-dashoffset="${2 * Math.PI * 30 * (1 - (summary.on_track / summary.total))}" 
									transform="rotate(-90 35 35)" style="transition: stroke-dashoffset 0.5s ease;"/>
							</svg>
							<div style="position: absolute; top: 50%; left: 50%; transform: translate(-50%, -50%); font-size: 1em; font-weight: 700; color: #27ae60;">${summary.on_track}</div>
						</div>
						<div style="color: #27ae60; font-size: 0.8em; font-weight: 500;">🟢 On Track</div>
					</div>
					
					<!-- At Risk Circle -->
					<div style="text-align: center; flex: 1; min-width: 80px;">
						<div style="position: relative; width: 70px; height: 70px; margin: 0 auto 8px;">
							<svg width="70" height="70" viewBox="0 0 70 70">
								<circle cx="35" cy="35" r="30" fill="none" stroke="#e9ecef" stroke-width="5"/>
								<circle cx="35" cy="35" r="30" fill="none" stroke="#f39c12" stroke-width="5" 
									stroke-dasharray="${2 * Math.PI * 30}" stroke-dashoffset="${2 * Math.PI * 30 * (1 - (summary.at_risk / summary.total))}" 
									transform="rotate(-90 35 35)" style="transition: stroke-dashoffset 0.5s ease;"/>
							</svg>
							<div style="position: absolute; top: 50%; left: 50%; transform: translate(-50%, -50%); font-size: 1em; font-weight: 700; color: #f39c12;">${summary.at_risk}</div>
						</div>
						<div style="color: #f39c12; font-size: 0.8em; font-weight: 500;">🟡 At Risk</div>
					</div>
					
					<!-- Overdue Circle -->
					<div style="text-align: center; flex: 1; min-width: 80px;">
						<div style="position: relative; width: 70px; height: 70px; margin: 0 auto 8px;">
							<svg width="70" height="70" viewBox="0 0 70 70">
								<circle cx="35" cy="35" r="30" fill="none" stroke="#e9ecef" stroke-width="5"/>
								<circle cx="35" cy="35" r="30" fill="none" stroke="#e74c3c" stroke-width="5" 
									stroke-dasharray="${2 * Math.PI * 30}" stroke-dashoffset="${2 * Math.PI * 30 * (1 - (summary.overdue_count / summary.total))}" 
									transform="rotate(-90 35 35)" style="transition: stroke-dashoffset 0.5s ease;"/>
							</svg>
							<div style="position: absolute; top: 50%; left: 50%; transform: translate(-50%, -50%); font-size: 1em; font-weight: 700; color: #e74c3c;">${summary.overdue_count}</div>
						</div>
						<div style="color: #e74c3c; font-size: 0.8em; font-weight: 500;">🔴 Overdue</div>
					</div>
				</div>
				
				<!-- Progress & Health Section -->
				<div style="padding: 25px; background: #f8f9fa;">
					<div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 15px;">
						<div style="font-weight: 600; color: #2c3e50; font-size: 1.1em;">📈 Progress Overview</div>
						<div style="display: flex; gap: 15px;">
							<div style="text-align: center; background: white; padding: 10px 15px; border-radius: 8px; box-shadow: 0 1px 3px rgba(0,0,0,0.1);">
								<div style="font-weight: bold; color: #27ae60; font-size: 1.2em;">${summary.average_progress}%</div>
								<div style="font-size: 0.8em; color: #7f8c8d;">Avg Progress</div>
							</div>
							<div style="text-align: center; background: white; padding: 10px 15px; border-radius: 8px; box-shadow: 0 1px 3px rgba(0,0,0,0.1);">
								<div style="font-weight: bold; color: #3498db; font-size: 1.2em;">${summary.overall_health}</div>
								<div style="font-size: 0.8em; color: #7f8c8d;">Health Score</div>
							</div>
							<div style="text-align: center; background: white; padding: 10px 15px; border-radius: 8px; box-shadow: 0 1px 3px rgba(0,0,0,0.1);">
								<div style="font-weight: bold; color: #27ae60; font-size: 1.2em;">${summary.completion_rate}%</div>
								<div style="font-size: 0.8em; color: #7f8c8d;">Completion Rate</div>
							</div>
							<div style="text-align: center; background: white; padding: 10px 15px; border-radius: 8px; box-shadow: 0 1px 3px rgba(0,0,0,0.1);">
								<div style="font-weight: bold; color: #e74c3c; font-size: 1.2em;">${summary.risk_score}%</div>
								<div style="font-size: 0.8em; color: #7f8c8d;">Risk Score</div>
							</div>
						</div>
					</div>
					
					<!-- Progress Bar -->
					<div style="background: #e9ecef; border-radius: 10px; height: 12px; overflow: hidden; box-shadow: inset 0 1px 3px rgba(0,0,0,0.1);">
						<div style="background: linear-gradient(90deg, #27ae60, #2ecc71); height: 100%; width: ${summary.average_progress}%; transition: width 0.5s ease; border-radius: 10px;"></div>
					</div>
				</div>
				

			</div>
		</div>
	`;
	
	// Add the enhanced summary to form dashboard
	frm.dashboard.add_section(
		card_html,
		__('📊 Measurable Summary (KR)')
	);
}

// Render basic summary as fallback
function renderBasicSummary(frm, measurables) {
	let summary = {
		total: measurables.length,
		completed: 0,
		in_progress: 0,
		not_started: 0,
		average_progress: 0
	};
	
	let total_progress = 0;
	
	measurables.forEach(function(measurable, index) {
		if (measurable.percent_complete === 100) {
			summary.completed++;
		} else if (measurable.percent_complete > 0) {
			summary.in_progress++;
		} else {
			summary.not_started++;
		}
		
		if (measurable.percent_complete) {
			total_progress += measurable.percent_complete;
		}
	});
	
	summary.average_progress = summary.total > 0 ? (total_progress / summary.total).toFixed(1) : 0;
	let overall_progress = summary.total > 0 ? (total_progress / summary.total) : 0;
	
	let card_html = `
		<div style="width: 100%; background: white; border-radius: 12px; box-shadow: 0 2px 8px rgba(0,0,0,0.1); overflow: hidden;">
			<div style="font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;">
				<!-- All 4 Circles in Single Flex Container -->
				<div style="display: flex; justify-content: space-around; align-items: center; padding: 30px 20px; background: #f8f9fa; flex-wrap: wrap; gap: 15px;">
					<!-- Total KRs Circle -->
					<div style="text-align: center; flex: 1; min-width: 80px;">
						<div style="position: relative; width: 70px; height: 70px; margin: 0 auto 8px;">
							<svg width="70" height="70" viewBox="0 0 70 70">
								<circle cx="35" cy="35" r="30" fill="none" stroke="#e9ecef" stroke-width="5"/>
								<circle cx="35" cy="35" r="30" fill="none" stroke="#2c3e50" stroke-width="5" 
									stroke-dasharray="${2 * Math.PI * 30}" stroke-dashoffset="${2 * Math.PI * 30 * (1 - 1)}" 
									transform="rotate(-90 35 35)" style="transition: stroke-dashoffset 0.5s ease;"/>
							</svg>
							<div style="position: absolute; top: 50%; left: 50%; transform: translate(-50%, -50%); font-size: 1em; font-weight: 700; color: #2c3e50;">${summary.total}</div>
						</div>
						<div style="color: #7f8c8d; font-size: 0.8em; font-weight: 500;">Total KRs</div>
					</div>
					
					<!-- Completed Circle -->
					<div style="text-align: center; flex: 1; min-width: 80px;">
						<div style="position: relative; width: 70px; height: 70px; margin: 0 auto 8px;">
							<svg width="70" height="70" viewBox="0 0 70 70">
								<circle cx="35" cy="35" r="30" fill="none" stroke="#e9ecef" stroke-width="5"/>
								<circle cx="35" cy="35" r="30" fill="none" stroke="#27ae60" stroke-width="5" 
									stroke-dasharray="${2 * Math.PI * 30}" stroke-dashoffset="${2 * Math.PI * 30 * (1 - (summary.completed / summary.total))}" 
									transform="rotate(-90 35 35)" style="transition: stroke-dashoffset 0.5s ease;"/>
							</svg>
							<div style="position: absolute; top: 50%; left: 50%; transform: translate(-50%, -50%); font-size: 1em; font-weight: 700; color: #27ae60;">${summary.completed}</div>
						</div>
						<div style="color: #27ae60; font-size: 0.8em; font-weight: 500;">✅ Completed</div>
					</div>
					
					<!-- In Progress Circle -->
					<div style="text-align: center; flex: 1; min-width: 80px;">
						<div style="position: relative; width: 70px; height: 70px; margin: 0 auto 8px;">
							<svg width="70" height="70" viewBox="0 0 70 70">
								<circle cx="35" cy="35" r="30" fill="none" stroke="#e9ecef" stroke-width="5"/>
								<circle cx="35" cy="35" r="30" fill="none" stroke="#f39c12" stroke-width="5" 
									stroke-dasharray="${2 * Math.PI * 30}" stroke-dashoffset="${2 * Math.PI * 30 * (1 - (summary.in_progress / summary.total))}" 
									transform="rotate(-90 35 35)" style="transition: stroke-dashoffset 0.5s ease;"/>
							</svg>
							<div style="position: absolute; top: 50%; left: 50%; transform: translate(-50%, -50%); font-size: 1em; font-weight: 700; color: #f39c12;">${summary.in_progress}</div>
						</div>
						<div style="color: #f39c12; font-size: 0.8em; font-weight: 500;">🔄 In Progress</div>
					</div>
					
					<!-- Not Started Circle -->
					<div style="text-align: center; flex: 1; min-width: 80px;">
						<div style="position: relative; width: 70px; height: 70px; margin: 0 auto 8px;">
							<svg width="70" height="70" viewBox="0 0 70 70">
								<circle cx="35" cy="35" r="30" fill="none" stroke="#e9ecef" stroke-width="5"/>
								<circle cx="35" cy="35" r="30" fill="none" stroke="#e74c3c" stroke-width="5" 
									stroke-dasharray="${2 * Math.PI * 30}" stroke-dashoffset="${2 * Math.PI * 30 * (1 - (summary.not_started / summary.total))}" 
									transform="rotate(-90 35 35)" style="transition: stroke-dashoffset 0.5s ease;"/>
							</svg>
							<div style="position: absolute; top: 50%; left: 50%; transform: translate(-50%, -50%); font-size: 1em; font-weight: 700; color: #e74c3c;">${summary.not_started}</div>
						</div>
						<div style="color: #e74c3c; font-size: 0.8em; font-weight: 500;">⏳ Not Started</div>
					</div>
				</div>
				
				<!-- Progress Overview -->
				<div style="padding: 25px; background: #f8f9fa;">
					<div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 15px;">
						<div style="font-weight: 600; color: #2c3e50; font-size: 1.1em;">📈 Progress Overview</div>
						<div style="text-align: center; background: white; padding: 10px 15px; border-radius: 8px; box-shadow: 0 1px 3px rgba(0,0,0,0.1);">
							<div style="font-weight: bold; color: #27ae60; font-size: 1.2em;">${summary.average_progress}%</div>
							<div style="font-size: 0.8em; color: #7f8c8d;">Avg Progress</div>
						</div>
					</div>
					
					<!-- Progress Bar -->
					<div style="background: #e9ecef; border-radius: 10px; height: 12px; overflow: hidden; margin-bottom: 20px; box-shadow: inset 0 1px 3px rgba(0,0,0,0.1);">
						<div style="background: linear-gradient(90deg, #27ae60, #2ecc71); height: 100%; width: ${overall_progress}%; transition: width 0.5s ease; border-radius: 10px;"></div>
					</div>
				</div>
			</div>
		</div>
	`;
	
	// Add the basic summary to form dashboard
	frm.dashboard.add_section(
		card_html,
		__('📊 Measurable Summary (KR)')
	);
}

// Helper functions for enhanced UI
function get_progress_color(percentage) {
	if (percentage >= 80) return '#27ae60'; // Green
	if (percentage >= 60) return '#f39c12'; // Orange
	if (percentage >= 40) return '#3498db'; // Blue
	if (percentage >= 20) return '#e67e22'; // Dark Orange
	return '#e74c3c'; // Red
}
 
function get_status_icon(percentage) {
	if (percentage === 100) return '✅';
	if (percentage >= 80) return '🚀';
	if (percentage >= 60) return '📈';
	if (percentage >= 40) return '🔄';
	if (percentage >= 20) return '⚠️';
	return '⏳';
}

function get_progress_status(percentage) {
	if (percentage === 100) return 'Completed';
	if (percentage >= 80) return 'Near Completion';
	if (percentage >= 60) return 'Good Progress';
	if (percentage >= 40) return 'Halfway';
	if (percentage >= 20) return 'Early Stage';
	return 'Not Started';
}

// Market-standard features for enhanced UX
function addMarketStandardFeatures(frm) {
	// Add achievement badges
	addAchievementBadges(frm);
	
	// Add risk indicators
	addRiskIndicators(frm);
	
	// Add performance metrics
	addPerformanceMetrics(frm);
	
	// Add collaboration features
	addCollaborationFeatures(frm);
	
	// Add export/share functionality
	addExportShareFeatures(frm);
}

// Add achievement badges
function addAchievementBadges(frm) {
	let measurables = frm.doc.measurables || [];
	let completedCount = measurables.filter(m => m.percent_complete === 100).length;
	let totalCount = measurables.length;
	
	if (totalCount > 0) {
		let completionRate = (completedCount / totalCount) * 100;
		let badge = '';
		
		if (completionRate === 100) {
			badge = '<span class="badge badge-success" style="margin-left: 10px;">🏆 Perfect Score</span>';
		} else if (completionRate >= 80) {
			badge = '<span class="badge badge-info" style="margin-left: 10px;">⭐ High Achiever</span>';
		} else if (completionRate >= 60) {
			badge = '<span class="badge badge-warning" style="margin-left: 10px;">📈 On Track</span>';
		}
		
		if (badge) {
			// Add badge to the title field
			let titleField = frm.get_field('title');
			if (titleField) {
				titleField.$wrapper.find('.control-value').append(badge);
			}
		}
	}
}

// Add risk indicators
function addRiskIndicators(frm) {
	let measurables = frm.doc.measurables || [];
	let atRiskCount = 0;
	let overdueCount = 0;
	
	measurables.forEach(measurable => {
		if (measurable.percent_complete < 40 && measurable.percent_complete > 0) {
			atRiskCount++;
		} else if (measurable.percent_complete === 0) {
			overdueCount++;
		}
	});
	
	let riskIndicator = '';
	if (atRiskCount > 0) {
		riskIndicator += `<div class="alert alert-warning" style="margin: 10px 0;">
			⚠️ ${atRiskCount} measurable(s) at risk
		</div>`;
	}
	if (overdueCount > 0) {
		riskIndicator += `<div class="alert alert-danger" style="margin: 10px 0;">
			🚨 ${overdueCount} measurable(s) overdue
		</div>`;
	}
	
	if (riskIndicator) {
		// Add risk indicators to the form
		let riskContainer = $(frm.wrapper).find('.risk-indicators');
		if (riskContainer.length === 0) {
			riskContainer = $('<div class="risk-indicators"></div>');
		}
		riskContainer.html(riskIndicator);
	}
}

// Add performance metrics
function addPerformanceMetrics(frm) {
	let measurables = frm.doc.measurables || [];
	let totalProgress = 0;
	let avgProgress = 0;
	
	if (measurables.length > 0) {
		totalProgress = measurables.reduce((sum, m) => sum + (m.percent_complete || 0), 0);
		avgProgress = totalProgress / measurables.length;
	}
	
	let metricsHtml = `
		<div class="performance-metrics" style="background: #f8f9fa; padding: 15px; border-radius: 8px; margin: 10px 0;">
			<div style="display: grid; grid-template-columns: repeat(3, 1fr); gap: 15px;">
				<div style="text-align: center;">
					<div style="font-size: 1.5em; font-weight: 700; color: #2c3e50;">${measurables.length}</div>
					<div style="font-size: 0.8em; color: #7f8c8d;">Total Measurables</div>
				</div>
				<div style="text-align: center;">
					<div style="font-size: 1.5em; font-weight: 700; color: #27ae60;">${avgProgress.toFixed(1)}%</div>
					<div style="font-size: 0.8em; color: #7f8c8d;">Average Progress</div>
				</div>
				<div style="text-align: center;">
					<div style="font-size: 1.5em; font-weight: 700; color: #3498db;">${frm.doc.progress || 0}%</div>
					<div style="font-size: 0.8em; color: #7f8c8d;">Overall Progress</div>
				</div>
			</div>
		</div>
	`;
	
	// Add metrics to the form
	let metricsContainer = $(frm.wrapper).find('.performance-metrics-container');
	if (metricsContainer.length === 0) {
		metricsContainer = $('<div class="performance-metrics-container"></div>');
	}
	metricsContainer.html(metricsHtml);
}

// Add collaboration features
function addCollaborationFeatures(frm) {
	// Add comment section
	let commentHtml = `
		<div class="collaboration-section" style="margin: 15px 0;">
			<h6 style="margin-bottom: 10px;">💬 Comments & Updates</h6>
			<div class="comment-input" style="margin-bottom: 10px;">
				<textarea class="form-control" placeholder="Add a comment or update..." rows="3"></textarea>
			</div>
			<button class="btn btn-sm btn-primary" onclick="addComment()">Add Comment</button>
		</div>
	`;
	
	// Add collaboration section
	let collabContainer = $(frm.wrapper).find('.collaboration-container');
	if (collabContainer.length === 0) {
		collabContainer = $('<div class="collaboration-container"></div>');
	}
	collabContainer.html(commentHtml);
}

// Add export/share features
function addExportShareFeatures(frm) {
	// Add export button
	frm.add_custom_button(__('📊 Export Report'), function() {
		exportOKRReport(frm);
	}, __('Actions'));
	
	// Add share button
	frm.add_custom_button(__('📤 Share'), function() {
		shareOKR(frm);
	}, __('Actions'));
}

// Export objective report
function exportOKRReport(frm) {
	frappe.call({
		method: 'okr_addon.okr_addon.page.okr_dashboard.okr_dashboard.export_dashboard',
		args: { 
			format: 'pdf',
			okr_name: frm.doc.name 
		},
		callback: function(r) {
			if (r.message && r.message.file_url) {
				window.open(r.message.file_url, '_blank');
			}
		}
	});
}

// Share objective
function shareOKR(frm) {
	frappe.msgprint({
		title: __('Share OKR'),
		message: __('Sharing functionality will be implemented here.'),
		indicator: 'blue'
	});
}

// Add comment function
function addComment() {
	frappe.msgprint({
		title: __('Comment Added'),
		message: __('Comment functionality will be implemented here.'),
		indicator: 'green'
	});
}

// Add Parent links (KR and/or OKR) to Connections section
function addParentLink(frm) {
	if (!frm.dashboard || !frm.dashboard.transactions_area) return;
	
	let $area = frm.dashboard.transactions_area;
	$area.find('.parent-link').remove(); // Remove existing parent links
	
	let parentLinks = [];
	
	// Add Parent KR if exists
	if (frm.doc.parent_kra) {
		parentLinks.push({
			doctype: 'KR',
			name: frm.doc.parent_kra,
			label: 'Parent KR',
			type: 'KR'
		});
	}
	
	// Add Parent OKR if exists
	if (frm.doc.parent_okr) {
		parentLinks.push({
			doctype: 'OKR',
			name: frm.doc.parent_okr,
			label: 'Parent OKR',
			type: 'OKR'
		});
	}
	
	if (parentLinks.length === 0) return;
	
	let $firstCol = $area.find('.col-md-4').first();
	if ($firstCol.length) {
		// Find the container for document links (after form-link-title)
		let $linkContainer = $firstCol.find('.form-link-title').next();
		if (!$linkContainer.length || !$linkContainer.hasClass('document-link')) {
			// If no container exists, create one or use the column itself
			$linkContainer = $firstCol;
		}
		
		// Insert at the beginning - after form-link-title if exists, otherwise at start
		let $title = $firstCol.find('.form-link-title');
		let $insertAfter = $title.length ? $title : $firstCol;
		
		// Create Parent links for both KR and OKR
		parentLinks.forEach((parentInfo) => {
			let $link = $(`
				<div class="document-link parent-link" data-doctype="${parentInfo.doctype}" data-names='["${parentInfo.name}"]'>
					<div class="document-link-badge" data-doctype="${parentInfo.doctype}">
						<span class="count">1</span>
						<a class="badge-link">${__(parentInfo.label)}</a>
					</div>
				</div>
			`);
			
			// Insert after the reference point
			$link.insertAfter($insertAfter);
			$insertAfter = $link; // Next link goes after this one
			
			// Make clickable
			$link.find('.badge-link').on('click', (e) => {
				e.preventDefault();
				frappe.set_route('Form', parentInfo.doctype, parentInfo.name);
			});
		});
	}
}

// Render Child OKRs in HTML Field
function renderChildOKRsInField(frm) {
	// Check if field exists
	if (!frm.fields_dict.child_okrs_html) {
		console.warn('child_okrs_html field not found');
		return;
	}
	
	// Only show if this OKR can have children (has a name and is saved)
	if (!frm.doc.name || frm.is_new()) {
		const emptyHtml = '<div style="text-align: center; padding: 20px; color: #8d99a6; font-size: 12px;">No child OKRs available. Save this OKR first.</div>';
		frm.fields_dict.child_okrs_html.set_value(emptyHtml);
		return;
	}
	
	// Fetch child OKRs
	frappe.call({
		method: 'phamos.okr_addon.doctype.okr.okr.get_child_okrs',
		args: {
			okr_name: frm.doc.name
		},
		callback: function(r) {
			if (r.message && r.message.length > 0) {
				const html = renderChildOKRsHTML(frm, r.message);
				frm.fields_dict.child_okrs_html.set_value(html);
			} else {
				const emptyHtml = '<div style="text-align: center; padding: 20px; color: #8d99a6; font-size: 12px;">No child OKRs found</div>';
				frm.fields_dict.child_okrs_html.set_value(emptyHtml);
			}
		},
		error: function(r) {
			console.error('Error fetching child OKRs:', r);
			const errorHtml = '<div style="text-align: center; padding: 20px; color: #e74c3c; font-size: 12px;">Error loading child OKRs</div>';
			if (frm.fields_dict.child_okrs_html) {
				frm.fields_dict.child_okrs_html.set_value(errorHtml);
			}
		}
	});
}

function renderChildOKRsHTML(frm, childOKRs) {
	// Calculate average progress
	const totalProgress = childOKRs.reduce((sum, child) => sum + (child.progress || 0), 0);
	const avgProgress = childOKRs.length > 0 ? (totalProgress / childOKRs.length).toFixed(1) : 0;
	const avgProgressColor = getProgressColor(avgProgress);
	
	let html = `
		<div class="child-okrs-section" style="margin-bottom: 15px;">
			<div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 10px; padding: 8px 0;">
				<div style="display: flex; align-items: center; gap: 8px;">
					<span style="font-size: 12px; color: #8d99a6; background: #f0f4f7; padding: 2px 8px; border-radius: 10px;">
						${childOKRs.length} OKR${childOKRs.length !== 1 ? 's' : ''}
					</span>
				</div>
				<div style="display: flex; align-items: center; gap: 12px;">
					<div style="display: flex; align-items: center; gap: 6px;">
						<span style="font-size: 12px; color: #8d99a6;">Avg Progress:</span>
						<span style="font-size: 14px; font-weight: 600; color: ${avgProgressColor};">${avgProgress}%</span>
					</div>
					<div style="width: 80px; height: 5px; background: #e9ecef; border-radius: 3px; overflow: hidden;">
						<div style="width: ${avgProgress}%; height: 100%; background: ${avgProgressColor}; transition: width 0.3s;"></div>
					</div>
				</div>
			</div>
			<div class="child-okrs-table" style="
				background: #fff;
				border: 1px solid #e0e0e0;
				border-radius: 4px;
				overflow: hidden;
			">
				<table style="width: 100%; border-collapse: collapse; font-size: 12px;">
					<thead>
						<tr style="background: #f8f9fa; border-bottom: 1px solid #e0e0e0;">
							<th style="padding: 6px 8px; text-align: left; font-weight: 600; color: #8d99a6; font-size: 11px; width: 32%;">Title</th>
							<th style="padding: 6px 8px; text-align: left; font-weight: 600; color: #8d99a6; font-size: 11px; width: 12%;">Progress</th>
							<th style="padding: 6px 8px; text-align: center; font-weight: 600; color: #8d99a6; font-size: 11px; width: 10%;">Score</th>
							<th style="padding: 6px 8px; text-align: left; font-weight: 600; color: #8d99a6; font-size: 11px; width: 12%;">OKR Type</th>
							<th style="padding: 6px 8px; text-align: left; font-weight: 600; color: #8d99a6; font-size: 11px; width: 17%;">Responsible</th>
							<th style="padding: 6px 8px; text-align: left; font-weight: 600; color: #8d99a6; font-size: 11px; width: 17%;">Target Date</th>
						</tr>
					</thead>
					<tbody>
	`;
	
	childOKRs.forEach((child, index) => {
		const progress = child.progress || 0;
		const progressColor = getProgressColor(progress);
		const rowBg = index % 2 === 0 ? '#fff' : '#fafbfc';
		
		html += `
			<tr class="child-okr-row" style="
				background: ${rowBg};
				border-bottom: 1px solid #f0f0f0;
				cursor: pointer;
				transition: background 0.15s;
			" data-okr-name="${child.name}" 
			onclick="frappe.set_route('Form', 'OKR', '${child.name}')"
			onmouseover="this.style.background='#f0f7ff'; this.style.borderLeft='3px solid ${progressColor}';"
			onmouseout="this.style.background='${rowBg}'; this.style.borderLeft='none';">
				<td style="padding: 6px 8px;">
					<div style="font-weight: 600; color: #36414c; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; max-width: 200px; font-size: 12px;" title="${child.title}">
						${child.title}
					</div>
				</td>
				<td style="padding: 6px 8px;">
					<div style="display: flex; align-items: center; gap: 6px;">
						<div style="flex: 1; min-width: 50px; height: 3px; background: #e9ecef; border-radius: 2px; overflow: hidden;">
							<div style="width: ${progress}%; height: 100%; background: ${progressColor}; transition: width 0.3s;"></div>
						</div>
						<span style="font-weight: 600; color: #36414c; font-size: 11px; min-width: 35px; text-align: right;">${child.progress_display || '0%'}</span>
					</div>
				</td>
				<td style="padding: 6px 8px; text-align: center;">
					<span style="color: #36414c; font-weight: 600; font-size: 11px;">
						<i class="fa fa-star" style="color: #f39c12; font-size: 10px; margin-right: 2px;"></i>${child.score_display || '0.00'}
					</span>
				</td>
				<td style="padding: 6px 8px;">
					<span style="color: #8d99a6; font-size: 11px; font-weight: 500;">
						${child.okr_type || '-'}
					</span>
				</td>
				<td style="padding: 6px 8px;">
					${child.responsible_person ? `
						<div style="color: #8d99a6; font-size: 11px; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; max-width: 120px;" title="${child.responsible_person}">
							<i class="fa fa-user" style="font-size: 10px; margin-right: 3px;"></i>${child.responsible_person}
						</div>
					` : '<span style="color: #d1d8dd;">-</span>'}
				</td>
				<td style="padding: 6px 8px;">
					${child.target_date ? `
						<div style="color: #8d99a6; font-size: 11px;">
							<i class="fa fa-calendar" style="font-size: 10px; margin-right: 3px;"></i>${frappe.datetime.str_to_user(child.target_date)}
						</div>
					` : '<span style="color: #d1d8dd;">-</span>'}
				</td>
			</tr>
		`;
	});
	
	html += `
					</tbody>
				</table>
			</div>
		</div>
	`;
	
	return html;
}


function getStatusClass(status) {
	const classes = {
		'completed': 'badge-success',
		'on_track': 'badge-info',
		'at_risk': 'badge-warning',
		'overdue': 'badge-danger'
	};
	return classes[status] || 'badge-secondary';
}

function getStatusIcon(status) {
	const icons = {
		'completed': '✓',
		'on_track': '→',
		'at_risk': '⚠',
		'overdue': '⚠'
	};
	return icons[status] || '•';
}

function getStatusColor(status) {
	const colors = {
		'completed': '#27ae60',
		'on_track': '#3498db',
		'at_risk': '#f39c12',
		'overdue': '#e74c3c'
	};
	return colors[status] || '#95a5a6';
}

// Add child KRA progress to a specific measurable row
function addChildKRAProgressToSpecificRow(frm, cdt, cdn) {
	if (!frm.doc.name || frm.is_new()) {
		return;
	}
	
	const measurable = locals[cdt][cdn];
	
	// Get the metric_name - it might be in metric_name field or name field depending on how it's loaded
	const metric_name = measurable?.metric_name || measurable?.name;
	
	if (!measurable || !metric_name) {
		return;
	}
	
	// Get child KRA progress data
	frappe.call({
		method: 'phamos.okr_addon.doctype.okr.okr.get_child_kra_progress',
		args: {
			okr_name: frm.doc.name
		},
		callback: function(r) {
			if (r.message && r.message.length > 0) {
				// Find progress data for this specific measurable
				const kraData = r.message.find(kra => kra.parent_kr_name === metric_name);
				
				if (kraData) {
					// Group child measurables by OKR
					const okrMap = new Map();
					if (kraData.child_measurables) {
						kraData.child_measurables.forEach(item => {
							if (!okrMap.has(item.okr_name)) {
								okrMap.set(item.okr_name, {
									title: item.okr_title,
									measurables: []
								});
							}
							okrMap.get(item.okr_name).measurables.push(item);
						});
					}
					
					// Build child OKRs HTML
					let childOkrsHtml = '';
					okrMap.forEach((okrData, okrName) => {
						const avgProgress = okrData.measurables.reduce((sum, m) => sum + m.progress, 0) / okrData.measurables.length;
						childOkrsHtml += `
							<div style="margin-bottom: 8px; padding: 8px; background: white; border-radius: 4px; border: 1px solid #e3e8ee;">
								<div style="display: flex; align-items: center; gap: 8px; margin-bottom: 6px;">
									<a href="/app/okr/${okrName}" target="_blank" style="color: #5e72e4; font-weight: 600; font-size: 11px; text-decoration: none; flex: 1;">
										📋 ${okrData.title || okrName}
									</a>
									<span style="font-weight: 600; color: ${getProgressColor(avgProgress)}; font-size: 11px;">
										${avgProgress.toFixed(1)}%
									</span>
								</div>
								<div style="font-size: 10px; color: #8898aa; padding-left: 18px;">
									${okrData.measurables.map(m => `
										<div style="margin: 3px 0; display: flex; align-items: center; gap: 6px;">
											<span style="color: #525f7f;">↳ ${m.kr_title}</span>
											<div style="flex: 1; height: 4px; background: #e9ecef; border-radius: 2px; overflow: hidden; max-width: 60px;">
												<div style="width: ${Math.min(m.progress, 100)}%; height: 100%; background: ${getProgressColor(m.progress)};"></div>
											</div>
											<span style="color: ${getProgressColor(m.progress)}; font-weight: 600;">${m.progress.toFixed(1)}%</span>
										</div>
									`).join('')}
								</div>
							</div>
						`;
					});
					
					// Create the child progress HTML
					const childProgressHtml = `
						<div class="child-kra-progress-info" style="
							margin-top: 8px;
							padding: 10px 12px;
							background: linear-gradient(135deg, #f0f7ff 0%, #e8f4ff 100%);
							border-radius: 6px;
							font-size: 11px;
							box-shadow: 0 2px 4px rgba(0,0,0,0.05);
						">
							<div style="display: flex; align-items: center; gap: 10px; margin-bottom: 10px;">
								<i class="fa fa-sitemap" style="font-size: 12px; color: #5e72e4;"></i>
								<span style="font-weight: 600; color: #32325d; font-size: 11px;">Child Progress:</span>
								<span style="font-weight: 700; color: ${getProgressColor(kraData.average_progress)}; font-size: 13px;">
									${kraData.average_progress.toFixed(1)}%
								</span>
								<span style="color: #8898aa; font-size: 10px; margin-left: auto;">
									${kraData.child_okr_count} OKR${kraData.child_okr_count !== 1 ? 's' : ''}, ${kraData.child_measurable_count} KR${kraData.child_measurable_count !== 1 ? 's' : ''}
								</span>
							</div>
							<div style="margin-bottom: 8px;">
								<div style="height: 6px; background: #e9ecef; border-radius: 3px; overflow: hidden;">
									<div style="width: ${Math.min(kraData.average_progress, 100)}%; height: 100%; background: ${getProgressColor(kraData.average_progress)}; transition: width 0.3s;"></div>
								</div>
							</div>
							${childOkrsHtml}
						</div>
					`;
					
					// Update the HTML field in the child table row
					frappe.model.set_value(cdt, cdn, 'child_progress_html', childProgressHtml);
					
					// Find the grid row and refresh the HTML field
					setTimeout(() => {
						const grid_row = frm.fields_dict.measurables.grid.grid_rows_by_docname[cdn];
						if (grid_row && grid_row.wrapper) {
							const html_field = grid_row.wrapper.find('[data-fieldname="child_progress_html"]');
							if (html_field && html_field.length > 0) {
								html_field.html(childProgressHtml);
								console.log('✅ Child progress HTML successfully updated in field for:', metric_name);
							}
						}
					}, 200);
					
					console.log('✅ Child progress info successfully set for:', metric_name);
				} else {
					console.log('❌ No KRA data found for metric:', metric_name);
				}
			} else {
				console.log('❌ No child KRA progress data returned');
			}
		},
		error: function(r) {
			console.error('Error fetching child KRA progress:', r);
		}
	});
}

// Add child KRA progress to measurable rows (in child table) - legacy function
function addChildKRAProgressToMeasurables(frm) {
	if (!frm.doc.name || frm.is_new()) {
		return;
	}
	
	// Get child KRA progress data
	frappe.call({
		method: 'phamos.okr_addon.doctype.okr.okr.get_child_kra_progress',
		args: {
			okr_name: frm.doc.name
		},
		callback: function(r) {
			if (r.message && r.message.length > 0) {
				// Create a map of KR name to progress data
				const kraProgressMap = {};
				r.message.forEach(kraData => {
					kraProgressMap[kraData.parent_kr_name] = kraData;
				});
				
				// Wait for grid to be ready, then add progress info to each row
				setTimeout(() => {
					if (frm.fields_dict.measurables && frm.fields_dict.measurables.grid) {
						const grid = frm.fields_dict.measurables.grid;
						
						// Function to add progress to a specific row
						const addProgressToRow = (row) => {
							// Get the row wrapper - try different properties
							let rowWrapper = null;
							if (row.$wrapper) {
								rowWrapper = $(row.$wrapper);
							} else if (row.wrapper) {
								rowWrapper = $(row.wrapper);
							} else if (row.row) {
								rowWrapper = $(row.row);
							} else if (row.$row) {
								rowWrapper = $(row.$row);
							} else {
								// Try to find the row element by data-idx
								const rowDoc = row.doc;
								if (rowDoc && rowDoc.idx) {
									rowWrapper = grid.wrapper.find(`[data-idx="${rowDoc.idx}"]`);
								}
							}
							
							if (!rowWrapper || rowWrapper.length === 0) {
								return;
							}
							
							const rowDoc = row.doc;
							// Use stored progress data if available, otherwise use current map
							const progressMap = grid._childKRAProgressData || kraProgressMap;
							
							if (rowDoc && rowDoc.metric_name && progressMap[rowDoc.metric_name]) {
								const progressData = progressMap[rowDoc.metric_name];
								
								// Find the percent_complete field control - try multiple methods
								let formGroup = null;
								
								// Method 1: Find by data-fieldname
								let percentCompleteControl = rowWrapper.find('[data-fieldname="percent_complete"]');
								if (percentCompleteControl && percentCompleteControl.length) {
									formGroup = percentCompleteControl.closest('.form-group');
								}
								
								// Method 2: Find by control class
								if (!formGroup || formGroup.length === 0) {
									percentCompleteControl = rowWrapper.find('.control[data-fieldname="percent_complete"]');
									if (percentCompleteControl && percentCompleteControl.length) {
										formGroup = percentCompleteControl.closest('.form-group');
									}
								}
								
								// Method 3: Find by input field
								if (!formGroup || formGroup.length === 0) {
									percentCompleteControl = rowWrapper.find('input[data-fieldname="percent_complete"]');
									if (percentCompleteControl && percentCompleteControl.length) {
										formGroup = percentCompleteControl.closest('.form-group');
									}
								}
								
								// Method 4: Find by label text
								if (!formGroup || formGroup.length === 0) {
									const labels = rowWrapper.find('label');
									if (labels && labels.length > 0) {
										labels.each(function() {
											const $label = $(this);
											const labelText = $label.text();
											if (labelText.includes('% Complete') || labelText.includes('Complete')) {
												formGroup = $label.closest('.form-group');
												return false; // break
											}
										});
									}
								}
								
								// Method 5: Find all form-groups and check for percent_complete
								if (!formGroup || formGroup.length === 0) {
									const formGroups = rowWrapper.find('.form-group');
									if (formGroups && formGroups.length > 0) {
										formGroups.each(function() {
											const $formGroup = $(this);
											const labelText = $formGroup.find('label').text();
											if (labelText.includes('% Complete') || labelText.includes('Complete') || 
											    $formGroup.find('[data-fieldname="percent_complete"]').length > 0) {
												formGroup = $formGroup;
												return false; // break
											}
										});
									}
								}
								
								// Check if row is actually open by looking at the DOM element
								let isRowOpen = false;
								let $rowEl = null;
								
								if (row.row) {
									$rowEl = $(row.row);
									isRowOpen = $rowEl.hasClass('grid-row-open');
								} else if (row.$row) {
									$rowEl = row.$row;
									isRowOpen = $rowEl.hasClass('grid-row-open');
								} else if (rowDoc && rowDoc.idx) {
									$rowEl = grid.wrapper.find(`[data-idx="${rowDoc.idx}"]`);
									isRowOpen = $rowEl.hasClass('grid-row-open');
								} else {
									// Try to find row element from wrapper
									$rowEl = rowWrapper.closest('.grid-row');
									if ($rowEl && $rowEl.length) {
										isRowOpen = $rowEl.hasClass('grid-row-open');
									}
								}
								
								// If still not found, check if rowWrapper itself contains the open class
								if (!isRowOpen && rowWrapper) {
									$rowEl = rowWrapper.closest('.grid-row');
									if ($rowEl && $rowEl.length) {
										isRowOpen = $rowEl.hasClass('grid-row-open');
									}
								}
								
								if (!isRowOpen) {
									return;
								}
								
								if (formGroup && formGroup.length) {
									insertProgressInfo(formGroup, progressData, rowDoc.metric_name);
								} else {
									// Try to find any form-group in the open row
									const allFormGroups = rowWrapper.find('.form-group');
									if (allFormGroups && allFormGroups.length > 0) {
										// Find the one with percent_complete or use the last one
										let targetFormGroup = null;
										allFormGroups.each(function() {
											const $formGroup = $(this);
											const labelText = $formGroup.find('label').text();
											if ($formGroup.find('[data-fieldname="percent_complete"]').length > 0 ||
											    labelText.includes('Complete') || labelText.includes('%')) {
												targetFormGroup = $formGroup;
												return false;
											}
										});
										if (!targetFormGroup) {
											targetFormGroup = allFormGroups.last();
										}
										if (targetFormGroup) {
											insertProgressInfo(targetFormGroup, progressData, rowDoc.metric_name);
										}
									}
								}
								
								// Helper function to insert progress info
								function insertProgressInfo(targetElement, progressData, metricName, isRowWrapper = false) {
									// Remove existing child progress info if any
									targetElement.next('.child-kra-progress-info').remove();
									targetElement.find('.child-kra-progress-info').remove();
									
									// Create child progress info HTML
									const childProgressHtml = $(`
										<div class="child-kra-progress-info" style="
											margin-top: 6px;
											padding: 6px 8px;
											background: #f0f7ff;
											border-left: 3px solid ${getProgressColor(progressData.average_progress)};
											border-radius: 2px;
											font-size: 10px;
											${isRowWrapper ? 'margin-left: 15px;' : ''}
										">
											<div style="display: flex; align-items: center; gap: 8px; margin-bottom: 4px;">
												<i class="fa fa-sitemap" style="font-size: 9px; color: #8d99a6;"></i>
												<span style="font-weight: 500; color: #36414c;">Child Progress:</span>
												<span style="font-weight: 600; color: ${getProgressColor(progressData.average_progress)};">
													${progressData.average_progress.toFixed(1)}%
												</span>
											</div>
											<div style="display: flex; align-items: center; gap: 6px;">
												<div style="flex: 1; height: 3px; background: #e9ecef; border-radius: 2px; overflow: hidden;">
													<div style="width: ${Math.min(progressData.average_progress, 100)}%; height: 100%; background: ${getProgressColor(progressData.average_progress)}; transition: width 0.3s;"></div>
												</div>
												<span style="color: #8d99a6; font-size: 9px; white-space: nowrap;">
													${progressData.child_okr_count} OKR${progressData.child_okr_count !== 1 ? 's' : ''}, ${progressData.child_measurable_count} Measurable${progressData.child_measurable_count !== 1 ? 's' : ''}
												</span>
											</div>
										</div>
									`);
									
									// Insert after the target element
									targetElement.after(childProgressHtml);
								}
							}
						};
						
						// Store progress data for later use
						grid._childKRAProgressData = kraProgressMap;
						
						// Function to add progress to a specific row (only if open)
						const tryAddProgressToRow = (row) => {
							// Find the row element in DOM
							let $rowEl = null;
							if (row.row) {
								$rowEl = $(row.row);
							} else if (row.$row) {
								$rowEl = row.$row;
							} else if (row.doc && row.doc.idx) {
								$rowEl = grid.wrapper.find(`[data-idx="${row.doc.idx}"]`);
							}
							
							if ($rowEl && $rowEl.length) {
								const isOpen = $rowEl.hasClass('grid-row-open');
								if (isOpen) {
									addProgressToRow(row);
								}
							}
						};
						
						// Process initially open rows
						grid.grid_rows.forEach((row) => {
							tryAddProgressToRow(row);
						});
						
						// Function to hook into a row's toggle_view
						const hookRowToggle = (row) => {
							if (row.toggle_view && !row._kraProgressHooked) {
								row._kraProgressHooked = true;
								const originalToggle = row.toggle_view;
								row.toggle_view = function(show, callback) {
									const result = originalToggle.apply(this, arguments);
									if (show) {
										// Row is being opened - wait for form to render
										setTimeout(() => {
											console.log('✅ Row opened, adding progress for:', this.doc?.metric_name);
											addProgressToRow(this);
										}, 1000);
									}
									return result;
								};
							}
						};
						
						// Hook into all existing rows
						grid.grid_rows.forEach((row) => {
							hookRowToggle(row);
						});
						
						// Function to check and add progress to open rows
						const checkAndAddProgressToOpenRows = () => {
							grid.grid_rows.forEach((row) => {
								if (row.doc && row.doc.metric_name && kraProgressMap[row.doc.metric_name]) {
									// Find row element
									let $rowEl = null;
									if (row.row) {
										$rowEl = $(row.row);
									} else if (row.doc && row.doc.idx) {
										$rowEl = grid.wrapper.find(`[data-idx="${row.doc.idx}"]`);
									}
									
									if ($rowEl && $rowEl.length && $rowEl.hasClass('grid-row-open')) {
										// Check if progress info already exists
										if (!$rowEl.find('.child-kra-progress-info').length) {
											console.log('Found open row without progress, adding:', row.doc.metric_name);
											addProgressToRow(row);
										}
									}
								}
							});
						};
						
						// Use MutationObserver to watch for when rows open (with throttling)
						let checkTimeout = null;
						const throttledCheck = () => {
							clearTimeout(checkTimeout);
							checkTimeout = setTimeout(() => {
								checkAndAddProgressToOpenRows();
							}, 500);
						};
						
						if (grid.wrapper && grid.wrapper.length) {
							const observer = new MutationObserver((mutations) => {
								let shouldCheck = false;
								mutations.forEach((mutation) => {
									if (mutation.type === 'attributes' && mutation.attributeName === 'class') {
										const target = $(mutation.target);
										if (target.hasClass('grid-row-open')) {
											shouldCheck = true;
										}
									} else if (mutation.type === 'childList') {
										shouldCheck = true;
									}
								});
								if (shouldCheck) {
									throttledCheck();
								}
							});
							
							observer.observe(grid.wrapper[0], {
								childList: true,
								subtree: true,
								attributes: true,
								attributeFilter: ['class']
							});
						}
						
						// Also check periodically as backup
						setInterval(checkAndAddProgressToOpenRows, 2000);
						
						// Also listen for new rows that might be added later
						const originalAddNewRow = grid.add_new_row;
						if (originalAddNewRow) {
							grid.add_new_row = function(idx, callback, show, copy_doc, go_to_last_page, go_to_first_page) {
								const result = originalAddNewRow.apply(this, arguments);
								// After new row is added, hook into its toggle_view if it opens
								setTimeout(() => {
									if (this.grid_rows && this.grid_rows.length > 0) {
										const lastRow = this.grid_rows[this.grid_rows.length - 1];
										if (lastRow && lastRow.toggle_view && !lastRow._kraProgressHooked) {
											lastRow._kraProgressHooked = true;
											const originalToggle = lastRow.toggle_view;
											lastRow.toggle_view = function(show, callback) {
												const toggleResult = originalToggle.apply(this, arguments);
												if (show) {
													setTimeout(() => {
														addProgressToRow(this);
													}, 800);
												}
												return toggleResult;
											};
										}
									}
								}, 100);
								return result;
							};
						}
					} else {
						console.log('Grid not found');
					}
				}, 800);
			} else {
				console.log('No child KRA progress data returned');
			}
		}
	});
}

// Add child KRA progress to measurable rows (in child table) - legacy function
function addChildKRAProgressToMeasurables(frm) {
	if (!frm.doc.name || frm.is_new()) {
		return;
	}
	
	// Get child KRA progress data
	frappe.call({
		method: 'phamos.okr_addon.doctype.okr.okr.get_child_kra_progress',
		args: {
			okr_name: frm.doc.name
		},
		callback: function(r) {
			if (r.message && r.message.length > 0) {
				// Create a map of KR name to progress data
				const kraProgressMap = {};
				r.message.forEach(kraData => {
					kraProgressMap[kraData.parent_kr_name] = kraData;
				});
				
				// Wait for grid to be ready, then add progress info to each row
				setTimeout(() => {
					if (frm.fields_dict.measurables && frm.fields_dict.measurables.grid) {
						const grid = frm.fields_dict.measurables.grid;
						
						// Function to add progress to a specific row
						const addProgressToRow = (row) => {
							// Get the row wrapper - try different properties
							let rowWrapper = null;
							if (row.$wrapper) {
								rowWrapper = $(row.$wrapper);
							} else if (row.wrapper) {
								rowWrapper = $(row.wrapper);
							} else if (row.row) {
								rowWrapper = $(row.row);
							} else if (row.$row) {
								rowWrapper = $(row.$row);
							} else {
								// Try to find the row element by data-idx
								const rowDoc = row.doc;
								if (rowDoc && rowDoc.idx) {
									rowWrapper = grid.wrapper.find(`[data-idx="${rowDoc.idx}"]`);
								}
							}
							
							if (!rowWrapper || rowWrapper.length === 0) {
								return;
							}
							
							const rowDoc = row.doc;
							// Use stored progress data if available, otherwise use current map
							const progressMap = grid._childKRAProgressData || kraProgressMap;
							
							if (rowDoc && rowDoc.metric_name && progressMap[rowDoc.metric_name]) {
								const progressData = progressMap[rowDoc.metric_name];
								
								// Find the percent_complete field control - try multiple methods
								let formGroup = null;
								
								// Method 1: Find by data-fieldname
								let percentCompleteControl = rowWrapper.find('[data-fieldname="percent_complete"]');
								if (percentCompleteControl && percentCompleteControl.length) {
									formGroup = percentCompleteControl.closest('.form-group');
								}
								
								// Method 2: Find by control class
								if (!formGroup || formGroup.length === 0) {
									percentCompleteControl = rowWrapper.find('.control[data-fieldname="percent_complete"]');
									if (percentCompleteControl && percentCompleteControl.length) {
										formGroup = percentCompleteControl.closest('.form-group');
									}
								}
								
								// Method 3: Find by input field
								if (!formGroup || formGroup.length === 0) {
									percentCompleteControl = rowWrapper.find('input[data-fieldname="percent_complete"]');
									if (percentCompleteControl && percentCompleteControl.length) {
										formGroup = percentCompleteControl.closest('.form-group');
									}
								}
								
								// Method 4: Find by label text
								if (!formGroup || formGroup.length === 0) {
									const labels = rowWrapper.find('label');
									if (labels && labels.length > 0) {
										labels.each(function() {
											const $label = $(this);
											const labelText = $label.text();
											if (labelText.includes('% Complete') || labelText.includes('Complete')) {
												formGroup = $label.closest('.form-group');
												return false; // break
											}
										});
									}
								}
								
								// Method 5: Find all form-groups and check for percent_complete
								if (!formGroup || formGroup.length === 0) {
									const formGroups = rowWrapper.find('.form-group');
									if (formGroups && formGroups.length > 0) {
										formGroups.each(function() {
											const $formGroup = $(this);
											const labelText = $formGroup.find('label').text();
											if (labelText.includes('% Complete') || labelText.includes('Complete') || 
											    $formGroup.find('[data-fieldname="percent_complete"]').length > 0) {
												formGroup = $formGroup;
												return false; // break
											}
										});
									}
								}
								
								// Check if row is actually open by looking at the DOM element
								let isRowOpen = false;
								let $rowEl = null;
								
								if (row.row) {
									$rowEl = $(row.row);
									isRowOpen = $rowEl.hasClass('grid-row-open');
								} else if (row.$row) {
									$rowEl = row.$row;
									isRowOpen = $rowEl.hasClass('grid-row-open');
								} else if (rowDoc && rowDoc.idx) {
									$rowEl = grid.wrapper.find(`[data-idx="${rowDoc.idx}"]`);
									isRowOpen = $rowEl.hasClass('grid-row-open');
								} else {
									// Try to find row element from wrapper
									$rowEl = rowWrapper.closest('.grid-row');
									if ($rowEl && $rowEl.length) {
										isRowOpen = $rowEl.hasClass('grid-row-open');
									}
								}
								
								// If still not found, check if rowWrapper itself contains the open class
								if (!isRowOpen && rowWrapper) {
									$rowEl = rowWrapper.closest('.grid-row');
									if ($rowEl && $rowEl.length) {
										isRowOpen = $rowEl.hasClass('grid-row-open');
									}
								}
								
								if (!isRowOpen) {
									return;
								}
								
								if (formGroup && formGroup.length) {
									insertProgressInfo(formGroup, progressData, rowDoc.metric_name);
								} else {
									// Try to find any form-group in the open row
									const allFormGroups = rowWrapper.find('.form-group');
									if (allFormGroups && allFormGroups.length > 0) {
										// Find the one with percent_complete or use the last one
										let targetFormGroup = null;
										allFormGroups.each(function() {
											const $formGroup = $(this);
											const labelText = $formGroup.find('label').text();
											if ($formGroup.find('[data-fieldname="percent_complete"]').length > 0 ||
											    labelText.includes('Complete') || labelText.includes('%')) {
												targetFormGroup = $formGroup;
												return false;
											}
										});
										if (!targetFormGroup) {
											targetFormGroup = allFormGroups.last();
										}
										if (targetFormGroup) {
											insertProgressInfo(targetFormGroup, progressData, rowDoc.metric_name);
										}
									}
								}
								
								// Helper function to insert progress info
								function insertProgressInfo(targetElement, progressData, metricName, isRowWrapper = false) {
									// Remove existing child progress info if any
									targetElement.next('.child-kra-progress-info').remove();
									targetElement.find('.child-kra-progress-info').remove();
									
									// Create child progress info HTML
									const childProgressHtml = $(`
										<div class="child-kra-progress-info" style="
											margin-top: 6px;
											padding: 6px 8px;
											background: #f0f7ff;
											border-left: 3px solid ${getProgressColor(progressData.average_progress)};
											border-radius: 2px;
											font-size: 10px;
											${isRowWrapper ? 'margin-left: 15px;' : ''}
										">
											<div style="display: flex; align-items: center; gap: 8px; margin-bottom: 4px;">
												<i class="fa fa-sitemap" style="font-size: 9px; color: #8d99a6;"></i>
												<span style="font-weight: 500; color: #36414c;">Child Progress:</span>
												<span style="font-weight: 600; color: ${getProgressColor(progressData.average_progress)};">
													${progressData.average_progress.toFixed(1)}%
												</span>
											</div>
											<div style="display: flex; align-items: center; gap: 6px;">
												<div style="flex: 1; height: 3px; background: #e9ecef; border-radius: 2px; overflow: hidden;">
													<div style="width: ${Math.min(progressData.average_progress, 100)}%; height: 100%; background: ${getProgressColor(progressData.average_progress)}; transition: width 0.3s;"></div>
												</div>
												<span style="color: #8d99a6; font-size: 9px; white-space: nowrap;">
													${progressData.child_okr_count} OKR${progressData.child_okr_count !== 1 ? 's' : ''}, ${progressData.child_measurable_count} Measurable${progressData.child_measurable_count !== 1 ? 's' : ''}
												</span>
											</div>
										</div>
									`);
									
									// Insert after the target element
									targetElement.after(childProgressHtml);
								}
							}
						};
						
						// Store progress data for later use
						grid._childKRAProgressData = kraProgressMap;
						
						// Function to add progress to a specific row (only if open)
						const tryAddProgressToRow = (row) => {
							// Find the row element in DOM
							let $rowEl = null;
							if (row.row) {
								$rowEl = $(row.row);
							} else if (row.$row) {
								$rowEl = row.$row;
							} else if (row.doc && row.doc.idx) {
								$rowEl = grid.wrapper.find(`[data-idx="${row.doc.idx}"]`);
							}
							
							if ($rowEl && $rowEl.length) {
								const isOpen = $rowEl.hasClass('grid-row-open');
								if (isOpen) {
									addProgressToRow(row);
								}
							}
						};
						
						// Process initially open rows
						grid.grid_rows.forEach((row) => {
							tryAddProgressToRow(row);
						});
						
						// Function to hook into a row's toggle_view
						const hookRowToggle = (row) => {
							if (row.toggle_view && !row._kraProgressHooked) {
								row._kraProgressHooked = true;
								const originalToggle = row.toggle_view;
								row.toggle_view = function(show, callback) {
									const result = originalToggle.apply(this, arguments);
									if (show) {
										// Row is being opened - wait for form to render
										setTimeout(() => {
											console.log('✅ Row opened, adding progress for:', this.doc?.metric_name);
											addProgressToRow(this);
										}, 1000);
									}
									return result;
								};
							}
						};
						
						// Hook into all existing rows
						grid.grid_rows.forEach((row) => {
							hookRowToggle(row);
						});
						
						// Function to check and add progress to open rows
						const checkAndAddProgressToOpenRows = () => {
							grid.grid_rows.forEach((row) => {
								if (row.doc && row.doc.metric_name && kraProgressMap[row.doc.metric_name]) {
									// Find row element
									let $rowEl = null;
									if (row.row) {
										$rowEl = $(row.row);
									} else if (row.doc && row.doc.idx) {
										$rowEl = grid.wrapper.find(`[data-idx="${row.doc.idx}"]`);
									}
									
									if ($rowEl && $rowEl.length && $rowEl.hasClass('grid-row-open')) {
										// Check if progress info already exists
										if (!$rowEl.find('.child-kra-progress-info').length) {
											console.log('Found open row without progress, adding:', row.doc.metric_name);
											addProgressToRow(row);
										}
									}
								}
							});
						};
						
						// Use MutationObserver to watch for when rows open (with throttling)
						let checkTimeout = null;
						const throttledCheck = () => {
							clearTimeout(checkTimeout);
							checkTimeout = setTimeout(() => {
								checkAndAddProgressToOpenRows();
							}, 500);
						};
						
						if (grid.wrapper && grid.wrapper.length) {
							const observer = new MutationObserver((mutations) => {
								let shouldCheck = false;
								mutations.forEach((mutation) => {
									if (mutation.type === 'attributes' && mutation.attributeName === 'class') {
										const target = $(mutation.target);
										if (target.hasClass('grid-row-open')) {
											shouldCheck = true;
										}
									} else if (mutation.type === 'childList') {
										shouldCheck = true;
									}
								});
								if (shouldCheck) {
									throttledCheck();
								}
							});
							
							observer.observe(grid.wrapper[0], {
								childList: true,
								subtree: true,
								attributes: true,
								attributeFilter: ['class']
							});
						}
						
						// Also check periodically as backup
						setInterval(checkAndAddProgressToOpenRows, 2000);
						
						// Also listen for new rows that might be added later
						const originalAddNewRow = grid.add_new_row;
						if (originalAddNewRow) {
							grid.add_new_row = function(idx, callback, show, copy_doc, go_to_last_page, go_to_first_page) {
								const result = originalAddNewRow.apply(this, arguments);
								// After new row is added, hook into its toggle_view if it opens
								setTimeout(() => {
									if (this.grid_rows && this.grid_rows.length > 0) {
										const lastRow = this.grid_rows[this.grid_rows.length - 1];
										if (lastRow && lastRow.toggle_view && !lastRow._kraProgressHooked) {
											lastRow._kraProgressHooked = true;
											const originalToggle = lastRow.toggle_view;
											lastRow.toggle_view = function(show, callback) {
												const toggleResult = originalToggle.apply(this, arguments);
												if (show) {
													setTimeout(() => {
														addProgressToRow(this);
													}, 800);
												}
												return toggleResult;
											};
										}
									}
								}, 100);
								return result;
							};
						}
					} else {
						console.log('Grid not found');
					}
				}, 800);
			} else {
				console.log('No child KRA progress data returned');
			}
		}
	});
}

function getProgressColor(progress) {
	if (progress >= 100) return '#27ae60';
	if (progress >= 70) return '#3498db';
	if (progress >= 40) return '#f39c12';
	return '#e74c3c';
}

