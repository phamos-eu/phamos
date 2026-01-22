frappe.ui.form.on('Sales Invoice', {
    is_return(frm) {
        if (frm.doc.is_return) {
            frappe.after_ajax(() => {
                setTimeout(() => {
                    frm.set_value('update_billed_amount_in_sales_order', 1);
                    frm.set_value('update_outstanding_for_self', 0);
                }, 300);
            });
        }
    },

    refresh(frm) {
        if (frm.doc.is_return) {
            frappe.after_ajax(() => {
                setTimeout(() => {
                    frm.set_value('update_billed_amount_in_sales_order', 1);
                    frm.set_value('update_outstanding_for_self', 0);
                }, 300);
            });
        }
    }
});
