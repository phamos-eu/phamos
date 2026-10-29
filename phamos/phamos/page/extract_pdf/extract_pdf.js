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
				<div data-supplier></div>
				<div data-pdf-file></div>
			</div>
			<div class="pdf-extract__panel pdf-extract__panel--right">
				<h3 class="pdf-extract__title">${__("Extracted fields")}</h3>
				<div data-mapping-lines></div>
				<button type="button" class="btn btn-primary btn-sm pdf-extract__create" data-create hidden></button>
			</div>
		</div>
	`);

	page.mapping_rows = [];
	page.generic_rows = [];
	page.target_doctype = "";

	const update_create_button = () => {
		const $button = $(page.main).find("[data-create]");
		if (!page.target_doctype) {
			$button.attr("hidden", true);
			return;
		}
		$button.text(__("Create {0}", [page.target_doctype])).removeAttr("hidden");
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

	$(page.main).on("click", "[data-create]", () => {
		if (!page.target_doctype) return;
		const doctype = page.target_doctype;
		frappe.model.with_doctype(doctype, async () => {
			const doc = frappe.model.get_new_doc(doctype);
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

	const render_lines = () => {
		const $lines = $(page.main).find("[data-mapping-lines]");
		if (!page.mapping_rows.length) {
			$lines.empty();
			return;
		}
		const body = page.mapping_rows
			.map(
				(row) => `
				<div class="pdf-extract__line">
					<div>${frappe.utils.escape_html(row.extracted_value || "")}</div>
					<div>${frappe.utils.escape_html(row.source_label || "")}</div>
					<div>${frappe.utils.escape_html(row.target_field || "")}</div>
				</div>`
			)
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

	const apply_supplier_rules = () => {
		if (!page.generic_rows.length) return;
		const rows = page.generic_rows.map((row) => ({
			source_label: row.source_label,
			target_field: row.target_field,
			extracted_value: "",
		}));
		const supplier = page.supplier && page.supplier.get_value();
		if (!supplier) {
			page.mapping_rows = rows;
			fill_extracted_values();
			return;
		}
		frappe.db.get_doc("Supplier", supplier).then((doc) => {
			(doc.custom_pdf_rule || []).forEach((rule) => {
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
			page.mapping_rows = rows;
			fill_extracted_values();
		});
	};

	page.pdf_file = frappe.ui.form.make_control({
		parent: $(page.main).find("[data-pdf-file]"),
		df: {
			fieldname: "pdf_file",
			label: "PDF",
			fieldtype: "Attach",
			change() {
				fill_extracted_values();
			},
		},
		render_input: true,
	});

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
					update_create_button();
					render_lines();
					return;
				}
				frappe.db.get_doc("PDF Mapping", name).then((doc) => {
					page.target_doctype = doc.target_doctype || "";
					update_create_button();
					page.generic_rows = (doc.pdf_mapping_line || []).map((row) => ({
						source_label: row.source_label,
						target_field: row.target_field,
					}));
					apply_supplier_rules();
				});
			},
		},
		render_input: true,
	});

	page.supplier = frappe.ui.form.make_control({
		parent: $(page.main).find("[data-supplier]"),
		df: {
			fieldname: "supplier",
			label: "Supplier",
			fieldtype: "Link",
			options: "Supplier",
			change() {
				apply_supplier_rules();
			},
		},
		render_input: true,
	});
};
