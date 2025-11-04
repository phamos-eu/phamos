frappe.listview_settings['Implementation'] = {
    get_indicator: function(doc) {
        if (doc.status === "Open") {
            return [__("Open"), "blue", "status,=,Open"];
        } else if (doc.status === "Completed") {
            return [__("Completed"), "green", "status,=,Completed"];
        } else if (doc.status === "Cancelled") {
            return [__("Cancelled"), "red", "status,=,Cancelled"];
        } else if (doc.status === "On Hold") {
            return [__("On Hold"), "gray", "status,=,On Hold"];
        } else if (doc.status === "Escalated") {
            return [__("Escalated"), "orange", "status,=,Escalated"];
        }
    }
};
