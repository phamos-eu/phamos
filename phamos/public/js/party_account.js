// Copyright (c) 2026, phamos.eu and contributors
// For license information, please see license.txt

// Shared by the Customer and Supplier forms: a button that creates the party's
// own ledger account (Debitorenkonto / Kreditorenkonto) as configured in
// phamos Settings → Party Accounts and links it in the party's Accounts table (#1529).

frappe.provide("phamos.party_account");

phamos.party_account.get_button_label = function (party_type) {
	return party_type === "Customer" ? __("Create Debtor Account") : __("Create Creditor Account");
};

phamos.party_account.setup_button = function (frm) {
	// The server requires write access on the party and create access on Account.
	if (frm.is_new() || !frm.has_perm("write") || !frappe.model.can_create("Account")) {
		return;
	}

	const docname = frm.doc.name;
	phamos.party_account.get_missing_companies(frm).then((companies) => {
		// The user may have navigated to another document meanwhile.
		if (frm.doc.name !== docname || !companies.length) {
			return;
		}

		frm.add_custom_button(
			phamos.party_account.get_button_label(frm.doctype),
			() => phamos.party_account.on_button_click(frm),
			__("Actions")
		);
	});
};

phamos.party_account.get_missing_companies = function (frm) {
	return frappe
		.xcall("phamos.accounting.party_account.get_configured_companies", {
			party_type: frm.doctype,
		})
		.then((configured_companies) =>
			phamos.party_account.get_companies_without_account(frm, configured_companies)
		);
};

phamos.party_account.on_button_click = async function (frm) {
	if (frm.is_dirty()) {
		// The server saves the stored party, and the form reloads afterwards, so
		// unsaved edits would be lost. Save them first.
		await frm.save();
		// frm.save() resolves even when the server rejects the save; the form then
		// still has unsaved changes and nothing must be created.
		if (frm.is_dirty()) {
			return;
		}
	}

	// The save may already have created the account ("Create Automatically and Require").
	const companies = await phamos.party_account.get_missing_companies(frm);
	if (!companies.length) {
		frappe.show_alert({
			message: __("All configured companies already have an account."),
			indicator: "green",
		});
		return;
	}

	phamos.party_account.choose_company(frm, companies);
};

phamos.party_account.get_companies_without_account = function (frm, configured_companies) {
	const companies_with_account = (frm.doc.accounts || [])
		.filter((row) => row.account)
		.map((row) => row.company);
	return configured_companies.filter((company) => !companies_with_account.includes(company));
};

phamos.party_account.choose_company = function (frm, companies) {
	if (companies.length === 1) {
		phamos.party_account.create(frm, companies[0]);
		return;
	}

	const default_company = frappe.defaults.get_user_default("Company");
	frappe.prompt(
		{
			fieldname: "company",
			fieldtype: "Select",
			label: __("Company"),
			options: companies,
			default: companies.includes(default_company) ? default_company : companies[0],
			reqd: 1,
		},
		(values) => phamos.party_account.create(frm, values.company),
		phamos.party_account.get_button_label(frm.doctype),
		__("Create")
	);
};

phamos.party_account.create = function (frm, company) {
	frappe.call({
		method: "phamos.accounting.party_account.create_party_account",
		args: {
			party_type: frm.doctype,
			party: frm.doc.name,
			company: company,
		},
		freeze: true,
		freeze_message: __("Creating account..."),
		callback: (r) => {
			if (r.exc || !r.message) {
				return;
			}
			frm.reload_doc();
			frappe.show_alert({
				// show_alert renders HTML and get_form_link does not escape the text.
				message: __("Account {0} created", [
					frappe.utils.get_form_link(
						"Account",
						r.message.account,
						true,
						frappe.utils.escape_html(r.message.account)
					),
				]),
				indicator: "green",
			});
		},
	});
};
