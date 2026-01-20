// Copyright (c) 2025, phamos.eu and contributors
// For license information, please see license.txt

frappe.ui.form.on("Team", {
    refresh(frm) {
        calculate_capacity(frm);
        calculate_leave_and_holiday(frm);
        calculate_capacity_daily(frm);
    }
});


frappe.ui.form.on("Team Members", {
    employee: function (frm, cdt, cdn) {
        let row = locals[cdt][cdn];

        if (!row.employee) return;

        frappe.db.get_value(
            "Weekly Working Hours",
            { employee: row.employee },
            "total_work_hours",
            function (r) {
                if (r && r.total_work_hours != null) {
                    frappe.model.set_value(cdt,cdn,"weekly_capacity",r.total_work_hours);
                } else {
                    frappe.model.set_value(cdt,cdn,"weekly_capacity",0);
                }
            }
        );
    },
    weekly_capacity(frm, cdt, cdn) {
        calculate_capacity(frm);
        calculate_capacity_daily(frm);
    },
    team_members_remove(frm) {
        calculate_capacity(frm);
        calculate_capacity_daily(frm);
    },
});

frappe.ui.form.on("Team Member Leaves and Holiday", {
    team_members_remove(frm) {
        calculate_leave_and_holiday(frm);
    }
});


function calculate_capacity(frm) {
    let total = 0;
    (frm.doc.team_members || []).forEach(row => {
        total += row.weekly_capacity || 0;
    });

    frm.set_value("team_members_capacity", total);

}


function calculate_leave_and_holiday(frm) {
    let total = 0;
    (frm.doc.team_member_leaves_and_holiday || []).forEach(row => {
        total += row.hrs || 0;
    });

    frm.set_value("team_members_leaves_and_holidays", total);
    console.log(total)

}