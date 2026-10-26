// Copyright (c) 2026, phamos.eu and contributors

frappe.listview_settings["Event Ticket Order"] = {
	add_fields: ["status"],
	get_indicator(doc) {
		const colour = { Free: "gray", Booked: "red", Ordered: "blue", Invoiced: "orange", Paid: "green",
			Credited: "purple", Cancelled: "gray" }[doc.status] || "gray";
		return [__(doc.status), colour, `status,=,${doc.status}`];
	},
};
