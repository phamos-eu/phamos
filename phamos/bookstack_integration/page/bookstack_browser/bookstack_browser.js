// Copyright (c) 2026, phamos.eu and contributors
// For license information, please see license.txt

frappe.pages["bookstack-browser"].on_page_load = function (wrapper) {
	const page = frappe.ui.make_app_page({
		parent: wrapper,
		title: __("Bookstack Browser"),
		single_column: true,
	});

	new phamos.BookstackBrowser(page);
};

frappe.pages["bookstack-browser"].on_page_show = function () {
	// Refresh the instance list every time the page is shown, in case a new
	// configuration was created since the page was first mounted.
	if (window.phamos && window.phamos._bookstack_browser) {
		window.phamos._bookstack_browser.load_instances();
	}
};

window.phamos = window.phamos || {};

phamos.BookstackBrowser = class BookstackBrowser {
	constructor(page) {
		this.page = page;
		this.instance = null;
		this.tree = [];
		this.selected = null; // { doctype, name, type, bookstack_id, url, title }
		this.expanded = new Set(); // node ids that are open

		window.phamos._bookstack_browser = this;

		this.make_toolbar();
		this.make_layout();
		this.load_instances();
	}

	// ------------------------------------------------------------------ toolbar

	make_toolbar() {
		this.instance_field = this.page.add_field({
			fieldname: "instance",
			label: __("Instance"),
			fieldtype: "Select",
			options: [""],
			change: () => {
				const val = this.instance_field.get_value();
				if (val && val !== this.instance) {
					this.instance = val;
					this.load_tree();
				}
			},
		});

		this.page.set_primary_action(__("Refresh"), () => this.load_tree(), "refresh");

		this.page.add_menu_item(__("Sync Instance Now"), () => {
			if (!this.instance) {
				frappe.show_alert({ message: __("Select an instance first"), indicator: "orange" });
				return;
			}
			frappe.confirm(__("Trigger a full sync of {0}?", [this.instance]), () => {
				frappe.call({
					method: "phamos.bookstack_integration.sync.sync_instance",
					args: { instance: this.instance },
					freeze: true,
					freeze_message: __("Syncing Bookstack..."),
				}).then(() => {
					frappe.show_alert({ message: __("Sync complete"), indicator: "green" });
					this.load_tree();
				});
			});
		});

		this.page.add_menu_item(__("Open Instance in Bookstack"), () => {
			const cfg = (this._instances || []).find((i) => i.name === this.instance);
			if (cfg && cfg.instance_url) window.open(cfg.instance_url, "_blank");
		});
	}

	// ------------------------------------------------------------------ layout

	make_layout() {
		const html = `
			<div class="bookstack-browser row" style="min-height: 70vh;">
				<div class="col-md-4 border-right bookstack-tree-pane" style="padding-right: 12px;">
					<div class="bookstack-tree-toolbar" style="margin-bottom: 8px;">
						<input type="text" class="form-control input-sm bookstack-filter"
							placeholder="${__("Filter titles...")}" />
					</div>
					<div class="bookstack-tree small"></div>
				</div>
				<div class="col-md-8 bookstack-detail-pane" style="padding-left: 16px;">
					<div class="bookstack-detail-empty text-muted" style="padding: 40px; text-align: center;">
						${__("Select a shelf, book, chapter or page on the left.")}
					</div>
					<div class="bookstack-detail" style="display:none;"></div>
				</div>
			</div>
		`;
		$(html).appendTo(this.page.body);

		this.$tree = this.page.body.find(".bookstack-tree");
		this.$detail = this.page.body.find(".bookstack-detail");
		this.$empty = this.page.body.find(".bookstack-detail-empty");
		this.$filter = this.page.body.find(".bookstack-filter");

		this.$filter.on("input", () => this.render_tree());

		this.$tree.on("click", ".bookstack-node-toggle", (ev) => {
			ev.stopPropagation();
			const id = $(ev.currentTarget).closest("[data-node-id]").attr("data-node-id");
			if (this.expanded.has(id)) this.expanded.delete(id);
			else this.expanded.add(id);
			this.render_tree();
		});

		this.$tree.on("click", ".bookstack-node-label", (ev) => {
			const $li = $(ev.currentTarget).closest("[data-node-id]");
			const node = this._find_node($li.attr("data-node-id"));
			if (!node) return;

			// Toggle children when a group/container is clicked too
			if (node.children && node.children.length) {
				const id = $li.attr("data-node-id");
				if (this.expanded.has(id)) this.expanded.delete(id);
				else this.expanded.add(id);
			}
			this.selected = node;
			this.render_tree();
			this.render_detail(node);
		});
	}

	// ---------------------------------------------------------------- data ops

	load_instances() {
		frappe.call({
			method: "phamos.bookstack_integration.api.list_instances",
		}).then((r) => {
			const instances = r.message || [];
			this._instances = instances;
			const options = [""].concat(instances.map((i) => ({ label: i.title || i.name, value: i.name })));
			this.instance_field.df.options = options;
			this.instance_field.set_options && this.instance_field.set_options(options);
			this.instance_field.refresh();

			if (!instances.length) {
				this.$tree.html(`<div class="text-muted" style="padding:12px;">
					${__("No enabled Bookstack Configurations found. Create one first.")}
				</div>`);
				return;
			}

			// Auto-select the first instance if nothing chosen yet
			if (!this.instance) {
				this.instance = instances[0].name;
				this.instance_field.set_value(this.instance);
				this.load_tree();
			}
		});
	}

	load_tree() {
		if (!this.instance) return;
		this.$tree.html(`<div class="text-muted" style="padding:12px;">${__("Loading...")}</div>`);
		frappe.call({
			method: "phamos.bookstack_integration.api.get_tree",
			args: { instance: this.instance },
		}).then((r) => {
			this.tree = r.message || [];
			// Auto-expand top level by default
			this.expanded = new Set(this.tree.map((n, i) => this._node_id(n, `root-${i}`)));
			this.render_tree();
			if (!this.tree.length) {
				this.$empty.text(__("This instance has no synced content yet. Use \"Sync Instance Now\" from the menu."));
			}
		});
	}

	// ----------------------------------------------------------------- render

	render_tree() {
		const filter = (this.$filter.val() || "").trim().toLowerCase();
		const html = `<ul class="bookstack-tree-list" style="list-style:none; padding-left:0; margin:0;">
			${this.tree.map((n, i) => this._render_node(n, `root-${i}`, 0, filter)).join("")}
		</ul>`;
		this.$tree.html(html);
	}

	_render_node(node, path, depth, filter) {
		const id = this._node_id(node, path);
		const has_children = node.children && node.children.length;
		const is_open = this.expanded.has(id);

		const child_html = has_children
			? node.children.map((c, i) => this._render_node(c, `${path}.${i}`, depth + 1, filter)).join("")
			: "";

		const matches = !filter || (node.title || "").toLowerCase().includes(filter);
		const child_visible = has_children && child_html.includes("data-node-id");
		if (filter && !matches && !child_visible) return "";

		const selected = this.selected && this.selected._id === id ? "bookstack-selected" : "";
		const icon = this._icon(node.type);
		const toggle = has_children
			? `<span class="bookstack-node-toggle" style="cursor:pointer; display:inline-block; width:14px; text-align:center;">${is_open ? "▾" : "▸"}</span>`
			: `<span style="display:inline-block; width:14px;"></span>`;

		node._id = id; // for click handler comparison

		return `
			<li data-node-id="${frappe.utils.escape_html(id)}" style="padding: 2px 0;">
				<div class="bookstack-node ${selected}" style="display:flex; align-items:center; padding: 3px 4px; border-radius: 4px; cursor: pointer;">
					${toggle}
					<span class="bookstack-node-label" style="flex:1; padding-left:4px; user-select:none;">
						<span class="bookstack-icon" style="margin-right:6px;">${icon}</span>
						${frappe.utils.escape_html(node.title || "(untitled)")}
					</span>
				</div>
				${has_children && (is_open || (filter && child_visible))
					? `<ul style="list-style:none; padding-left:18px; margin:0;">${child_html}</ul>`
					: ""}
			</li>
		`;
	}

	render_detail(node) {
		this.$empty.hide();
		this.$detail.show();

		if (node.type === "group" || !node.doctype) {
			this.$detail.html(`<h4>${frappe.utils.escape_html(node.title)}</h4>
				<p class="text-muted">${__("{0} child item(s).", [(node.children || []).length])}</p>`);
			return;
		}

		this.$detail.html(`<div class="text-muted">${__("Loading...")}</div>`);
		frappe.call({
			method: "phamos.bookstack_integration.api.get_node_detail",
			args: { doctype: node.doctype, name: node.name },
		}).then((r) => {
			const doc = r.message || {};
			this._render_detail_body(node, doc);
		});
	}

	_render_detail_body(node, doc) {
		const kind_label = { shelf: __("Shelf"), book: __("Book"), chapter: __("Chapter"), page: __("Page") }[node.type] || "";
		const fmt = (v) => (v || v === 0 ? frappe.utils.escape_html(String(v)) : "<em class='text-muted'>—</em>");
		const link = (v) => (v ? `<a href="${frappe.utils.escape_html(v)}" target="_blank" rel="noopener">${frappe.utils.escape_html(v)}</a>` : "<em class='text-muted'>—</em>");

		const rows = [
			[__("Type"), kind_label],
			[__("Title"), fmt(doc.title)],
			[__("Bookstack ID"), fmt(doc.bookstack_id)],
			[__("Slug"), fmt(doc.slug)],
		];
		if (node.type === "book") rows.push([__("Shelf"), fmt(doc.shelf)]);
		if (node.type === "chapter") rows.push([__("Book"), fmt(doc.book)]);
		if (node.type === "page") {
			rows.push([__("Book"), fmt(doc.book)]);
			rows.push([__("Chapter"), fmt(doc.chapter)]);
			rows.push([__("Draft"), doc.draft ? __("Yes") : __("No")]);
			rows.push([__("Revisions"), fmt(doc.revision_count)]);
		}
		rows.push([__("URL"), link(doc.url)]);
		rows.push([__("Created At"), fmt(doc.created_at)]);
		rows.push([__("Updated At"), fmt(doc.updated_at)]);
		rows.push([__("Last Synced"), fmt(doc.last_synced)]);

		const rows_html = rows
			.map(([k, v]) => `<tr><th style="width: 160px; font-weight: 500; color: var(--text-muted);">${k}</th><td>${v}</td></tr>`)
			.join("");

		const desc = doc.description
			? `<h5 style="margin-top:16px;">${__("Description")}</h5>
				<div class="bookstack-desc" style="white-space: pre-wrap;">${frappe.utils.escape_html(doc.description)}</div>`
			: "";

		this.$detail.html(`
			<div class="bookstack-detail-header" style="display:flex; align-items:center; gap:8px; margin-bottom:12px;">
				<h3 style="margin:0; flex:1;">${frappe.utils.escape_html(doc.title || "")}</h3>
				<button class="btn btn-xs btn-default bookstack-open-doc">${__("Open Record")}</button>
				${doc.url ? `<button class="btn btn-xs btn-default bookstack-open-external">${__("Open in Bookstack")}</button>` : ""}
				${node.type === "page" ? `<button class="btn btn-xs btn-primary bookstack-load-preview">${__("Load Preview")}</button>` : ""}
			</div>
			<table class="table table-sm bookstack-detail-table"><tbody>${rows_html}</tbody></table>
			${desc}
			<div class="bookstack-preview-container" style="margin-top: 16px;"></div>
		`);

		this.$detail.find(".bookstack-open-doc").on("click", () => {
			frappe.set_route("Form", node.doctype, node.name);
		});
		this.$detail.find(".bookstack-open-external").on("click", () => {
			if (doc.url) window.open(doc.url, "_blank");
		});
		this.$detail.find(".bookstack-load-preview").on("click", (ev) => {
			this._load_preview(node, doc, $(ev.currentTarget));
		});
	}

	_load_preview(node, doc, $btn) {
		const $container = this.$detail.find(".bookstack-preview-container");
		$btn.prop("disabled", true).text(__("Loading..."));
		$container.html(`<div class="text-muted">${__("Fetching from Bookstack...")}</div>`);
		frappe.call({
			method: "phamos.bookstack_integration.api.get_page_html",
			args: { instance: this.instance, bookstack_id: doc.bookstack_id },
		}).then((r) => {
			const data = r.message || {};
			// Render inside a scoped iframe to avoid CSS bleed and script exec on desk
			const iframe_id = `bookstack-preview-${frappe.utils.get_random(6)}`;
			$container.html(`
				<h5 style="margin-top:0;">${__("Page Preview")}</h5>
				<iframe id="${iframe_id}" sandbox="allow-same-origin"
					style="width:100%; min-height:60vh; border:1px solid var(--border-color); border-radius:6px; background:white;"></iframe>
			`);
			const iframe = document.getElementById(iframe_id);
			const html = `<!doctype html><html><head><meta charset="utf-8">
				<style>
					body { font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif; padding: 16px; color: #222; }
					img { max-width: 100%; height: auto; }
					pre, code { background:#f5f5f5; padding: 2px 6px; border-radius: 4px; }
					pre { padding: 12px; overflow:auto; }
					table { border-collapse: collapse; }
					table td, table th { border: 1px solid #ddd; padding: 6px 10px; }
				</style></head><body>${data.html || `<em>${__("This page has no rendered HTML.")}</em>`}</body></html>`;
			iframe.srcdoc = html;
			$btn.prop("disabled", false).text(__("Reload Preview"));
		}).fail(() => {
			$btn.prop("disabled", false).text(__("Load Preview"));
			$container.html(`<div class="text-danger">${__("Could not load preview.")}</div>`);
		});
	}

	// -------------------------------------------------------------- utilities

	_icon(type) {
		return {
			shelf: "📚",
			book: "📖",
			chapter: "📑",
			page: "📄",
			group: "📁",
		}[type] || "•";
	}

	_node_id(node, path) {
		return `${node.type}:${node.name || path}`;
	}

	_find_node(id) {
		const walk = (list) => {
			for (const n of list || []) {
				if (n._id === id) return n;
				const hit = walk(n.children);
				if (hit) return hit;
			}
			return null;
		};
		return walk(this.tree);
	}
};
