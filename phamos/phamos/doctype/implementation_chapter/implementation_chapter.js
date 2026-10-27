// Copyright (c) 2026, phamos.eu and contributors
// For license information, please see license.txt

frappe.ui.form.on("Implementation Chapter", {
	refresh(frm) {
		frm.trigger("toggle_agreed_content_readonly");
		frm.trigger("render_history_section");

		if (!frm.is_new() && frm.doc.status === "Draft") {
			frm.add_custom_button(__("Set as Planned"), () => {
				frappe.confirm(
					__(
						"This locks the agreed content (title, description, dates) as an immutable Revision 1 and moves this Chapter to Planned. This cannot be undone. Continue?"
					),
					() => {
						frappe.call({
							method:
								"phamos.phamos.doctype.implementation_chapter.implementation_chapter.set_as_planned",
							args: { name: frm.doc.name },
							freeze: true,
							freeze_message: __("Setting as Planned..."),
							callback: () => {
								frm.reload_doc();
							},
						});
					}
				);
			}).addClass("btn-primary");
		}
	},
	toggle_agreed_content_readonly(frm) {
		const locked = frm.doc.status && frm.doc.status !== "Draft";
		["chapter_title", "chapter_introduction", "full_chapter_description", "planned_start", "target_date"].forEach(
			(fieldname) => {
				frm.set_df_property(fieldname, "read_only", locked ? 1 : 0);
			}
		);
		frm.refresh_fields();
	},

	render_history_section(frm) {
		const wrapper = frm.fields_dict.chapter_history_html?.wrapper;
		if (!wrapper) return;

		if (frm.is_new()) {
			$(wrapper).html(`<div class="text-muted">${__("Save the Chapter to see its history.")}</div>`);
			return;
		}

		$(wrapper).html(`<div class="text-muted">${__("Loading history...")}</div>`);

		frappe.call({
			method: "phamos.phamos.doctype.implementation_chapter.implementation_chapter.get_chapter_history",
			args: { chapter: frm.doc.name },
			callback: (r) => {
				const data = r.message || {};
				$(wrapper).html(build_chapter_history_html(data));
			},
		});
	},
});

const PROGRESS_COLORS = {
	"On Track": "#2f9e44",
	"At Risk": "#f2b705",
	"Off Track": "#e03131",
};

function chapter_history_pill(text, colors) {
	if (!text) return "";
	const color = colors[text] || "#868e96";
	return `<span class="chapter-history-pill" style="background:${color}">${frappe.utils.escape_html(text)}</span>`;
}

function build_revision_decision_html(rev) {
	if (!rev.decision) return "-";
	const heading = `<strong>${frappe.utils.escape_html(rev.decision)}</strong>`;
	const description = rev.decision_description
		? `<div class="text-muted">${frappe.utils.escape_html(rev.decision_description)}</div>`
		: "";
	return `${heading}${description}`;
}

function build_revisions_html(revisions) {
	if (!revisions || !revisions.length) {
		return `<div class="text-muted">${__("No revisions yet.")}</div>`;
	}

	const rows = revisions
		.map((rev) => {
			const current_badge = rev.is_current
				? `<span class="chapter-history-pill" style="background:#1c7ed6">${__("Current")}</span>`
				: "";
			return `
				<tr>
					<td>
						<a href="/app/implementation-chapter-revision/${encodeURIComponent(rev.name)}">
							${__("Rev {0}", [rev.revision_number])}
						</a>
						${current_badge}
					</td>
					<td>${frappe.utils.escape_html(rev.chapter_title || "")}</td>
					<td>${rev.planned_start ? frappe.datetime.str_to_user(rev.planned_start) : "-"}</td>
					<td>${rev.target_date ? frappe.datetime.str_to_user(rev.target_date) : "-"}</td>
					<td>${chapter_history_pill(rev.progress, PROGRESS_COLORS) || "-"}</td>
					<td>${build_revision_decision_html(rev)}</td>
					<td>${frappe.datetime.str_to_user(rev.creation)}</td>
				</tr>
			`;
		})
		.join("");

	return `
		<div style="overflow-x: auto;">
			<table class="chapter-history-table">
				<thead>
					<tr>
						<th>${__("Revision")}</th>
						<th>${__("Title")}</th>
						<th>${__("Planned Start")}</th>
						<th>${__("Target Date")}</th>
						<th>${__("Progress")}</th>
						<th>${__("Decisions")}</th>
						<th>${__("Created On")}</th>
					</tr>
				</thead>
				<tbody>${rows}</tbody>
			</table>
		</div>
	`;
}

function build_chapter_history_html(data) {
	const current = (data.revisions || []).find((rev) => rev.is_current);
	const current_html = current
		? `
			<div class="chapter-history-current">
				<strong>${__("Current Revision: Rev {0}", [current.revision_number])}</strong> – ${frappe.utils.escape_html(
					current.chapter_title || ""
				)}
			</div>
		`
		: `<div class="text-muted">${__("This Chapter has not been planned yet, so it has no revisions.")}</div>`;

	return `
		<style>
			.chapter-history-current { margin-bottom: 15px; padding: 10px; background: var(--bg-light-gray, #f5f5f5); border-radius: 4px; }
			.chapter-history-pill { display: inline-block; padding: 1px 8px; border-radius: 10px; color: #fff; font-size: 11px; margin-left: 4px; }
			.chapter-history-table { width: 100%; border-collapse: collapse; }
			.chapter-history-table th, .chapter-history-table td { padding: 6px 10px; border-bottom: 1px solid var(--border-color, #d1d8dd); text-align: left; vertical-align: top; }
			.chapter-history-decisions { margin: 0; padding-left: 16px; }
		</style>
		${current_html}
		<h6 style="margin-top:15px;">${__("Revisions")}</h6>
		${build_revisions_html(data.revisions)}
	`;
}
