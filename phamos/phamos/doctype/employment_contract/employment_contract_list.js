// Copyright (c) 2026, phamos.eu and contributors
// For license information, please see license.txt

frappe.listview_settings["Employment Contract"] = {
	add_fields: ["status"],
	get_indicator(doc) {
		const colors = { Draft: "red", Upcoming: "blue", Active: "green", Expired: "gray", Cancelled: "red" };
		return [__(doc.status), colors[doc.status] || "gray", `status,=,${doc.status}`];
	},
};
