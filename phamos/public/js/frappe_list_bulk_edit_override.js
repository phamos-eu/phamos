/**
 * Frappe Bulk Edit Null-Label Fix
 *
 * Two-part fix for the crash in frappe/public/js/frappe/list/bulk_operations.js:
 *   TypeError: Cannot read properties of null/undefined (reading 'match')
 *   at set_value_field (bulk_operations.js:387)
 *
 * Root cause: ERPNext's timesheet.json has fields with label: null.
 * bulk_operations.js calls new_df.label.match() with no null guard.
 * Additionally, BulkOperations.edit() is triggered at menu-setup time
 * (via jQuery event cascade inside add_dropdown_item), at which point
 * dialog.get_value("field") returns undefined, so new_df comes back as {}
 * and new_df.label is undefined regardless of label fix.
 *
 * Part 1 — add_field patch (belt-and-suspenders):
 *   Patches frappe.meta.add_field so null labels never enter the meta system.
 *   Runs synchronously before $(document).ready so the patch is in place
 *   when frappe.model.sync(frappe.boot.docs) iterates all fields.
 *
 * Part 2 — safe bulk-edit override:
 *   Replaces the Edit action in ListView.get_actions_menu_items with a safe
 *   implementation that:
 *     a) Returns early (no-op) when nothing is checked — prevents the
 *        spurious call that happens at menu-build time.
 *     b) Guards new_df.label before calling .match() in set_value_field.
 *     c) Uses fieldname as the label key when field_doc.label is null,
 *        so field_mappings never has a null-keyed entry.
 */
