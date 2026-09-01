frappe.ui.form.on("Appointment", {
	refresh(frm) {
		frm.set_df_property(
			"party",
			"label",
			frm.doc.appointment_with
				? `Party (${frm.doc.appointment_with})`
				: "Party"
		);

		this.set_party_details(frm);
	},

	appointment_with(frm) {
		frm.set_df_property(
			"party",
			"label",
			frm.doc.appointment_with
				? `Party (${frm.doc.appointment_with})`
				: "Party"
		);

		// Party type changed, so the existing party is no longer reliable.
		frm.set_value("party", null);
		frm.set_value("customer_name", null);
		frm.set_value("customer_email", null);
		frm.set_value("customer_phone_number", null);
		frm.set_value("customer_skype", null);
	},

	party(frm) {
		this.set_party_details(frm);
	},

	set_party_details(frm) {
		const party_type = frm.doc.appointment_with;
		const party_name = frm.doc.party;

		if (!party_type || !party_name) {
			return;
		}

		frappe.db.get_doc(party_type, party_name).then((doc) => {
			if (!doc) {
				return;
			}

			if (frm.fields_dict.customer_name) {
				frm.set_value(
					"customer_name",
					doc.customer_name ||
					doc.full_name ||
					doc.employee_name ||
					doc.name
				);
			}

			if (frm.fields_dict.customer_email) {
				frm.set_value(
					"customer_email",
					doc.email ||
					doc.email_id ||
					doc.contact_email
				);
			}

			if (frm.fields_dict.customer_phone_number) {
				frm.set_value(
					"customer_phone_number",
					doc.phone ||
					doc.contact_phone ||
					doc.mobile_no ||
					doc.phone_number
				);
			}

			if (frm.fields_dict.customer_skype) {
				frm.set_value(
					"customer_skype",
					doc.skype_id || doc.skype
				);
			}
		});
	}
});
