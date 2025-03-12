frappe.ui.form.on("Job Applicant", {
	refresh: function (frm) {
		if (!frm.doc.status == "") {
			frm.add_custom_button(__("Send Interview Slot booking link"), () => {
				frappe.call({
					method: "invite_for_interview",
					doc: frm.doc,
					callback(r){
						frappe.msgprint("Invite sent");
						if (r.message && r.message.status == "Accepted") { 
							frm.reload_doc();
						}
					}
				})
			});
		}
	}
});