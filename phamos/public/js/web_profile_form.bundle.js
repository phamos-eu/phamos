// Desk helpers for every "<Source> Web Profile" form (phamos/phamos#1492):
// a visible hint when a website language has no text row, and a link to the public page.
(function () {
	const SECTIONS = {
		"Person Web Profile": { en: "people", de: "personen" },
		"Department Web Profile": { en: "departments", de: "abteilungen" },
		"Team Web Profile": { en: "teams", de: "teams" },
		"Module Web Profile": { en: "modules", de: "module" },
		"Implementation Web Profile": { en: "implementations", de: "implementierungen" },
		"Industry Web Profile": { en: "industries", de: "branchen" },
		"Stakeholder Web Profile": { en: "customers", de: "kunden", Partner: { en: "partners", de: "partner" } },
	};
	// Website languages, German first (keep in sync with phamos/web_profile/i18n.py LANGUAGES).
	const LANGUAGES = { de: "Deutsch", en: "English" };

	// Site languages without a row in the "Texts per Language" table (Web Profile Content).
	function missingTranslations(frm) {
		const present = new Set((frm.doc.translations || []).map((row) => row.language));
		return Object.entries(LANGUAGES)
			.filter(([code]) => !present.has(code))
			.map(([, label]) => label);
	}

	// Person Web Profile: pick a party (Employee, Customer, Supplier, Sales Partner), then the
	// Contact that is the actual person at that party.
	frappe.ui.form.on("Person Web Profile", {
		setup(frm) {
			frm.set_query("party_type", () => ({
				filters: { name: ["in", ["Employee", "Customer", "Supplier", "Sales Partner"]] },
			}));
			frm.set_query("contact", () => ({
				query: "frappe.contacts.doctype.contact.contact.contact_query",
				filters: { link_doctype: frm.doc.party_type, link_name: frm.doc.party },
			}));
		},
		party_type(frm) {
			frm.set_value("party", "");
			frm.set_value("contact", "");
		},
		party(frm) {
			frm.set_value("contact", "");
		},
		publication_consent(frm) {
			if (frm.doc.publication_consent && !frm.doc.publication_consent_date) frm.set_value("publication_consent_date", frappe.datetime.get_today());
		},
		alumni_consent(frm) {
			if (frm.doc.alumni_consent && !frm.doc.alumni_consent_date) frm.set_value("alumni_consent_date", frappe.datetime.get_today());
		},
		contact_consent(frm) {
			if (frm.doc.contact_consent && !frm.doc.contact_consent_date) frm.set_value("contact_consent_date", frappe.datetime.get_today());
		},
	});

	// Stakeholder Web Profile: Customer, Supplier or Sales Partner as party.
	frappe.ui.form.on("Stakeholder Web Profile", {
		setup(frm) {
			frm.set_query("party_type", () => ({ filters: { name: ["in", ["Customer", "Supplier", "Sales Partner"]] } }));
			frm.set_query("key_person", () => ({ filters: { party_type: frm.doc.party_type, party: frm.doc.party } }));
		},
		party_type(frm) {
			frm.set_value("party", "");
		},
		naming_approved(frm) {
			if (frm.doc.naming_approved && !frm.doc.naming_approval_date) frm.set_value("naming_approval_date", frappe.datetime.get_today());
		},
	});

	for (const [doctype, slugs] of Object.entries(SECTIONS)) {
		frappe.ui.form.on(doctype, {
			refresh(frm) {
				const missing = missingTranslations(frm);
				frm.set_intro(
					missing.length
						? __("Missing translation: {0}. The German text (or another language) is shown instead.", [missing.join(", ")])
						: "",
					"orange"
				);
				if (!frm.is_new() && frm.doc.published && frm.doc.route) {
					for (const lang of ["en", "de"]) {
						frm.add_custom_button(lang.toUpperCase(), () => {
							const section = slugs[frm.doc.stakeholder_type] || slugs;
							window.open(`/${lang}/${section[lang]}/${frm.doc.route}`, "_blank");
						}, __("View on Website"));
					}
				}
			},
		});
	}
})();