(function () {
	"use strict";

	/* ── Part 1: add_field null-label guard ────────────────────────── */
	if (
		window.frappe &&
		frappe.meta &&
		typeof frappe.meta.add_field === "function" &&
		!frappe.meta._phamos_null_label_fix
	) {
		var _orig_add_field = frappe.meta.add_field;
		frappe.meta.add_field = function (df) {
			if (df && !df.label) {
				df.label = df.fieldname || df.fieldtype || "Unknown";
			}
			return _orig_add_field.call(this, df);
		};
		frappe.meta._phamos_null_label_fix = true;
		console.log("[phamos] Null-label guard active on frappe.meta.add_field");
	}

	/* ── Part 2: safe bulk-edit override ───────────────────────────── */

	/**
	 * Safe drop-in for BulkOperations.edit() with two null guards:
	 *  - Bails out silently when docnames is empty (setup-time spurious call)
	 *  - Guards new_df.label before .match() in set_value_field
	 */
	function phamos_safe_bulk_edit(listview, doctype) {
		var docnames = listview.get_checked_items(true);

		// Guard A: no-op if nothing is selected.  The edit action is
		// occasionally called at menu-build time (jQuery event cascade inside
		// page.add_dropdown_item); at that point nothing is checked.
		if (!docnames || !docnames.length) return;

		listview.disable_list_update = true;

		var status_regex = /status/i;

		function is_field_editable(field_doc) {
			return (
				field_doc.fieldname &&
				frappe.model.is_value_type(field_doc) &&
				field_doc.fieldtype !== "Read Only" &&
				!field_doc.hidden &&
				!field_doc.read_only &&
				!field_doc.is_virtual
			);
		}

		// Build field_mappings keyed by label, using fieldname as fallback
		// when label is null/empty so the key is never null.
		var field_mappings = {};
		frappe.meta.get_docfields(doctype).forEach(function (field_doc) {
			if (is_field_editable(field_doc)) {
				var label = field_doc.label || field_doc.fieldname;
				field_mappings[label] = Object.assign({}, field_doc, { label: label });
			}
		});

		var field_options = Object.keys(field_mappings).sort(function (a, b) {
			return __(cstr(field_mappings[a].label)).localeCompare(
				cstr(__(field_mappings[b].label))
			);
		});

		var default_field = field_options.find(function (v) {
			return status_regex.test(v);
		});

		var dialog = new frappe.ui.Dialog({
			title: __("Bulk Edit"),
			fields: [
				{
					fieldtype: "Select",
					options: field_options,
					default: default_field,
					label: __("Field"),
					fieldname: "field",
					reqd: 1,
					onchange: function () {
						set_value_field(dialog);
					},
				},
				{
					fieldtype: "Data",
					label: __("Value"),
					fieldname: "value",
					onchange: function () {
						show_help_text();
					},
				},
			],
			primary_action: function (args) {
				var value = args ? args.value : undefined;
				var selected_field = dialog.get_value("field");
				var field_doc = field_mappings[selected_field];
				if (!field_doc) return;
				var fieldname = field_doc.fieldname;
				dialog.disable_primary_action();
				frappe
					.call({
						method: "frappe.desk.doctype.bulk_update.bulk_update.submit_cancel_or_update_docs",
						args: {
							doctype: doctype,
							freeze: true,
							docnames: docnames,
							action: "update",
							data: { [fieldname]: value || null },
						},
					})
					.then(function (r) {
						var failed = r.message || [];
						if (failed.length && !r._server_messages) {
							dialog.enable_primary_action();
							frappe.throw(
								__(
									"Cannot update {0}",
									[
										failed
											.map(function (f) {
												return f.bold ? f.bold() : f;
											})
											.join(", "),
									]
								)
							);
						}
						listview.disable_list_update = false;
						listview.refresh();
						dialog.hide();
						frappe.show_alert(__("Updated successfully"));
					});
			},
			primary_action_label: __("Update {0} records", [docnames.length]),
		});

		if (default_field) set_value_field(dialog);
		show_help_text();

		function set_value_field(dialogObj) {
			var selected = dialogObj.get_value("field");

			// Guard B: bail out if selected field is null/undefined or missing
			// from field_mappings (can happen when dialog is not yet refreshed).
			if (!selected || !field_mappings[selected]) return;

			var new_df = Object.assign({}, field_mappings[selected]);

			// Guard C: check label is truthy before calling .match()
			if (
				new_df.label &&
				new_df.label.match(status_regex) &&
				new_df.fieldtype === "Select" &&
				!new_df.default
			) {
				var options = [];
				if (typeof new_df.options === "string") {
					options = new_df.options.split("\n");
				}
				new_df.default = options[0] || options[1];
			}
			new_df.label = __("Value");
			new_df.onchange = show_help_text;

			delete new_df.depends_on;
			dialogObj.replace_field("value", new_df);
			show_help_text();
		}

		function show_help_text() {
			var value = dialog.get_value("value");
			if (value == null || value === "") {
				dialog.set_df_property(
					"value",
					"description",
					__("You have not entered a value. The field will be set to empty.")
				);
			} else {
				dialog.set_df_property("value", "description", "");
			}
		}

		dialog.refresh();
		dialog.show();
	}

	function patch_bulk_edit() {
		if (!window.frappe || !frappe.views || !frappe.views.ListView) return false;
		if (frappe.views.ListView.prototype._phamos_bulk_edit_patched) return true;

		var _orig = frappe.views.ListView.prototype.get_actions_menu_items;

		frappe.views.ListView.prototype.get_actions_menu_items = function () {
			var items = _orig.call(this);
			var listview = this;
			var doctype = this.doctype;

			// Identify and replace the Edit action by its translated label
			var edit_label = __("Edit", null, "Button in list view actions menu");
			for (var i = 0; i < items.length; i++) {
				if (items[i].label === edit_label) {
					items[i].action = function () {
						phamos_safe_bulk_edit(listview, doctype);
					};
					break;
				}
			}
			return items;
		};

		frappe.views.ListView.prototype._phamos_bulk_edit_patched = true;
		console.log("[phamos] Safe bulk-edit override active on ListView.get_actions_menu_items");
		return true;
	}

	// list.bundle.js loads synchronously before app_include_js files,
	// so frappe.views.ListView should be available immediately.
	if (!patch_bulk_edit()) {
		// Fallback in case load order ever changes
		document.addEventListener("DOMContentLoaded", function () {
			patch_bulk_edit();
		});
	}
})();
