// Desk helpers for every "<Source> Web Profile" form (phamos/phamos#1492):
// a visible hint when a website language has no text row, and a link to the public page.
// Also the content Web Pages (#1539): translation hints and "Create Translation".
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

	// Content Web Pages (phamos/phamos#1539): one page per language, the English one points to the
	// German one with "Translation Of" (#1502). The form says which translation is missing or older
	// than its German page, and creates a missing translation as a copy of the German page.
	async function webPageHints(frm) {
		const hints = [];
		if (frm.doc.content_type === "HTML") {
			hints.push(__("This page is raw HTML. Page Builder blocks (or Rich Text) are easier to edit and keep the site's design."));
		}
		if (frm.doc.language === "de") {
			const translations = await frappe.db.get_list("Web Page", {
				filters: { translation_of: frm.doc.name },
				fields: ["name", "language", "modified"],
			});
			for (const [code, label] of Object.entries(LANGUAGES)) {
				if (code === "de") continue;
				const page = translations.find((row) => row.language === code);
				if (!page) {
					hints.push(__("Missing translation: {0}.", [__(label)]));
					frm.add_custom_button(__(label), () => createTranslation(frm, code), __("Create Translation"));
				} else if (page.modified < frm.doc.modified) hints.push(__("This page changed after its {0} version ({1}): check the translation.", [__(label), page.name]));
			}
		} else if (frm.doc.language && frm.doc.translation_of) {
			const master = await frappe.db.get_value("Web Page", frm.doc.translation_of, "modified");
			const modified = master.message && master.message.modified;
			if (modified && modified > frm.doc.modified) hints.push(__("The German page changed after this one: check the translation."));
		}
		frm.set_intro(hints.join("<br>"), "orange");
	}

	function createTranslation(frm, lang) {
		const rest = (frm.doc.route || "").replace(/^de\//, "");
		frappe.prompt(
			[
				{ fieldname: "title", fieldtype: "Data", label: __("Title"), reqd: 1, default: frm.doc.title },
				{ fieldname: "route", fieldtype: "Data", label: __("Route"), reqd: 1, default: `${lang}/${rest}` },
			],
			(values) => {
				const page = frappe.model.copy_doc(frm.doc);
				Object.assign(page, values, { language: lang, translation_of: frm.doc.name, published: 0 });
				frappe.set_route("Form", "Web Page", page.name);
			},
			__("Create {0} version", [__(LANGUAGES[lang])]),
			__("Create")
		);
	}

	frappe.ui.form.on("Web Page", {
		refresh(frm) {
			if (frm.is_new()) return;
			webPageHints(frm);  // Frappe's sidebar already links "See on Website"
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
