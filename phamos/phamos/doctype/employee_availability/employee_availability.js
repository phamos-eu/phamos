// Copyright (c) 2026, phamos.eu and contributors
// For license information, please see license.txt

frappe.ui.form.on("Employee Availability", {
	onload(frm) {
		set_default_month_range(frm);
	},

	employee(frm) {
		queue_available_slot_fetch(frm);
	},

	appointment_duration(frm) {
		update_appointment_slots_from_available(frm);
	},

	day(frm) {
		update_appointment_slots_from_available(frm);
	},

	from_date(frm) {
		queue_available_slot_fetch(frm);
	},

	to_date(frm) {
		queue_available_slot_fetch(frm);
	},
});

function set_default_month_range(frm) {
	if (!frm.is_new()) return;

	const today = frappe.datetime.str_to_obj(frappe.datetime.get_today());
	const first = new Date(today.getFullYear(), today.getMonth(), 1);
	const last = new Date(today.getFullYear(), today.getMonth() + 1, 0);

	const updates = {};
	if (!frm.doc.from_date) {
		updates.from_date = frappe.datetime.obj_to_str(first);
	}
	if (!frm.doc.to_date) {
		updates.to_date = frappe.datetime.obj_to_str(last);
	}

	if (Object.keys(updates).length) {
		frm.set_value(updates);
	}
}

function is_available_fetch_ready(frm) {
	return Boolean(
		frm.doc.employee &&
		frm.doc.from_date &&
		frm.doc.to_date
	);
}

function queue_available_slot_fetch(frm) {
	if (frm._available_slot_timer) {
		clearTimeout(frm._available_slot_timer);
	}

	if (!is_available_fetch_ready(frm)) {
		if ((frm.doc.available_slots || []).length) {
			frm.clear_table("available_slots");
			frm.refresh_field("available_slots");
		}
		clear_appointment_slots(frm);
		return;
	}

	show_slot_fetch_progress(0, 2, __("Queued"));

	frm._available_slot_timer = setTimeout(() => {
		fetch_available_slots(frm);
	}, 200);
}

function fetch_available_slots(frm) {
	if (!is_available_fetch_ready(frm)) {
		if ((frm.doc.available_slots || []).length) {
			frm.clear_table("available_slots");
			frm.refresh_field("available_slots");
		}
		clear_appointment_slots(frm);
		show_slot_fetch_progress(2, 2, __("Done"));
		return;
	}

	if (frm.doc.from_date > frm.doc.to_date) {
		frm.clear_table("available_slots");
		frm.refresh_field("available_slots");
		clear_appointment_slots(frm);
		show_slot_fetch_progress(2, 2, __("Done"));
		return;
	}

	const requestId = (frm._available_slot_request_id || 0) + 1;
	frm._available_slot_request_id = requestId;
	show_slot_fetch_progress(1, 2, __("Fetching from Mailcow"));

	frappe.call({
		method: "phamos.phamos.doctype.employee_availability.employee_availability.generate_available_slots",
		args: {
			employee: frm.doc.employee,
			from_date: frm.doc.from_date,
			to_date: frm.doc.to_date,
		},
		freeze: true,
		freeze_message: __("Fetching available slots from Mailcow..."),
		callback(r) {
			if (requestId !== frm._available_slot_request_id) {
				return;
			}

			const slots = Array.isArray(r.message) ? r.message : [];
			frm.clear_table("available_slots");
			slots.forEach((slot) => {
				frm.add_child("available_slots", slot);
			});
			frm.refresh_field("available_slots");
			update_appointment_slots_from_available(frm);
			show_slot_fetch_progress(2, 2, __("Done"));
		},
		error() {
			show_slot_fetch_progress(2, 2, __("Failed"));
		},
	});
}

function show_slot_fetch_progress(current, total, message) {
	frappe.show_progress(__("Available Slots"), current, total, message || "");
}

function clear_appointment_slots(frm) {
	if ((frm.doc.appointment_slots || []).length) {
		frm.clear_table("appointment_slots");
		frm.refresh_field("appointment_slots");
	}
}

function timeToMinutes(timeValue) {
	if (!timeValue) return null;
	const parts = String(timeValue).split(":");
	if (parts.length < 2) return null;
	const h = parseInt(parts[0], 10);
	const m = parseInt(parts[1], 10);
	if (Number.isNaN(h) || Number.isNaN(m)) return null;
	return h * 60 + m;
}

function minutesToTime(totalMinutes) {
	const h = Math.floor(totalMinutes / 60);
	const m = totalMinutes % 60;
	return `${String(h).padStart(2, "0")}:${String(m).padStart(2, "0")}:00`;
}

function update_appointment_slots_from_available(frm) {
	const selectedDay = frm.doc.day;
	const duration = parseInt(frm.doc.appointment_duration, 10);

	if (!selectedDay || Number.isNaN(duration) || duration <= 0) {
		clear_appointment_slots(frm);
		return;
	}

	frm.clear_table("appointment_slots");
	const seen = new Set();

	(frm.doc.available_slots || []).forEach((slot) => {
		if (slot.day !== selectedDay) return;

		const start = timeToMinutes(slot.from_time);
		const end = timeToMinutes(slot.to_time);
		if (start === null || end === null || end <= start) return;

		let cursor = start;
		while (cursor + duration <= end) {
			const from_time = minutesToTime(cursor);
			const to_time = minutesToTime(cursor + duration);
			const key = `${slot.date}|${from_time}|${to_time}`;

			if (!seen.has(key)) {
				frm.add_child("appointment_slots", {
					date: slot.date,
					day: selectedDay,
					duration: duration * 60,
					from_time,
					to_time,
				});
				seen.add(key);
			}

			cursor += duration;
		}
	});

	frm.refresh_field("appointment_slots");
}