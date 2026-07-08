// Copyright (c) 2026, phamos.eu and contributors
// For license information, please see license.txt

frappe.ui.form.on("Lead Data", {
    refresh(frm) {
        if (frm.is_new()) return;

        frm.add_custom_button(__("Create Lead"), () => {
            create_lead_from_lead_data(frm);
        }).addClass("btn-primary");
    },
});

function create_lead_from_lead_data(frm) {
    const primary_address = first_row(frm.doc.lead_data_address);
    const primary_contact = first_row(frm.doc.lead_data_contact);

    const lead_doc = {
        doctype: "Lead",
        salutation: frm.doc.salutation || primary_contact.salutation || "",
        first_name: frm.doc.first_name || primary_contact.first_name || frm.doc.organization_name || __("Unknown"),
        middle_name: frm.doc.middle_name || primary_contact.middle_name || "",
        last_name: frm.doc.last_name || primary_contact.last_name || "",
        job_title: frm.doc.job_title || primary_contact.designation || "",
        email_id: frm.doc.email || primary_contact.email_address || primary_address.email_address || "",
        website: frm.doc.website || "",
        mobile_no: frm.doc.mobile_no || primary_contact.mobile_no || "",
        phone: frm.doc.phone || primary_contact.phone || primary_address.phone || "",
        company_name: frm.doc.organization_name || primary_address.address_title || "",
        city: frm.doc.city || primary_address.citytown || "",
        state: frm.doc.stateprovince || primary_address.stateprovince || "",
        country: frm.doc.country || primary_address.country || "",
    };

    frappe.call({
        method: "frappe.client.insert",
        args: {
            doc: lead_doc,
        },
        freeze: true,
        freeze_message: __("Creating Lead..."),
        callback(r) {
            if (r.exc) {
                frappe.msgprint({ title: __("Error"), indicator: "red", message: r.exc });
                return;
            }

            const lead_name = r.message && r.message.name;
            frappe.msgprint(__("Lead created successfully: {0}", [lead_name || ""]));
            frappe.show_alert({ message: __("Lead created successfully!"), indicator: "green" });
        },
    });
}

function first_row(rows) {
    return rows && rows.length ? rows[0] : {};
}
