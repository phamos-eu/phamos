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
}
});