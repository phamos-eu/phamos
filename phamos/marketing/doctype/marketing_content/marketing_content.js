// Marketing Content (event): attendee counts, attendee list and report, campaign, newsletter.

const NAMED_STAKEHOLDERS = { filters: { published: 1, publish_as: "Named", naming_approved: 1 } };

frappe.ui.form.on("Marketing Content", {
	setup(frm) {
		// Only stakeholders that may be named on the website (published, approved to be named).
		frm.set_query("organizer", () => NAMED_STAKEHOLDERS);
		frm.set_query("stakeholder", "sponsors", () => NAMED_STAKEHOLDERS);
		frm.set_query("ticket_item", () => ({ filters: { is_stock_item: 0, is_sales_item: 1, disabled: 0 } }));
	},

	refresh(frm) {
		set_location_hint(frm);
		if (frm.is_new()) return;
		if (!frm.doc.ticket_item) {
			frm.add_custom_button(__("Ticket Item"), () =>
				frappe.call({ method: "phamos.marketing.api.create_ticket_item", args: { event: frm.doc.name } })
					.then(() => frm.reload_doc()), __("Create"));
		}

		frappe.call({ method: "phamos.marketing.api.attendee_summary", args: { event: frm.doc.name } }).then((r) => {
			const c = r.message || {};
			frm.dashboard.add_indicator(__("Registered: {0}", [c.registered || 0]), "blue");
			frm.dashboard.add_indicator(__("Paid: {0}", [c.paid || 0]), "green");
			if (c.open_payment) frm.dashboard.add_indicator(__("Payment open: {0}", [c.open_payment]), "orange");
			if (c.attended || c.no_show) frm.dashboard.add_indicator(__("Attended: {0} · No show: {1}", [c.attended || 0, c.no_show || 0]), "gray");
		});

		frm.add_custom_button(__("Attendees"), () => frappe.set_route("List", "Attendee", { event: frm.doc.name }), __("View"));
		frm.add_custom_button(__("Event Attendees Report"), () =>
			frappe.set_route("query-report", "Event Attendees", { event: frm.doc.name }), __("View"));
		frm.add_custom_button(__("Add Attendee"), () =>
			frappe.new_doc("Attendee", { event: frm.doc.name, source: "Manual" }), __("Create"));
		if (!frm.doc.campaign) {
			frm.add_custom_button(__("Campaign"), () =>
				frappe.call({ method: "phamos.marketing.api.create_campaign", args: { event: frm.doc.name } })
					.then(() => frm.reload_doc()), __("Create"));
		}
		frm.add_custom_button(__("Newsletter"), () => {
			if (!frm.doc.email_group) {
				frappe.msgprint({ title: __("Email Group Required"), indicator: "orange",
					message: __("Please set an Email Group on this record before creating a Newsletter.") });
				return;
			}
			frappe.call({
				method: "phamos.marketing.doctype.marketing_content.marketing_content.create_newsletter_for_event",
				args: { event_name: frm.doc.name },
			}).then((r) => r.message && frappe.set_route("Form", "Newsletter", r.message));
		}, __("Create"));
	},

	organizer_is_phamos(frm) {
		if (frm.doc.organizer_is_phamos) frm.set_value("organizer", null);
	},

	attendance_mode(frm) {
		set_location_hint(frm);
	},

	// The address is looked up on OpenStreetMap (Nominatim) by the server; the pin can then be dragged.
	find_on_map(frm) {
		const { street, postal_code, city, country } = frm.doc;
		if (!street && !postal_code && !city) {
			frappe.msgprint(__("Please enter the address first."));
			return;
		}
		frappe.call({
			method: "phamos.marketing.location.find_on_map",
			args: { street, postal_code, city, country },
			freeze: true,
			freeze_message: __("Looking up the address…"),
		}).then((r) => {
			const found = r.message;
			if (!found) return;
			frm.set_value("geolocation", JSON.stringify({ type: "FeatureCollection", features: [{ type: "Feature",
				properties: {}, geometry: { type: "Point", coordinates: [found.longitude, found.latitude] } }] }));
			frappe.show_alert({ message: __("Pin set: {0}", [found.label || ""]), indicator: "green" });
		});
	},

	geolocation(frm) {
		// The pin was set or dragged: keep the plain numbers in step (the server does the same on save).
		let features = [];
		try {
			features = JSON.parse(frm.doc.geolocation || "{}").features || [];
		} catch (e) {
			// Not GeoJSON: no point to read; the server checks the value again on save.
		}
		const point = (features.find((f) => f.geometry && f.geometry.type === "Point") || {}).geometry;
		frm.set_value({ latitude: point ? point.coordinates[1] : null, longitude: point ? point.coordinates[0] : null });
	},
});

function set_location_hint(frm) {
	const online = frm.doc.attendance_mode === "Online";
	frm.set_df_property("location", "description", online
		? __("The meeting link (https://…). It is only sent to registered attendees, never shown on the website.")
		: __("The venue's name, e.g. \"Hotel Adlon, Saal 2\". The address goes below."));
	frm.set_df_property("location", "placeholder", online ? "https://" : "");
}
