function register_checklist_popup_handlers(doctypes) {
	if (!Array.isArray(doctypes) || !doctypes.length) {
		return;
	}

	doctypes.forEach((doctype) => {
		frappe.ui.form.on(doctype, {
			onload(frm) {
				frm.__checklist_dialog_shown_for = null;
			},

			refresh(frm) {
				if (frm.is_new() || !frm.doc.name) {
					return;
				}

				if (frm.__checklist_dialog_shown_for === frm.doc.name) {
					return;
				}

				frm.__checklist_dialog_shown_for = frm.doc.name;

				requestAnimationFrame(() => {
					setTimeout(() => {
						show_linked_checklists_dialog(frm);
					}, 100);
				});
			},
		});
	});

	if (window.cur_frm && doctypes.includes(cur_frm.doctype)) {
		cur_frm.trigger("refresh");
	}
}

frappe.call({
	method: "phamos.api.get_popup_doctypes",
	callback(r) {
		register_checklist_popup_handlers(r.message || []);
	},
	error(r) {
		console.error("Failed to load popup doctypes", r);
	},
});

function show_linked_checklists_dialog(frm) {
	frappe.call({
		method: "phamos.phamos.doctype.marketing_content.marketing_content.get_linked_checklists",
		args: {
			doctype: frm.doctype,
			name: frm.doc.name,
		},
		callback(r) {
			const checklists = r.message || [];

			if (!checklists.length) {
				return;
			}

			const dialog = new frappe.ui.Dialog({
				title: __("Linked Checklist Overview"),
				size: "large",
				fields: [
					{
						fieldtype: "HTML",
						fieldname: "linked_checklists_html",
					},
				],
				primary_action_label: __("Close"),
				primary_action() {
					dialog.hide();
				},
			});

			const $wrapper = dialog.fields_dict.linked_checklists_html.$wrapper;
			$wrapper.html(build_checklist_dialog_html(checklists));
			bind_checklist_dialog_events(dialog, frm, checklists);

			dialog.show();
		},
	});
}

function build_checklist_dialog_html(checklists) {
	const rows = checklists
		.map((row) => {
			const percentage = row.completion_percentage || 0;

			const badge_color = {
				Completed: "green",
				"In Progress": "orange",
				"Not Started": "gray",
			}[row.status] || "blue";

			const escaped_name = frappe.utils.escape_html(row.name);
			return `
				<tr class="checklist-summary-row" data-checklist-name="${escaped_name}">
					<td>
						<button type="button" class="btn btn-link p-0 checklist-toggle" data-checklist-name="${escaped_name}">
							<span class="checklist-caret">▶</span>
							<span>${escaped_name}</span>
						</button>
						<a href="/app/checklist/${encodeURIComponent(row.name)}" target="_blank" class="ml-2 text-muted" title="${__("Open checklist")}">↗</a>
					</td>

					<td>
						<span class="indicator ${badge_color} checklist-status" data-checklist-name="${escaped_name}">
							${frappe.utils.escape_html(row.status || "-")}
						</span>
					</td>

					<td style="min-width:220px;">
						<div class="progress">
							<div
								class="progress-bar bg-success checklist-progress-bar"
								data-checklist-name="${escaped_name}"
								role="progressbar"
								style="width:${percentage}%"
								aria-valuenow="${percentage}"
								aria-valuemin="0"
								aria-valuemax="100"
							>
								${format_percentage(percentage)}%
							</div>
						</div>
					</td>
				</tr>
				<tr class="checklist-detail-row" data-checklist-name="${escaped_name}" style="display:none;">
					<td colspan="3">
						<div class="checklist-items-container" data-checklist-name="${escaped_name}">
							<div class="text-muted">${__("Click to load items")}</div>
						</div>
					</td>
				</tr>
			`;
		})
		.join("");

	return `
		<div style="max-height:400px; overflow:auto;">
			<table class="table table-bordered table-hover">
				<thead>
					<tr>
						<th>${__("Checklist")}</th>
						<th>${__("Status")}</th>
						<th>${__("Completion")}</th>
					</tr>
				</thead>
				<tbody>
					${rows}
				</tbody>
			</table>
		</div>
	`;
}

