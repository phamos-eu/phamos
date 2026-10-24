// Copyright (c) 2026, phamos.eu and contributors
// For license information, please see license.txt

// Calendar status of a Leave Application (milestone 68, Phase 2): the leave is mirrored as an
// all-day Event in the employee's own calendar. HR usually cannot read that Private Event, so
// the state comes from the server.
frappe.ui.form.on("Leave Application", {
	refresh(frm) {
		if (frm.is_new()) return;
		frappe
			.call({
				method: "phamos.phamos.hr.leave_calendar.get_calendar_state",
				args: { leave_application: frm.doc.name },
			})
			.then(({ message: state }) => {
				if (!state || frm.doc.name !== frm.docname) return;
				show_calendar_state(frm, state);
			});
	},
});

function show_calendar_state(frm, state) {
	const user = frappe.utils.escape_html(state.user || "");
	if (state.reason === "no_user") {
		frm.dashboard.set_headline_alert(__("Calendar: no user linked to the employee"), "gray");
	} else if (state.reason === "error") {
		frm.dashboard.set_headline_alert(
			__("Calendar: not synced, {0}", [frappe.utils.escape_html(state.error)]),
			"orange"
		);
	} else if (state.reason === "pending") {
		frm.dashboard.set_headline_alert(__("Calendar: being added to {0}'s calendar", [user]), "blue");
	} else if (state.event) {
		frm.dashboard.set_headline_alert(__("Calendar: in {0}'s calendar", [user]), "green");
	}
	if (state.event && frappe.model.can_read("Event")) {
		frm.add_custom_button(__("Calendar Event"), () =>
			frappe.set_route("Form", "Event", state.event)
		);
	}
}
