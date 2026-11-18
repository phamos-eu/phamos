frappe.ui.form.on("Issue", {
	refresh: function (frm) {
        if (!frm.doc.accounting_receipt) {
            frm.add_custom_button(__('Accounting Receipt'), () => {
                    frappe.call({
                        method: "phamos.phamos.doctype.accounting_receipt.accounting_receipt.make_accounting_receipt",
                        args: {
                            issue: frm.doc.name
                        },
                        callback(r){
                            frappe.set_route('Form', 'Accounting Receipt', r.message)
                        }
                    })
            }, __("Create"));
	    }
		phamos_add_open_in_cockpit(frm);
}
});

// "Open in Cockpit" (#1957): one entry per cockpit that can show this Issue, best fit first;
// each opens the cockpit's Issue page in a new tab. No fitting cockpit, no group.
function phamos_add_open_in_cockpit(frm) {
	if (frm.is_new()) return;
	const name = frm.doc.name;
	frappe.call({
		method: "phamos.api.issue_cockpits.get_issue_cockpits",
		args: { name },
		callback(r) {
			if (frm.doc.name !== name) return; // the form moved on while the call ran
			(r.message || []).forEach((cockpit) => {
				// Two refreshes of the same Issue can overlap; Frappe dedupes the toolbar entry
				// but not the mobile menu item, so drop any earlier copy first.
				frm.remove_custom_button(cockpit.label, __("Open in Cockpit"));
				frm.add_custom_button(
					cockpit.label,
					() => window.open(cockpit.url, "_blank", "noopener"),
					__("Open in Cockpit")
				);
			});
		},
	});
}