function bind_checklist_dialog_events(dialog, frm, checklists) {
	const $wrapper = dialog.fields_dict.linked_checklists_html.$wrapper;
	const loadedChecklists = new Set();

	$wrapper.on("click", ".checklist-toggle", function (event) {
		event.preventDefault();
		const checklistName = $(this).data("checklistName");
		toggle_checklist_row($wrapper, checklistName);

		if (!loadedChecklists.has(checklistName)) {
			load_checklist_items($wrapper, checklistName, frm);
			loadedChecklists.add(checklistName);
		}
	});

	$wrapper.on("change", ".checklist-item-done", function () {
		const $input = $(this);
		const checklistName = $input.data("checklistName");
		const itemName = $input.data("itemName");
		const done = $input.prop("checked") ? 1 : 0;

		save_checklist_item_changes($wrapper, frm, checklistName, itemName, { done }, $input);
	});

	$wrapper.on("blur", ".checklist-item-description", function () {
		const $input = $(this);
		const checklistName = $input.data("checklistName");
		const itemName = $input.data("itemName");
		const description = $input.val();

		save_checklist_item_changes($wrapper, frm, checklistName, itemName, { description }, $input);
	});

	$wrapper.on("blur", ".checklist-item-note", function () {
		const $input = $(this);
		const checklistName = $input.data("checklistName");
		const itemName = $input.data("itemName");
		const note = $input.val();

		save_checklist_item_changes($wrapper, frm, checklistName, itemName, { note }, $input);
	});
}

function toggle_checklist_row($wrapper, checklistName) {
	const $detailRow = $wrapper.find(`.checklist-detail-row[data-checklist-name="${escape_selector_value(checklistName)}"]`);
	const $caret = $wrapper.find(`.checklist-toggle[data-checklist-name="${escape_selector_value(checklistName)}"] .checklist-caret`);
	const isVisible = $detailRow.is(":visible");

	$detailRow.toggle(!isVisible);
	$caret.text(isVisible ? "▶" : "▼");
}

function load_checklist_items($wrapper, checklistName, frm) {
	const $container = $wrapper.find(`.checklist-items-container[data-checklist-name="${escape_selector_value(checklistName)}"]`);
	$container.html(`<div class="text-muted">${__("Loading items...")}</div>`);

	frappe.call({
		method: "phamos.phamos.doctype.checklist.checklist.get_checklist_details",
		args: {
			checklist_name: checklistName,
		},
		callback(r) {
			const payload = r.message || {};
			const items = payload.items || [];
			$container.html(build_checklist_items_table(checklistName, items));
			initialize_checklist_link_controls($container, $wrapper, frm);
			update_checklist_summary_row($wrapper, checklistName, payload.status, payload.completion_percentage);
		},
		error() {
			$container.html(`<div class="text-danger">${__("Failed to load checklist items")}</div>`);
		},
	});
}

