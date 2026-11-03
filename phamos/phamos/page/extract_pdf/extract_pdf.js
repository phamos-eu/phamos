frappe.pages["extract-pdf"].on_page_load = function (wrapper) {
	const page = frappe.ui.make_app_page({
		parent: wrapper,
		title: "Extract PDF",
		single_column: true,
	});

	$(page.main).html(`
		<div class="pdf-extract">
			<div class="pdf-extract__panel pdf-extract__panel--left">
				<h3 class="pdf-extract__title">${__("PDF")}</h3>
				<div data-pdf-mapping></div>
				<div data-party></div>
				<div data-pdf-file></div>
			</div>
			<div class="pdf-extract__panel pdf-extract__panel--right">
				<h3 class="pdf-extract__title">${__("Extracted fields")}</h3>
				<div data-mapping-lines></div>
				<div class="pdf-extract__actions">
					<button type="button" class="btn btn-default btn-sm" data-save-rules hidden></button>
					<button type="button" class="btn btn-primary btn-sm" data-create hidden></button>
				</div>
			</div>
		</div>
	`);

	page.mapping_rows = [];
	page.generic_rows = [];
	page.target_doctype = "";
	page.party_doctype = "";
	page.rules_loaded = false;

	const party_link_field = (doctype) => {
		if (!page.party_doctype) return "";
		const preferred = { Lead: "lead", Customer: "customer", Supplier: "supplier" }[page.party_doctype];
		if (preferred) {
			const preferred_df = frappe.meta.get_docfield(doctype, preferred);
			if (
				preferred_df &&
				preferred_df.fieldtype === "Link" &&
				preferred_df.options === page.party_doctype
			) {
				return preferred;
			}
		}
		const match = (frappe.meta.get_docfields(doctype) || []).find((df) => {
			return df.fieldtype === "Link" && df.options === page.party_doctype;
		});
		return match ? match.fieldname : "";
	};

	const update_buttons = () => {
		const $create = $(page.main).find("[data-create]");
		const $save = $(page.main).find("[data-save-rules]");
		if (!page.target_doctype) {
			$create.attr("hidden", true);
		} else {
			$create.text(__("Create {0}", [page.target_doctype])).removeAttr("hidden");
		}
		const party = page.party && page.party.get_value();
		if (!page.party_doctype || !party || !page.rules_loaded) {
			$save.attr("hidden", true);
			return;
		}
		$save.text(__("Save rules for {0}", [page.party_doctype])).removeAttr("hidden");
	};

	const resolve_field = (doctype, target) => {
		const needle = (target || "").trim();
		if (!needle) return "";
		if (frappe.meta.has_field(doctype, needle)) return needle;
		const match = frappe.meta.get_docfields(doctype).find((df) => {
			return (df.label || "").trim().toLowerCase() === needle.toLowerCase();
		});
		return match ? match.fieldname : "";
	};

	const to_system_date = (value) => {
		const text = String(value || "").trim();
		const dmy = text.match(/^(\d{1,2})[./](\d{1,2})[./](\d{4})$/);
		if (!dmy) return text;
		return `${dmy[3]}-${dmy[2].padStart(2, "0")}-${dmy[1].padStart(2, "0")}`;
	};

	const learned_rules = () => {
		return page.mapping_rows
			.filter((row) => {
				const target = (row.target_field || "").trim();
				const source = (row.source_label || "").trim();
				if (!target || !source) return false;
				const generic = page.generic_rows.find((item) => item.target_field === target);
				if (!generic) return true;
				return source !== (generic.source_label || "").trim();
			})
			.map((row) => ({
				source_label: row.source_label.trim(),
				target_field: row.target_field.trim(),
			}));
	};

	$(page.main).on("click", "[data-create]", () => {
		if (!page.target_doctype) return;
		const doctype = page.target_doctype;
		const party_name = page.party.get_value();
		frappe.model.with_doctype(doctype, async () => {
			const doc = frappe.model.get_new_doc(doctype);
			const link_field = party_link_field(doctype);
			if (party_name && link_field) {
				try {
					await frappe.model.set_value(doc.doctype, doc.name, link_field, party_name);
				} catch (e) {
					doc[link_field] = party_name;
				}
			}
			for (const row of page.mapping_rows) {
				const fieldname = resolve_field(doctype, row.target_field);
				if (!fieldname || !row.extracted_value) continue;
				const df = frappe.meta.get_docfield(doctype, fieldname);
				let value = row.extracted_value;
				if (df && df.fieldtype === "Date") {
					value = to_system_date(value);
				}
				try {
					await frappe.model.set_value(doc.doctype, doc.name, fieldname, value);
				} catch (e) {
					doc[fieldname] = value;
				}
			}
			frappe.set_route("Form", doc.doctype, doc.name);
		});
	});

	$(page.main).on("click", "[data-save-rules]", () => {
		const party = page.party.get_value();
		const pdf_mapping = page.pdf_mapping.get_value();
		if (!page.party_doctype || !party || !pdf_mapping || !page.rules_loaded) return;
		frappe.call({
			method: "phamos.phamos.page.extract_pdf.extract_pdf.save_party_rules",
			args: {
				party_doctype: page.party_doctype,
				party,
				pdf_mapping,
				rules: learned_rules(),
			},
			callback() {
				frappe.show_alert({
					message: __("Rules saved for {0}", [party]),
					indicator: "green",
				});
			},
		});
	});

	const render_lines = () => {
		const $lines = $(page.main).find("[data-mapping-lines]");
		if (!page.mapping_rows.length) {
			$lines.empty();
			return;
		}
		const body = page.mapping_rows
			.map((row, index) => {
				return `
				<div class="pdf-extract__line">
					<div>${frappe.utils.escape_html(row.extracted_value || "")}</div>
					<div>
						<input class="form-control input-sm" data-source-label data-idx="${index}"
							value="${frappe.utils.escape_html(row.source_label || "")}">
					</div>
					<div>${frappe.utils.escape_html(row.target_field || "")}</div>
				</div>`;
			})
			.join("");
		$lines.html(`
			<div class="pdf-extract__line pdf-extract__line--head">
				<div>${__("Extracted value")}</div>
				<div>${__("Source label")}</div>
				<div>${__("Target field")}</div>
			</div>
			${body}
		`);
	};

	const fill_extracted_values = () => {
		const file_url = page.pdf_file.get_value();
		if (!file_url || !page.mapping_rows.length) {
			page.mapping_rows.forEach((row) => {
				row.extracted_value = "";
			});
			render_lines();
			return;
		}
		frappe.call({
			method: "phamos.phamos.page.extract_pdf.extract_pdf.extract_values",
			args: {
				file_url,
				source_labels: page.mapping_rows.map((row) => row.source_label),
			},
			callback(response) {
				const values = response.message || {};
				page.mapping_rows.forEach((row) => {
					row.extracted_value = values[row.source_label] || "";
				});
				render_lines();
			},
		});
	};

	const apply_party_rules = () => {
		const rows = page.generic_rows.map((row) => ({
			source_label: row.source_label,
			target_field: row.target_field,
			extracted_value: "",
		}));
		const party = page.party && page.party.get_value();
		const pdf_mapping = page.pdf_mapping && page.pdf_mapping.get_value();
		if (!page.party_doctype || !party || !pdf_mapping) {
			page.rules_loaded = false;
			page.mapping_rows = rows;
			update_buttons();
			fill_extracted_values();
			return;
		}
		page.rules_loaded = false;
		update_buttons();
		frappe.call({
			method: "phamos.phamos.page.extract_pdf.extract_pdf.party_rules",
			args: {
				party_doctype: page.party_doctype,
				party,
				pdf_mapping,
			},
			callback(response) {
				(response.message || []).forEach((rule) => {
					if (!rule.target_field || !rule.source_label) return;
					const row = rows.find((item) => item.target_field === rule.target_field);
					if (row) {
						row.source_label = rule.source_label;
					} else {
						rows.push({
							source_label: rule.source_label,
							target_field: rule.target_field,
							extracted_value: "",
						});
					}
				});
				page.rules_loaded = true;
				page.mapping_rows = rows;
				update_buttons();
				fill_extracted_values();
			},
		});
	};

	$(page.main).on("change", "[data-source-label]", function () {
		const index = Number($(this).attr("data-idx"));
		const row = page.mapping_rows[index];
		if (!row) return;
		const typed = ($(this).val() || "").trim();
		const generic = page.generic_rows.find((item) => item.target_field === row.target_field);
		row.source_label = typed || (generic ? generic.source_label : "");
		fill_extracted_values();
	});

	page.pdf_file = frappe.ui.form.make_control({
		parent: $(page.main).find("[data-pdf-file]"),
		df: {
			fieldname: "pdf_file",
			label: "PDF or image",
			fieldtype: "Attach",
			change() {
				fill_extracted_values();
			},
		},
		render_input: true,
	});

	const set_party_doctype = (party_doctype) => {
		const next = party_doctype || "";
		const changed = page.party_doctype !== next;
		page.party_doctype = next;
		page.party.df.options = next || "Lead";
		page.party.df.label = next || __("Primary Key");
		if (next) {
			page.party.$wrapper.show();
		} else {
			page.party.$wrapper.hide();
		}
		page.party.refresh();
		if (changed) {
			page.party.value = "";
			page.party.set_value("");
		}
	};

	page.pdf_mapping = frappe.ui.form.make_control({
		parent: $(page.main).find("[data-pdf-mapping]"),
		df: {
			fieldname: "pdf_mapping",
			label: "PDF Mapping",
			fieldtype: "Link",
			options: "PDF Mapping",
			change() {
				const name = page.pdf_mapping.get_value();
				if (!name) {
					page.generic_rows = [];
					page.mapping_rows = [];
					page.target_doctype = "";
					page.rules_loaded = false;
					set_party_doctype("");
					update_buttons();
					render_lines();
					return;
				}
				frappe.db.get_doc("PDF Mapping", name).then((doc) => {
					page.target_doctype = doc.target_doctype || "";
					page.generic_rows = (doc.pdf_mapping_line || []).map((row) => ({
						source_label: row.source_label,
						target_field: row.target_field,
					}));
					set_party_doctype(doc.party_doctype || "");
					update_buttons();
					apply_party_rules();
				});
			},
		},
		render_input: true,
	});

	page.party = frappe.ui.form.make_control({
		parent: $(page.main).find("[data-party]"),
		df: {
			fieldname: "party",
			label: "Primary Key",
			fieldtype: "Link",
			options: "Lead",
			change() {
				apply_party_rules();
			},
		},
		render_input: true,
	});
	page.party.$wrapper.hide();
};
