// Copyright (c) 2026, phamos.eu and contributors
// For license information, please see license.txt

frappe.ui.form.on("Bookstack Configuration", {
	onload(frm) {
		// Result of a sync started with "Sync All" (phamos.bookstack_integration.sync.run_sync_job).
		// Registered once per page load; the Bookstack Browser has a listener of its own.
		if (frappe._bookstack_sync_listener) return;
		frappe._bookstack_sync_listener = true;
		frappe.realtime.on("bookstack_sync_done", (stats) => {
			if (cur_frm?.doctype !== "Bookstack Configuration") return;
			bookstack_show_sync_result(stats);
			if (cur_frm.doc.name === stats.instance) cur_frm.reload_doc();
		});
	},
	refresh(frm) {
		if (!frm.is_new()) {
			frm.add_custom_button(__("Test Connection"), () => {
				frm.call("test_connection").then((r) => {
					if (r.message) frappe.show_alert({ message: r.message, indicator: "green" });
				});
			});

			frm.add_custom_button(__("Sync…"), () => bookstack_sync_dialog(frm), __("Actions"));

			frm.add_custom_button(__("Open Bookstack"), () => {
				if (frm.doc.instance_url) window.open(frm.doc.instance_url, "_blank");
			});

			frm.add_custom_button(__("Provision Users..."), () => {
				const d = new frappe.ui.Dialog({
					title: __("Provision Bookstack Users"),
					fields: [
						{
							fieldname: "users_csv",
							fieldtype: "Long Text",
							label: __("Users (one per line: name,email,role[,language])"),
							reqd: 1,
							description: __("Example: Alice Example,alice@example.com,Admin,en")
						},
						{ fieldname: "send_invite", fieldtype: "Check", label: __("Send Invite Email"), default: frm.doc.send_invite_by_default }
					],
					primary_action_label: __("Create"),
					primary_action(values) {
						frappe.call({
							method: "phamos.bookstack_integration.provisioning.bulk_create_users",
							args: {
								instance: frm.doc.name,
								users_csv: values.users_csv,
								send_invite: values.send_invite ? 1 : 0
							},
							freeze: true,
							freeze_message: __("Creating users...")
						}).then((r) => {
							d.hide();
							frappe.msgprint({ title: __("Provisioning result"), message: `<pre>${JSON.stringify(r.message, null, 2)}</pre>`, indicator: "green" });
						});
					}
				});
				d.show();
			}, __("Actions"));
		}
	}
});

// Parts of a sync, in the order the server runs them (phamos.bookstack_integration.sync.SYNC_STEPS, #2029).
// Functions, not top-level consts: Desk may evaluate a form script more than once.
function bookstack_sync_steps() {
	return [
	{ step: "roles", label: __("Roles") },
	{ step: "users", label: __("Users"), description: __("Links each user to the roles synced before.") },
	{ step: "books", label: __("Books") },
	{ step: "shelves", label: __("Shelves"), description: __("One call per shelf; links the books.") },
	{ step: "chapters", label: __("Chapters") },
	{ step: "pages", label: __("Pages") },
	{
		step: "content",
		label: __("Website content"),
		description: __("Copies the pages of books published on the website."),
	},
	];
}

function bookstack_step_labels() {
	// Same order as the server runs them: the removal comes right before the website copy.
	const labels = {};
	for (const s of bookstack_sync_steps()) {
		if (s.step === "content") labels.removed = __("Removed (deleted in BookStack)");
		labels[s.step] = s.label;
	}
	return labels;
}

