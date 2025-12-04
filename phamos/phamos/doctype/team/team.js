// Copyright (c) 2025, phamos.eu and contributors
// For license information, please see license.txt

frappe.ui.form.on("Team", {
    refresh(frm) {
        calculate_capacity(frm);
    },
    after_save: function(frm) {
        frappe.call({
            method: "frappe.client.insert",
            args: {
                doc: {
                    doctype: "Team Capacity Ledger",
                    team: frm.doc.team_name,
                    total_team_capacity: frm.doc.total_team_capacity,
                    date: frappe.datetime.nowdate()
                }
            },
            callback: function(r) {
                if (!r.exc) {
                    frappe.show_alert("Team Capacity Ledger updated successfully!");
                }
            }
        });
    }
});


frappe.ui.form.on("Team Members", {
    weekly_capacity(frm, cdt, cdn) {
        calculate_capacity(frm);
    },
    team_members_remove(frm) {
        calculate_capacity(frm);
    }
});

function calculate_capacity(frm) {
    let total = 0;
    (frm.doc.team_members || []).forEach(row => {
        total += row.weekly_capacity || 0;
    });

    frm.set_value("total_team_capacity", total);
}