function build_checklist_items_table(checklistName, items) {
	if (!items.length) {
		return `<div class="text-muted">${__("No checklist items")}</div>`;
	}

	const rows = items
		.map((item) => {
			const escapedItemName = frappe.utils.escape_html(item.name);
			const escapedChecklistName = frappe.utils.escape_html(checklistName);
			const safeDescription = frappe.utils.escape_html(item.description || "");
			const safeNote = frappe.utils.escape_html(item.note || "");
			const safeDocument = frappe.utils.escape_html(item.document || "");
			const safeRecord = frappe.utils.escape_html(item.record || "");

			return `
				<tr
					class="checklist-item-row"
					data-checklist-name="${escapedChecklistName}"
					data-item-name="${escapedItemName}"
					data-document="${safeDocument}"
					data-record="${safeRecord}"
				>
					<td style="width:70px;">
						<input
							type="checkbox"
							class="checklist-item-done"
							data-checklist-name="${escapedChecklistName}"
							data-item-name="${escapedItemName}"
							${item.done ? "checked" : ""}
						/>
					</td>
					<td>
						<input
							type="text"
							class="form-control checklist-item-description mb-2"
							data-checklist-name="${escapedChecklistName}"
							data-item-name="${escapedItemName}"
							placeholder="${__("Description")}"
							value="${safeDescription}"
						/>
						<textarea
							class="form-control checklist-item-note"
							data-checklist-name="${escapedChecklistName}"
							data-item-name="${escapedItemName}"
							rows="2"
							placeholder="${__("Note")}"
						>${safeNote}</textarea>
					</td>
					<td style="width:180px;">
						<div class="checklist-item-document-link"></div>
					</td>
					<td style="width:220px;">
						<div class="checklist-item-record-link"></div>
					</td>
				</tr>
			`;
		})
		.join("");

	return `
		<div class="small text-muted mb-2">${__("Changes are saved immediately")}</div>
		<div style="overflow:auto;">
			<table class="table table-sm table-bordered mb-0">
				<thead>
					<tr>
						<th>${__("Done")}</th>
						<th>${__("Description / Note")}</th>
						<th>${__("Document")}</th>
						<th>${__("Record")}</th>
					</tr>
				</thead>
				<tbody>
					${rows}
				</tbody>
			</table>
		</div>
	`;
}

function save_checklist_item_changes($wrapper, frm, checklistName, itemName, values, $control) {
	if (!checklistName || !itemName) {
		return;
	}

	const saveKey = `${checklistName}::${itemName}`;
	const payload = {
		checklistName,
		itemName,
		values,
	};

	if (!window.__phamos_checklist_save_state) {
		window.__phamos_checklist_save_state = {};
	}

	if (!window.__phamos_checklist_save_state[saveKey]) {
		window.__phamos_checklist_save_state[saveKey] = {
			inFlight: false,
			lastPayloadHash: null,
			queuedPayload: null,
			queuedControl: null,
		};
	}

	const state = window.__phamos_checklist_save_state[saveKey];
	const payloadHash = JSON.stringify(payload.values || {});

	if (state.inFlight) {
		state.queuedPayload = payload;
		state.queuedControl = $control;
		return;
	}

	if (state.lastPayloadHash === payloadHash) {
		return;
	}

	state.inFlight = true;
	state.lastPayloadHash = payloadHash;

	toggle_control_saving_state($control, true);

	frappe.call({
		method: "phamos.phamos.doctype.checklist.checklist.update_checklist_item",
		args: {
			checklist_name: checklistName,
			item_name: itemName,
			values,
		},
		callback(r) {
			const payload = r.message || {};
			update_checklist_summary_row($wrapper, checklistName, payload.status, payload.completion_percentage);
			toggle_control_saving_state($control, false);
			state.inFlight = false;

			if (state.queuedPayload) {
				const nextPayload = state.queuedPayload;
				const nextControl = state.queuedControl;
				state.queuedPayload = null;
				state.queuedControl = null;
				save_checklist_item_changes(
					$wrapper,
					frm,
					nextPayload.checklistName,
					nextPayload.itemName,
					nextPayload.values,
					nextControl
				);
			}
		},
		error() {
			toggle_control_saving_state($control, false);
			state.inFlight = false;
			frappe.show_alert({
				message: __("Failed to save checklist item"),
				indicator: "red",
			});

			if (state.queuedPayload) {
				const nextPayload = state.queuedPayload;
				const nextControl = state.queuedControl;
				state.queuedPayload = null;
				state.queuedControl = null;
				save_checklist_item_changes(
					$wrapper,
					frm,
					nextPayload.checklistName,
					nextPayload.itemName,
					nextPayload.values,
					nextControl
				);
			}
		},
	});
}