function bookstack_sync_dialog(frm) {
	const steps_config = bookstack_sync_steps();
	let tree = null; // set once the tree has loaded; the selection is only saved then
	// Everyone who may read the configuration may sync; only those who may edit it change the
	// selection (save_sync_selection needs write). For the others the tree is shown read-only.
	const can_save = frappe.model.can_write("Bookstack Configuration");
	const d = new frappe.ui.Dialog({
		title: __("Sync from {0}", [frm.doc.title]),
		size: "large",
		fields: [
			{ fieldtype: "Heading", label: __("What to sync") },
			...steps_config.map((s, i) => ({
				fieldname: s.step,
				fieldtype: "Check",
				label: s.label,
				description: s.description,
				default: 1,
			})),
			{
				fieldname: "remove_deleted_records",
				fieldtype: "Check",
				label: __("Remove records deleted in BookStack"),
				description: __("Only for the ticked shelves, books, chapters and pages."),
				default: 1,
			},
			{ fieldtype: "Section Break", label: __("Books, chapters and pages") },
			{ fieldname: "tree_html", fieldtype: "HTML" },
		],
		primary_action_label: __("Sync"),
		primary_action(values) {
			const steps = steps_config.filter((s) => values[s.step]).map((s) => s.step);
			if (!steps.length) {
				frappe.msgprint(__("Choose at least one part to sync."));
				return;
			}
			(can_save ? bookstack_save_selection(frm, tree) : Promise.resolve())
				.then(() =>
					// A background job (#2004): a first copy of a big book takes minutes. The result
					// arrives as the realtime event "bookstack_sync_done" (see onload).
					frappe.xcall("phamos.bookstack_integration.sync.start_sync", {
						instance: frm.doc.name,
						steps,
						remove_deleted_records: values.remove_deleted_records ? 1 : 0,
					})
				)
				.then(() => {
					d.hide();
					frm.reload_doc();
					frappe.show_alert({
						message: __("Sync started in the background. The result shows here when it is done."),
						indicator: "blue",
					}, 10);
				});
		},
		// Only for those who may change the selection; Frappe would show a default button otherwise.
		...(can_save && {
			secondary_action_label: __("Save selection"),
			secondary_action() {
				if (!tree) return;
				bookstack_save_selection(frm, tree).then((r) => {
					d.hide();
					frappe.show_alert({
						message: __("Selection saved; {0} records removed from ERPNext.", [r.removed]),
						indicator: "green",
					});
					frm.reload_doc();
				});
			},
		}),
	});
	d.show();

	const $area = d.fields_dict.tree_html.$wrapper;
	$area.html(`<div class="text-muted small">${__("Loading books from BookStack…")}</div>`);
	frappe
		.xcall("phamos.bookstack_integration.selection.get_sync_tree", { instance: frm.doc.name })
		.then((books) => {
			tree = bookstack_render_tree($area, books, !can_save);
		})
		.catch(() => {
			$area.html(
				`<div class="text-danger small">${__(
					"BookStack could not be reached. The saved selection stays as it is."
				)}</div>`
			);
			d.get_secondary_btn().prop("disabled", true);
		});
}

