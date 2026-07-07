// Copyright (c) 2026, phamos.eu and contributors
// For license information, please see license.txt

frappe.ui.form.on("Lead Data", {
    refresh(frm) {
        if (frm.is_new()) return;

        frm.add_custom_button(__("Create Lead"), () => {
            show_lead_preview_dialog(frm);
        }).addClass("btn-primary");
    },
});

function show_lead_preview_dialog(frm) {
    const primary_address = first_row(frm.doc.lead_data_address);
    const primary_contact = first_row(frm.doc.lead_data_contact);

    const dialog = new frappe.ui.Dialog({
        title: __("Preview Lead Data"),
        size: "extra-large",
        fields: [
            { fieldtype: "Section Break", label: __("Lead") },
            { fieldname: "salutation", fieldtype: "Data", label: __("Salutation"), default: frm.doc.salutation || primary_contact.salutation || "" },
            { fieldname: "first_name", fieldtype: "Data", label: __("First Name"), default: frm.doc.first_name || primary_contact.first_name || "" },
            { fieldname: "middle_name", fieldtype: "Data", label: __("Middle Name"), default: frm.doc.middle_name || primary_contact.middle_name || "" },
            { fieldname: "last_name", fieldtype: "Data", label: __("Last Name"), default: frm.doc.last_name || primary_contact.last_name || "" },
            { fieldname: "job_title", fieldtype: "Data", label: __("Job Title"), default: frm.doc.job_title || primary_contact.designation || "" },
            { fieldtype: "Column Break" },
            { fieldname: "company_name", fieldtype: "Data", label: __("Company Name"), default: frm.doc.organization_name || primary_address.address_title || "" },
            { fieldname: "email_id", fieldtype: "Data", label: __("Email"), default: frm.doc.email || primary_contact.email_address || primary_address.email_address || "" },
            { fieldname: "website", fieldtype: "Data", label: __("Website"), default: frm.doc.website || "" },
            { fieldname: "mobile_no", fieldtype: "Data", label: __("Mobile No"), default: frm.doc.mobile_no || primary_contact.mobile_no || "" },
            { fieldname: "phone", fieldtype: "Data", label: __("Phone"), default: frm.doc.phone || primary_contact.phone || primary_address.phone || "" },

            { fieldtype: "Section Break", label: __("Address Preview") },
            { fieldname: "address_title", fieldtype: "Data", label: __("Address Title"), default: primary_address.address_title || frm.doc.organization_name || "" },
            { fieldname: "address_line_1", fieldtype: "Data", label: __("Address Line 1"), default: primary_address.address_line_1 || "" },
            { fieldname: "address_line_2", fieldtype: "Data", label: __("Address Line 2"), default: primary_address.address_line_2 || "" },
            { fieldtype: "Column Break" },
            { fieldname: "city", fieldtype: "Data", label: __("City"), default: frm.doc.city || primary_address.citytown || "" },
            { fieldname: "state", fieldtype: "Data", label: __("State/Province"), default: frm.doc.stateprovince || primary_address.stateprovince || "" },
            { fieldname: "country", fieldtype: "Data", label: __("Country"), default: frm.doc.country || primary_address.country || "" },
            { fieldname: "pincode", fieldtype: "Data", label: __("Postal Code"), default: primary_address.postal_code || "" },

            { fieldtype: "Section Break", label: __("Contact Preview") },
            { fieldname: "contact_first_name", fieldtype: "Data", label: __("First Name"), default: primary_contact.first_name || frm.doc.first_name || "" },
            { fieldname: "contact_middle_name", fieldtype: "Data", label: __("Middle Name"), default: primary_contact.middle_name || frm.doc.middle_name || "" },
            { fieldname: "contact_last_name", fieldtype: "Data", label: __("Last Name"), default: primary_contact.last_name || frm.doc.last_name || "" },
            { fieldtype: "Column Break" },
            { fieldname: "contact_designation", fieldtype: "Data", label: __("Designation"), default: primary_contact.designation || frm.doc.job_title || "" },
            { fieldname: "contact_email", fieldtype: "Data", label: __("Email"), default: primary_contact.email_address || frm.doc.email || "" },
            { fieldname: "contact_phone", fieldtype: "Data", label: __("Phone"), default: primary_contact.phone || frm.doc.phone || "" },
            { fieldname: "contact_mobile_no", fieldtype: "Data", label: __("Mobile No"), default: primary_contact.mobile_no || frm.doc.mobile_no || "" },
        ],
        primary_action_label: __("Create Lead"),
        primary_action(values) {
            if (!values) return;
            create_lead_from_preview(frm, dialog, values);
        },
        secondary_action_label: __("Cancel"),
        secondary_action() {
            dialog.hide();
        },
    });

    dialog.show();
}

function create_lead_from_preview(frm, dialog, values) {
    const lead_doc = {
        doctype: "Lead",
        salutation: values.salutation || "",
        first_name: values.first_name || values.company_name || __("Unknown"),
        middle_name: values.middle_name || "",
        last_name: values.last_name || "",
        job_title: values.job_title || "",
        email_id: values.email_id || "",
        website: values.website || "",
        mobile_no: values.mobile_no || "",
        phone: values.phone || "",
        company_name: values.company_name || "",
        city: values.city || "",
        state: values.state || "",
        country: values.country || "",
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
            dialog.hide();
            frappe.msgprint(__("Lead created successfully: {0}", [lead_name || ""]));
            frappe.show_alert({ message: __("Lead created successfully!"), indicator: "green" });
        },
    });
}

function first_row(rows) {
    return rows && rows.length ? rows[0] : {};
}