function update_checklist_summary_row($wrapper, checklistName, status, completionPercentage) {
	const percentage = Number(completionPercentage || 0);
	const badgeColor = {
		Completed: "green",
		"In Progress": "orange",
		"Not Started": "gray",
	}[status] || "blue";

	const statusText = status || "-";
	const escapedName = escape_selector_value(checklistName);
	const $status = $wrapper.find(`.checklist-status[data-checklist-name="${escapedName}"]`);
	const $progressBar = $wrapper.find(`.checklist-progress-bar[data-checklist-name="${escapedName}"]`);

	$status.removeClass("green orange gray blue").addClass(badgeColor).text(statusText);

	$progressBar
		.css("width", `${percentage}%`)
		.attr("aria-valuenow", percentage)
		.text(`${format_percentage(percentage)}%`);
}

function toggle_control_saving_state($control, isSaving) {
	if (!$control || !$control.length) {
		return;
	}

	$control.prop("disabled", isSaving);
	if (isSaving) {
		$control.addClass("disabled");
	} else {
		$control.removeClass("disabled");
	}
}

function format_percentage(value) {
	const number = Number(value || 0);
	if (Number.isInteger(number)) {
		return number;
	}

	return number.toFixed(1);
}

function escape_selector_value(value) {
	if (window.CSS && typeof window.CSS.escape === "function") {
		return window.CSS.escape(String(value));
	}

	return String(value).replace(/([ #;?%&,.+*~':\"!^$\[\]()=>|\/@])/g, "\\$1");
}

function initialize_checklist_link_controls($container, $wrapper, frm) {
	$container.find(".checklist-item-row").each(function () {
		const $row = $(this);
		const checklistName = $row.data("checklistName");
		const itemName = $row.data("itemName");
		const initialDocument = ($row.attr("data-document") || "").trim();
		const initialRecord = ($row.attr("data-record") || "").trim();

		const $documentHost = $row.find(".checklist-item-document-link");
		const $recordHost = $row.find(".checklist-item-record-link");

		const documentControl = create_checklist_link_control($documentHost, {
			label: __("Document"),
			options: "DocType",
			placeholder: __("DocType"),
			value: initialDocument,
		});

		const recordControl = create_checklist_link_control($recordHost, {
			label: __("Record"),
			options: initialDocument || "DocType",
			placeholder: __("Record"),
			value: initialRecord,
		});

		$row.data("currentDocument", initialDocument);

		documentControl.$input.on("change awesomplete-selectcomplete", () => {
			const selectedDocument = (documentControl.get_value() || "").trim();
			const previousDocument = ($row.data("currentDocument") || "").trim();

			recordControl.df.options = selectedDocument || "DocType";
			recordControl.refresh();

			if (selectedDocument !== previousDocument) {
				recordControl.set_value("");
			}

			$row.data("currentDocument", selectedDocument);
			save_checklist_item_changes(
				$wrapper,
				frm,
				checklistName,
				itemName,
				{ document: selectedDocument, record: recordControl.get_value() || "" },
				documentControl.$input
			);
		});

		recordControl.$input.on("change awesomplete-selectcomplete", () => {
			save_checklist_item_changes(
				$wrapper,
				frm,
				checklistName,
				itemName,
				{ document: documentControl.get_value() || "", record: recordControl.get_value() || "" },
				recordControl.$input
			);
		});
	});
}

function create_checklist_link_control($host, config) {
	const control = frappe.ui.form.make_control({
		parent: $host.get(0),
		df: {
			fieldtype: "Link",
			label: config.label || "",
			options: config.options || "DocType",
			placeholder: config.placeholder || "",
		},
		render_input: true,
	});

	control.refresh();
	control.set_value(config.value || "");

	return control;
}