frappe.listview_settings["Monthly Implementation Summary"] = {
	add_fields: ["status"],
	get_indicator: function (doc) {
		if (doc.status === "Closed") {
			return [__("Closed"), "green", "status,=,Closed"];
		} else if (doc.status === "Open") {
			return [__("Open"), "orange", "status,=,Open"];
		}
		return [__("Draft"), "red", "status,=,Draft"];
	},
};
