// Accounting Receipt list: "Fetch e-mails" pulls the receipt inboxes now instead of waiting
// for Frappe's 10-minute scheduler (#1964). The pull runs in the background; the job sends
// `receipt_emails_fetched` to the clicking user when an account is done.
frappe.listview_settings["Accounting Receipt"] = {
	onload(listview) {
		if (!frappe.model.can_create("Accounting Receipt")) return;

		listview.page.add_inner_button(__("Fetch e-mails"), fetch_receipt_emails);

		// onload runs once per list instance; off() keeps a re-created list from listening twice.
		frappe.realtime.off("receipt_emails_fetched");
		frappe.realtime.on("receipt_emails_fetched", (data) => {
			if (data.error) {
				frappe.show_alert({ message: data.error, indicator: "red" }, 10);
			} else if (data.created) {
				frappe.show_alert({ message: __("{0} new receipts from e-mail", [data.created]), indicator: "green" });
			} else {
				frappe.show_alert({ message: __("No new e-mails"), indicator: "blue" });
			}
			listview.refresh();
		});
	},
};

function fetch_receipt_emails() {
	frappe.call({
		method: "phamos.accounting.email_pull.fetch_receipt_emails",
		type: "POST",
		freeze: false,
		callback({ message }) {
			if (message.queued.length) {
				frappe.show_alert({ message: __("Fetching e-mails…"), indicator: "blue" });
			} else {
				frappe.show_alert({ message: __("E-mails are already being fetched"), indicator: "orange" });
			}
		},
	});
}
