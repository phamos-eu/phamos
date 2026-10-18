// Linked Checklists dialog on Desk forms (GitLab #973, #997, #1005).
//
// The doctypes come from phamos Settings > Checklist. The dialog opens by itself when a record
// has unfinished checklists, and the "Checklists" button opens it at any time. It follows the
// cockpit's LinkedChecklistsSection / ChecklistEditor: one card per checklist (open while
// unfinished), item cards that expand for editing, and every change saved at once through the
// same phamos.api.checklist_inbox endpoints, so nothing needs a reload of the parent record.
(() => {
	const API = "phamos.api.checklist_inbox";
	const CHEVRON = `<svg viewBox="0 0 24 24" width="14" height="14" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><polyline points="9 18 15 12 9 6"/></svg>`;
	const EXTERNAL_LINK = `<svg viewBox="0 0 24 24" width="12" height="12" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M18 13v6a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V8a2 2 0 0 1 2-2h6"/><polyline points="15 3 21 3 21 9"/><line x1="10" y1="14" x2="21" y2="3"/></svg>`;

	frappe.call({
		method: "phamos.api.get_popup_doctypes",
		callback(r) {
			register_checklist_popup_handlers(r.message || []);
		},
		error(r) {
			console.error("Failed to load popup doctypes", r);
		},
	});

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
					if (frm.is_new() || !frm.doc.name || !frappe.model.can_read("Checklist")) {
						return;
					}

					frm.add_custom_button(__("Checklists"), () => {
						new LinkedChecklistsDialog(frm).open({ only_if_unfinished: false });
					});

					if (frm.__checklist_dialog_shown_for === frm.doc.name) {
						return;
					}
					frm.__checklist_dialog_shown_for = frm.doc.name;

					requestAnimationFrame(() => {
						setTimeout(() => {
							new LinkedChecklistsDialog(frm).open({ only_if_unfinished: true });
						}, 100);
					});
				},
			});
		});

		if (window.cur_frm && doctypes.includes(cur_frm.doctype)) {
			cur_frm.trigger("refresh");
		}
	}

	class LinkedChecklistsDialog {
		constructor(frm) {
			this.frm = frm;
			this.can_write = frappe.model.can_write("Checklist");
			this.can_create = frappe.model.can_create("Checklist");
			this.summaries = [];
			this.expanded = {};
			this.details = {};
			// The one item being edited: { checklist, item, controls }.
			this.editing = null;
			// Saves run one after another per checklist; each one saves the whole parent doc.
			this.save_chains = {};
		}

		async open({ only_if_unfinished }) {
			let summaries;
			try {
				summaries = await frappe.xcall(`${API}.get_checklists_for_reference`, {
					document: this.frm.doctype,
					reference_record: this.frm.doc.name,
				});
			} catch (e) {
				return;
			}

			this.summaries = summaries || [];
			const unfinished = this.summaries.filter((row) => row.status !== "Completed");
			if (only_if_unfinished && !unfinished.length) {
				return;
			}

			this.make_dialog();
			this.summaries.forEach((row) => {
				this.expanded[row.name] = row.status !== "Completed";
			});
			this.render();
			this.dialog.show();

			await Promise.all(unfinished.map((row) => this.load_detail(row.name)));
		}

		make_dialog() {
			this.dialog = new frappe.ui.Dialog({
				title: __("Checklists"),
				size: "large",
				fields: [{ fieldtype: "HTML", fieldname: "checklists_html" }],
				primary_action_label: __("Close"),
				primary_action: () => this.dialog.hide(),
				secondary_action_label: this.can_create ? __("New checklist") : null,
				secondary_action: this.can_create
					? () => {
							this.dialog.hide();
							frappe.new_doc("Checklist", {
								document: this.frm.doctype,
								reference_record: this.frm.doc.name,
							});
					  }
					: null,
				on_hide: () => this.collapse_item(),
			});
			this.dialog.$wrapper.addClass("phamos-checklist-dialog");
			this.$body = this.dialog.fields_dict.checklists_html.$wrapper;
			this.bind_events();
		}

		bind_events() {
			const $body = this.$body;

			$body.on("click", ".pcl-card-header", (e) => {
				this.toggle_checklist($(e.currentTarget).closest(".pcl-card").attr("data-checklist"));
			});

			$body.on("click", ".pcl-item", (e) => {
				if ($(e.target).closest("a, input[type=checkbox]").length) {
					return;
				}
				const $item = $(e.currentTarget);
				this.expand_item($item.attr("data-checklist"), $item.attr("data-item"));
			});

			$body.on("keydown", ".pcl-item.collapsed", (e) => {
				if (e.key === "Enter") {
					e.preventDefault();
					$(e.currentTarget).trigger("click");
				}
			});

			$body.on("change", ".pcl-done", (e) => {
				const $input = $(e.currentTarget);
				const $item = $input.closest(".pcl-item");
				this.save_done($item.attr("data-checklist"), $item.attr("data-item"), $input);
			});

			$body.on("click", ".pcl-add-item", (e) => {
				this.add_item($(e.currentTarget).closest(".pcl-card").attr("data-checklist"));
			});

			$body.on("blur", ".pcl-description", () => this.save_editing_text());

			// A click anywhere outside the edited item closes it, like in the cockpit.
			this.dialog.$wrapper.on("mousedown", (e) => {
				if (!this.editing) {
					return;
				}
				const $target = $(e.target);
				const $editing = this.item_element(this.editing.checklist, this.editing.item);
				if (
					$target.closest($editing).length ||
					$target.closest(".pcl-item").length ||
					$target.closest(".awesomplete, .ql-tooltip, .ql-picker").length
				) {
					return;
				}
				this.collapse_item();
			});

			// Escape closes the edited item first and only then the dialog.
			this.dialog.$wrapper.get(0).addEventListener(
				"keydown",
				(e) => {
					if (e.key === "Escape" && this.editing) {
						e.preventDefault();
						e.stopPropagation();
						this.collapse_item();
					}
				},
				true
			);
		}

		// ----- rendering -----

		render() {
			if (!this.summaries.length) {
				this.$body.html(`<div class="pcl-empty">${__("No checklists linked yet.")}</div>`);
				return;
			}
			this.$body.html(`<div class="pcl-list">${this.summaries.map((row) => this.card_html(row)).join("")}</div>`);
			this.summaries.forEach((row) => this.render_card_body(row.name));
		}

		card_html(row) {
			const name = frappe.utils.escape_html(row.name);
			return `
				<div class="pcl-card" data-checklist="${name}">
					<button type="button" class="pcl-card-header">
						<span class="pcl-chevron">${CHEVRON}</span>
						<span class="pcl-card-title">${frappe.utils.escape_html(row.title || row.name)}</span>
						<span class="pcl-badge"></span>
					</button>
					<div class="pcl-card-body"></div>
				</div>
			`;
		}

		card_element(checklist) {
			return this.$body.find(`.pcl-card[data-checklist="${css_escape(checklist)}"]`);
		}

		item_element(checklist, item) {
			return this.card_element(checklist).find(`.pcl-item[data-item="${css_escape(item)}"]`);
		}

		render_card_header(checklist) {
			const row = this.summaries.find((r) => r.name === checklist);
			if (!row) {
				return;
			}
			const $card = this.card_element(checklist);
			$card.toggleClass("open", !!this.expanded[checklist]);
			$card
				.find(".pcl-badge")
				.html(
					`<span class="indicator-pill no-indicator-dot ${status_color(row.status)}">${frappe.utils.escape_html(
						__(row.status || "Not Started")
					)} ${cint(row.done_count)}/${cint(row.total_count)}</span>`
				);
		}

		render_card_body(checklist) {
			this.render_card_header(checklist);
			const $body = this.card_element(checklist).find(".pcl-card-body");
			if (!this.expanded[checklist]) {
				$body.empty();
				return;
			}

			const detail = this.details[checklist];
			if (!detail) {
				$body.html(`<div class="pcl-muted">${__("Loading items…")}</div>`);
				return;
			}

			const items = detail.items || [];
			const items_html = items.length
				? `<div class="pcl-items">${items.map((item) => this.item_html(checklist, item)).join("")}</div>`
				: `<div class="pcl-muted pcl-no-items">${__("No items yet")}</div>`;

			$body.html(`
				${items_html}
				<div class="pcl-card-footer">
					${
						this.can_write
							? `<button type="button" class="btn btn-default btn-xs pcl-add-item">${__("Add item")}</button>`
							: "<span></span>"
					}
					<a class="pcl-open-desk" href="/app/checklist/${encodeURIComponent(checklist)}" target="_blank" rel="noopener noreferrer">
						${EXTERNAL_LINK} ${__("Open in Desk")}
					</a>
				</div>
			`);
		}

		item_html(checklist, item) {
			const description = (item.description || "").trim();
			const has_note = !is_empty_html(item.note);
			let text = "";
			if (description) {
				text += `<div class="pcl-item-description">${frappe.utils.escape_html(description)}</div>`;
			}
			if (has_note) {
				text += `<div class="pcl-item-note${description ? " secondary" : ""}">${frappe.dom.remove_script_and_style(
					item.note
				)}</div>`;
			}
			if (!description && !has_note) {
				text += `<div class="pcl-placeholder">${this.can_write ? __("Click to edit…") : __("No description")}</div>`;
			}
			if (item.document && item.record) {
				text += `
					<a class="pcl-item-link" href="${frappe.utils.get_form_link(item.document, item.record)}" target="_blank" rel="noopener noreferrer">
						<span>${frappe.utils.escape_html(__(item.document))} · ${frappe.utils.escape_html(item.record)}</span>
						${EXTERNAL_LINK}
					</a>`;
			} else if (item.document) {
				text += `<div class="pcl-item-doctype">${frappe.utils.escape_html(__(item.document))}</div>`;
			}

			return `
				<div class="pcl-item collapsed${this.can_write ? " editable" : ""}"
					data-checklist="${frappe.utils.escape_html(checklist)}"
					data-item="${frappe.utils.escape_html(item.name)}"
					${this.can_write ? 'tabindex="0" role="button"' : ""}>
					<div class="pcl-item-row">
						<div class="pcl-item-text">${text}</div>
						${this.done_checkbox_html(item)}
					</div>
				</div>
			`;
		}

		done_checkbox_html(item) {
			return `
				<input type="checkbox" class="pcl-done" title="${__("Done")}"
					${item.done ? "checked" : ""} ${this.can_write ? "" : "disabled"} />
			`;
		}

		// ----- checklist cards -----

		async toggle_checklist(checklist) {
			if (this.editing?.checklist === checklist) {
				await this.collapse_item();
			}
			this.expanded[checklist] = !this.expanded[checklist];
			this.render_card_body(checklist);
			if (this.expanded[checklist] && !this.details[checklist]) {
				await this.load_detail(checklist);
			}
		}

		async load_detail(checklist) {
			try {
				this.details[checklist] = await frappe.xcall(`${API}.get_checklist`, { name: checklist });
			} catch (e) {
				this.card_element(checklist)
					.find(".pcl-card-body")
					.html(`<div class="text-danger">${__("Failed to load checklist items")}</div>`);
				return;
			}
			this.apply_summary(checklist, this.details[checklist]);
			if (this.editing?.checklist !== checklist) {
				this.render_card_body(checklist);
			}
		}

		// Takes the checklist a save returned: keeps the header in step and closes a checklist
		// that just got completed (and reopens one that no longer is).
		on_checklist_updated(checklist, payload, { rerender = true } = {}) {
			const previous_status = this.summaries.find((r) => r.name === checklist)?.status;
			this.details[checklist] = payload;
			this.apply_summary(checklist, payload);

			if (payload.status === "Completed" && previous_status !== "Completed" && !this.editing) {
				this.expanded[checklist] = false;
				rerender = true;
			} else if (previous_status === "Completed" && payload.status !== "Completed") {
				this.expanded[checklist] = true;
				rerender = true;
			}

			if (rerender && this.editing?.checklist !== checklist) {
				this.render_card_body(checklist);
			} else {
				this.render_card_header(checklist);
			}
		}

		apply_summary(checklist, payload) {
			const row = this.summaries.find((r) => r.name === checklist);
			if (!row || !payload) {
				return;
			}
			Object.assign(row, {
				status: payload.status,
				completion_percentage: payload.completion_percentage,
				done_count: payload.done_count,
				total_count: payload.total_count,
			});
		}

		// ----- item editing -----

		find_item(checklist, item) {
			return (this.details[checklist]?.items || []).find((row) => row.name === item) || null;
		}

		async expand_item(checklist, item_name, { focus = false } = {}) {
			if (!this.can_write) {
				return;
			}
			if (this.editing?.checklist === checklist && this.editing?.item === item_name) {
				return;
			}
			await this.collapse_item();

			const item = this.find_item(checklist, item_name);
			if (!item) {
				return;
			}
			const $item = this.item_element(checklist, item_name);
			$item.removeClass("collapsed").addClass("expanded").removeAttr("tabindex");
			$item.html(`
				<div class="pcl-item-row">
					<div class="pcl-item-editor">
						<input type="text" class="form-control pcl-description"
							placeholder="${__("Short description")}"
							value="${frappe.utils.escape_html(item.description || "")}" />
						<div class="pcl-note"></div>
					</div>
					${this.done_checkbox_html(item)}
				</div>
				<div class="pcl-links">
					<div class="pcl-document"></div>
					<div class="pcl-record"></div>
				</div>
			`);

			const note = frappe.ui.form.make_control({
				parent: $item.find(".pcl-note").get(0),
				df: {
					fieldtype: "Text Editor",
					fieldname: "note",
					placeholder: __("Item note…"),
					// A short menu like the cockpit note: bold, italic, link and lists.
					get_toolbar_options: () => [
						["bold", "italic", "link"],
						[{ list: "bullet" }, { list: "ordered" }],
						["clean"],
					],
					change: () => this.save_editing_text_soon(),
				},
				render_input: true,
			});
			note.set_value(item.note || "");

			const document = frappe.ui.form.make_control({
				parent: $item.find(".pcl-document").get(0),
				df: { fieldtype: "Link", fieldname: "document", label: __("Document"), options: "DocType" },
				render_input: true,
			});
			document.set_value(item.document || "");

			const record = frappe.ui.form.make_control({
				parent: $item.find(".pcl-record").get(0),
				df: {
					fieldtype: "Link",
					fieldname: "record",
					label: __("Record"),
					options: item.document || "DocType",
				},
				render_input: true,
			});
			record.set_value(item.record || "");
			$item.find(".pcl-record").toggle(!!item.document);

			this.editing = { checklist, item: item_name, controls: { note, document, record } };

			document.$input.on("change awesomplete-selectcomplete", () => this.on_document_change());
			record.$input.on("change awesomplete-selectcomplete", () => this.on_record_change());

			if (focus) {
				$item.find(".pcl-description").trigger("focus");
			}
		}

		// Saves what was typed, closes the item, and drops it again if it stayed empty.
		async collapse_item() {
			if (!this.editing) {
				return;
			}
			const { checklist, item } = this.editing;
			// Read the typed text and let go of the item before awaiting, so a second collapse
			// (a click outside followed by the dialog closing) finds nothing left to do.
			const values = this.editing_text_values();
			clearTimeout(this.text_timer);
			this.editing = null;
			if (Object.keys(values).length) {
				Object.assign(this.find_item(checklist, item), values);
				await this.save_item(checklist, item, values);
			}

			const row = this.find_item(checklist, item);
			if (row && is_empty_item(row)) {
				await this.run_save(checklist, () =>
					frappe.xcall(`${API}.delete_spa_checklist_item`, { checklist_name: checklist, item_name: item })
				);
			}

			const detail = this.details[checklist];
			if (detail?.status === "Completed") {
				this.expanded[checklist] = false;
			}
			this.render_card_body(checklist);
		}

		editing_text_values() {
			const { checklist, item, controls } = this.editing;
			const row = this.find_item(checklist, item);
			if (!row) {
				return {};
			}
			const $item = this.item_element(checklist, item);
			const description = $item.find(".pcl-description").val() ?? row.description;
			const note = controls.note.get_value() || "";
			const values = {};
			if ((description || "") !== (row.description || "")) {
				values.description = description;
			}
			if (is_empty_html(note) ? !is_empty_html(row.note) : note !== (row.note || "")) {
				values.note = is_empty_html(note) ? "" : note;
			}
			return values;
		}

		save_editing_text_soon() {
			clearTimeout(this.text_timer);
			this.text_timer = setTimeout(() => this.save_editing_text(), 800);
		}

		async save_editing_text() {
			clearTimeout(this.text_timer);
			if (!this.editing) {
				return;
			}
			const { checklist, item } = this.editing;
			const values = this.editing_text_values();
			if (!Object.keys(values).length) {
				return;
			}
			// Keep the local copy current, so a second call does not send the same text again.
			Object.assign(this.find_item(checklist, item), values);
			await this.save_item(checklist, item, values);
		}

		async on_document_change() {
			const { checklist, item, controls } = this.editing;
			const row = this.find_item(checklist, item);
			const document = (controls.document.get_value() || "").trim();
			if (!row || document === (row.document || "")) {
				return;
			}
			controls.record.df.options = document || "DocType";
			controls.record.refresh();
			controls.record.set_value("");
			this.item_element(checklist, item).find(".pcl-record").toggle(!!document);
			Object.assign(row, { document, record: "" });
			await this.save_item(checklist, item, { document, record: "" });
		}

		async on_record_change() {
			const { checklist, item, controls } = this.editing;
			const row = this.find_item(checklist, item);
			const record = (controls.record.get_value() || "").trim();
			if (!row || record === (row.record || "")) {
				return;
			}
			row.record = record;
			await this.save_item(checklist, item, { record });
		}

		async save_done(checklist, item, $input) {
			const done = $input.prop("checked") ? 1 : 0;
			$input.prop("disabled", true);
			if (this.editing?.checklist === checklist && this.editing?.item === item) {
				await this.save_editing_text();
			}
			const ok = await this.save_item(checklist, item, { done }, { rerender: true });
			$input.prop("disabled", false);
			if (!ok) {
				$input.prop("checked", !done);
			}
		}

		async add_item(checklist) {
			await this.collapse_item();
			const updated = await this.run_save(checklist, () =>
				frappe.xcall(`${API}.add_spa_checklist_item`, { checklist_name: checklist, values: {} })
			);
			const items = updated?.items || [];
			const newest = items[items.length - 1];
			if (newest) {
				await this.expand_item(checklist, newest.name, { focus: true });
			}
		}

		save_item(checklist, item, values, options = { rerender: false }) {
			return this.run_save(
				checklist,
				() =>
					frappe.xcall(`${API}.update_spa_checklist_item`, {
						checklist_name: checklist,
						item_name: item,
						values,
					}),
				options
			);
		}

		run_save(checklist, request, options = {}) {
			const previous = this.save_chains[checklist] || Promise.resolve();
			const next = previous.then(async () => {
				try {
					const payload = await request();
					this.on_checklist_updated(checklist, payload, options);
					return payload;
				} catch (e) {
					frappe.show_alert({ message: __("Failed to save checklist item"), indicator: "red" });
					return null;
				}
			});
			this.save_chains[checklist] = next;
			return next;
		}
	}

	function status_color(status) {
		return { Completed: "green", "In Progress": "orange" }[status] || "gray";
	}

	function is_empty_html(html) {
		if (!html) {
			return true;
		}
		const text = $("<div>").html(html).text().replace(/\u00a0/g, " ").trim();
		return !text && !/<(img|iframe|video)\b/i.test(html);
	}

	function is_empty_item(item) {
		return (
			!(item.description || "").trim() &&
			is_empty_html(item.note) &&
			!(item.document || "").trim() &&
			!(item.record || "").trim()
		);
	}

	function css_escape(value) {
		return window.CSS?.escape ? CSS.escape(String(value)) : String(value).replace(/["\\]/g, "\\$&");
	}
})();
