// Copyright (c) 2026, phamos.eu and contributors
// For license information, please see license.txt

// Implementation Change (#1971): the decisions on a change, for phamos users in Desk.
// Customers decide in the cockpit; here a PM can record a customer's answer by naming the Contact.
const METHOD = "phamos.phamos.doctype.implementation_change.implementation_change.";

frappe.ui.form.on("Implementation Change", {
	refresh(frm) {
		const call = (method, args) =>
			frappe.call({ method: METHOD + method, args: { name: frm.doc.name, ...args } }).then(() => frm.reload_doc());
		const status = frm.doc.status;

		if (status === "Proposed" && !frm.doc.agreed_by_phamos) {
			frm.add_custom_button(__("Agree"), () => call("agree_change"));
		}
		if (status === "Proposed" && !frm.doc.agreed_by_customer) {
			frm.add_custom_button(__("Customer agreed"), () =>
				frappe.prompt(
					{ fieldname: "contact", fieldtype: "Link", options: "Contact", label: __("Customer contact"), reqd: 1 },
					(v) => call("agree_change", { contact: v.contact }),
					__("Record the customer's agreement")
				)
			);
		}
		if (["Proposed", "Agreed"].includes(status)) {
			frm.add_custom_button(__("Reject"), () =>
				frappe.prompt({ fieldname: "reason", fieldtype: "Small Text", label: __("Reason"), reqd: 1 }, (v) =>
					call("reject_change", { reason: v.reason }), __("Reject change"))
			);
		}
		if (["Applied – awaiting customer", "Disputed"].includes(status)) {
			frm.add_custom_button(__("Customer confirmed"), () =>
				frappe.prompt(
					{ fieldname: "contact", fieldtype: "Link", options: "Contact", label: __("Customer contact"), reqd: 1 },
					(v) => call("confirm_change", { contact: v.contact }),
					__("Record the customer's confirmation")
				)
			);
		}
		if (status === "Applied – awaiting customer") {
			frm.add_custom_button(__("Customer disputed"), () =>
				frappe.prompt(
					[
						{ fieldname: "contact", fieldtype: "Link", options: "Contact", label: __("Customer contact"), reqd: 1 },
						{ fieldname: "reason", fieldtype: "Small Text", label: __("Reason"), reqd: 1 },
					],
					(v) => call("dispute_change", v),
					__("Record the customer's dispute")
				)
			);
		}
	},
});
