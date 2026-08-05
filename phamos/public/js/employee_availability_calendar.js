frappe.views.calendar["Employee Availability"] = {
	field_map: {
		start: "start",
		end: "end",
		id: "name",
		title: "title",
		allDay: "allDay",
	},
	filters: [
		{
			fieldtype: "Link",
			fieldname: "employee",
			options: "Employee",
			label: __("Employee"),
		},
		{
			fieldtype: "Date",
			fieldname: "date",
			label: __("Date"),
		},
		{
			fieldtype: "Select",
			fieldname: "slot_status",
			label: __("Slot Status"),
			options: "All\nAvailable\nBooked\nOptional",
			default: "All",
		},
	],
	editable: false,
	selectable: false,
	eventStartEditable: false,
	eventDurationEditable: false,
	eventRender(event, element) {
		element.attr("title", event.title || "");
		element.css("cursor", "default");
	},
	eventClick() {
		return false;
	},
	get_events_method:
		"phamos.phamos.doctype.employee_availability.employee_availability.get_employee_availability_calendar_events",
};

function ensure_employee_availability_legend() {
	const calendarRoot = document.querySelector(".fc");
	if (!calendarRoot) return;

	const sideSection = document.querySelector(".layout-side-section");
	if (!sideSection) return;

	if (sideSection.querySelector(".employee-availability-legend")) return;

	const legend = document.createElement("div");
	legend.className = "employee-availability-legend";
	legend.style.marginTop = "16px";
	legend.style.padding = "10px";
	legend.style.border = "1px solid #e3e3e3";
	legend.style.borderRadius = "8px";
	legend.style.background = "#fff";
	legend.innerHTML = [
		'<div style="font-weight:600; margin-bottom:8px;">Status Legend</div>',
		'<div style="display:flex; align-items:center; gap:8px; margin-bottom:6px;"><span style="width:10px; height:10px; border-radius:50%; display:inline-block; background:#D94841;"></span><span>Booked</span></div>',
		'<div style="display:flex; align-items:center; gap:8px; margin-bottom:6px;"><span style="width:10px; height:10px; border-radius:50%; display:inline-block; background:#E0A106;"></span><span>Optional</span></div>',
		'<div style="display:flex; align-items:center; gap:8px;"><span style="width:10px; height:10px; border-radius:50%; display:inline-block; background:#2EAF4A;"></span><span>Available</span></div>',
	].join("");

	sideSection.appendChild(legend);
}

if (typeof frappe !== "undefined" && frappe.router && frappe.router.on) {
	frappe.router.on("change", () => {
		window.setTimeout(ensure_employee_availability_legend, 100);
	});
}

window.setTimeout(ensure_employee_availability_legend, 100);
