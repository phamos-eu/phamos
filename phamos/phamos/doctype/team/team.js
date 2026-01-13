// Copyright (c) 2025, phamos.eu and contributors
// For license information, please see license.txt

frappe.ui.form.on("Team", {
    refresh(frm) {
        set_daily_from_weekly(frm);
        calculate_capacity(frm);
        calculate_leave_and_holiday(frm);
        calculate_capacity_daily(frm);
    }
});


frappe.ui.form.on("Team Members", {
    weekly_capacity(frm, cdt, cdn) {
        set_daily_from_weekly(frm);
        calculate_capacity(frm);
        calculate_capacity_daily(frm);
    },
    team_members_remove(frm) {
        calculate_capacity(frm);
        calculate_capacity_daily(frm);
    },
    daily_capacityhrs(frm, cdt, cdn) {
        calculate_capacity_daily(frm);
    }
});

frappe.ui.form.on("Team Member Leaves and Holiday", {
    team_members_remove(frm) {
        calculate_leave_and_holiday(frm);
    }
});

function set_daily_from_weekly(frm) {
    (frm.doc.team_members || []).forEach(row => {
        row.daily_capacityhrs = row.weekly_capacity
            ? row.weekly_capacity / 5
            : 0;
    });

    frm.refresh_field("team_members");
}


function calculate_capacity(frm) {
    let total = 0;
    (frm.doc.team_members || []).forEach(row => {
        total += row.weekly_capacity || 0;
    });

    frm.set_value("team_members_capacity", total);

}

function calculate_capacity_daily(frm) {
    let total = 0;
    (frm.doc.team_members || []).forEach(row => {
        total += row.daily_capacityhrs || 0;
    });

    frm.set_value("team_members_capacitydaily", total);

}

function calculate_leave_and_holiday(frm) {
    let total = 0;
    (frm.doc.team_member_leaves_and_holiday || []).forEach(row => {
        total += row.hrs || 0;
    });

    frm.set_value("team_members_leaves_and_holidays", total);
    console.log(total)

}