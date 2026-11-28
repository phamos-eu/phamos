// Copyright (c) 2026, phamos.eu and contributors
// For license information, please see license.txt

// The Implementations the assistant is switched on for (#2114): User Permissions of its user on
// Implementation. Listed here, managed in the User Permission list.
frappe.ui.form.on("Issue Assistant Settings", {
	refresh(frm) {
		render_implementations(frm);
	},
});

function render_implementations(frm) {
	const user = frm.doc.assistant_user;
	const field = frm.get_field("implementations_html");
	if (!user) {
		field.$wrapper.html(`<p class="text-muted">${__("Run bench migrate to create the assistant's user.")}</p>`);
		return;
	}
	frappe.db
		.get_list("User Permission", {
			filters: { user, allow: "Implementation" },
			fields: ["name", "for_value"],
			order_by: "for_value asc",
			limit: 500,
		})
		.then((rows) => {
			const list = rows.length
				? `<ul>${rows
						.map(
							(r) =>
								`<li><a href="/app/implementation/${encodeURIComponent(r.for_value)}">${frappe.utils.escape_html(r.for_value)}</a></li>`
						)
						.join("")}</ul>`
				: `<p class="text-muted">${__("None yet: the assistant takes no new Issues.")}</p>`;
			field.$wrapper.html(
				`<p>${__("The assistant only takes new Issues of these Implementations. Issues of other Implementations, and Issues without one, are left alone.")}</p>${list}`
			);
			frm.remove_custom_button(__("Switch Implementations on or off"));
			frm.add_custom_button(__("Switch Implementations on or off"), () =>
				frappe.set_route("List", "User Permission", { user, allow: "Implementation" })
			);
		});
}