// Checkbox tree (#2029): a parent's box sets everything under it; an unticked book or chapter
// greys out its contents, a parent with some unticked children shows a mixed state.
function bookstack_render_tree($area, books, readonly = false) {
	const esc = frappe.utils.escape_html;
	// Under a left-out book or chapter everything shows unticked: the parent stands for all of it.
	const item = (n, parent_on = true) => {
		const on = n.included && parent_on;
		const box = `<input type="checkbox" class="bs-tree-box" data-type="${n.type}" data-id="${n.id}"
			data-title="${esc(n.title)}" ${on ? "checked" : ""}${readonly ? " disabled" : ""}>`;
		const label = `<label class="bs-tree-label">${box}<span>${esc(n.title)}</span>
			<span class="text-muted small">${__(n.type)}</span></label>`;
		if (!n.children.length) return `<li class="bs-tree-item">${label}</li>`;
		return `<li class="bs-tree-item"><details${n.type === "Chapter" ? " open" : ""}><summary>${label}
			<span class="text-muted small">(${n.children.length})</span></summary>
			<ul class="bs-tree-list">${n.children.map((c) => item(c, on)).join("")}</ul></details></li>`;
	};
	$area.html(`
		<style>
			.bs-tree-tools { display: flex; gap: 8px; align-items: center; margin-bottom: 8px; }
			.bs-tree-tools input { max-width: 260px; }
			.bs-tree { max-height: 380px; overflow-y: auto; border: 1px solid var(--border-color); border-radius: var(--border-radius); padding: 6px 10px; }
			.bs-tree-list { list-style: none; margin: 0; padding-left: 22px; }
			.bs-tree > .bs-tree-list { padding-left: 14px; }
			.bs-tree summary { list-style-position: outside; }
			.bs-tree-label { display: inline-flex; gap: 6px; align-items: center; margin: 2px 0; font-weight: normal; cursor: pointer; }
			/* Desk's checkbox style draws no mixed state; a dash on the ticked colour marks "partly". */
			.bs-tree-box:indeterminate { background: var(--gray-600) linear-gradient(#fff, #fff) center / 8px 2px no-repeat; border-color: var(--gray-600); }
			.bs-tree-item.bs-off > details > summary ~ *, .bs-tree-item.bs-off > details > summary ~ * label { opacity: 0.45; }
		</style>
		<div class="bs-tree-tools">
			<input type="search" class="form-control input-xs bs-tree-search" placeholder="${__("Filter books…")}">
			<button class="btn btn-xs btn-default bs-tree-all">${__("All")}</button>
			<button class="btn btn-xs btn-default bs-tree-none">${__("None")}</button>
			<span class="text-muted small bs-tree-count"></span>
		</div>
		<div class="text-muted small" style="margin-bottom:6px">${__(
			"Unticked books, chapters and pages are never mirrored into ERPNext, by any sync; their copies are removed when you save. New items in BookStack are synced."
		)}${readonly ? " " + __("Only users who may edit this configuration change the selection.") : ""}</div>
		<div class="bs-tree"><ul class="bs-tree-list">${books.map((b) => item(b)).join("")}</ul></div>`);

	const $boxes = () => $area.find(".bs-tree-box");
	const refresh = () => {
		$area.find(".bs-tree-item").each(function () {
			const $li = $(this);
			const box = $li.find("> label > .bs-tree-box, > details > summary .bs-tree-box").get(0);
			const below = $li.find("ul .bs-tree-box").toArray();
			$li.toggleClass("bs-off", !box.checked);
			box.indeterminate = box.checked && below.some((b) => !b.checked);
		});
		const roots = $area.find(".bs-tree > .bs-tree-list > .bs-tree-item");
		const on = roots.filter((_, li) => !$(li).hasClass("bs-off")).length;
		$area.find(".bs-tree-count").text(__("{0} of {1} books", [on, roots.length]));
	};
	$area.on("click", ".bs-tree-label", (e) => e.stopPropagation()); // ticking does not fold
	$area.on("change", ".bs-tree-box", function () {
		$(this).closest(".bs-tree-item").find("ul .bs-tree-box").prop("checked", this.checked);
		if (this.checked) {
			// A page ticked under an unticked chapter or book ticks them too (they show as partly
			// ticked); otherwise the left-out parent would still leave the page out.
			$(this)
				.parents(".bs-tree-item")
				.slice(1)
				.each(function () {
					$(this).find("> label > .bs-tree-box, > details > summary .bs-tree-box").prop("checked", true);
				});
		}
		refresh();
	});
	$area.find(".bs-tree-all, .bs-tree-none").on("click", function () {
		$boxes().prop("checked", $(this).hasClass("bs-tree-all"));
		refresh();
	});
	$area.find(".bs-tree-search").on("input", function () {
		const q = this.value.trim().toLowerCase();
		$area.find(".bs-tree > .bs-tree-list > .bs-tree-item").each(function () {
			// dataset, not jQuery's .data(): that turns titles like "2024" or "[1]" into numbers/arrays
			const title = ($(this).find(".bs-tree-box").get(0).dataset.title || "").toLowerCase();
			$(this).toggle(!q || title.includes(q));
		});
	});
	refresh();
	return $area;
}

// Left-out items, as few as possible: an unticked book or chapter stands for everything under it.
function bookstack_collect_exclusions($area) {
	const out = [];
	const walk = ($list) => {
		$list.children(".bs-tree-item").each(function () {
			const $li = $(this);
			const box = $li.find("> label > .bs-tree-box, > details > summary .bs-tree-box").get(0);
			if (!box.checked) {
				out.push({ item_type: box.dataset.type, bookstack_id: Number(box.dataset.id), title: box.dataset.title });
			} else {
				walk($li.find("> details > .bs-tree-list"));
			}
		});
	};
	walk($area.find(".bs-tree > .bs-tree-list"));
	return out;
}

function bookstack_save_selection(frm, $tree) {
	if (!$tree) return Promise.resolve({ removed: 0 }); // tree not loaded: keep the saved selection
	return frappe.xcall("phamos.bookstack_integration.selection.save_sync_selection", {
		instance: frm.doc.name,
		excluded: bookstack_collect_exclusions($tree),
	});
}

function bookstack_show_sync_result(stats) {
	const labels = bookstack_step_labels();
	const rows = Object.keys(labels)
		.filter((step) => step in stats)
		.map((step) => {
			const value = stats[step];
			const failed = typeof value === "string" && value.startsWith("error");
			return `<tr><td>${frappe.utils.escape_html(labels[step])}</td>
				<td class="${failed ? "text-danger" : "text-right"}">${frappe.utils.escape_html(String(value))}</td></tr>`;
		})
		.join("");
	// A sync that could not start (e.g. another one was running) has no steps, only "failed".
	const failed = stats.failed
		? `<p class="text-danger">${frappe.utils.escape_html(stats.failed)}</p>`
		: "";
	frappe.msgprint({
		title: stats.errors ? __("Sync finished with errors") : __("Sync complete"),
		indicator: stats.errors ? "orange" : "green",
		message: `${failed}<table class="table table-sm"><tbody>${rows}</tbody></table>`,
	});
}
