frappe.ui.form.on("Job Applicant", {
	refresh: function (frm) {
		if (!frm.doc.status == "") {
			frm.add_custom_button(__("Send Interview Slot booking link"), () => {
				// Prompt for Interview Round selection (filtered by Designation)
				frappe.prompt(
					{
						label: __("Interview Round"),
						fieldname: "interview_round",
						fieldtype: "Link",
						options: "Interview Round",
						reqd: 1,
						get_query: function() {
							return {
								filters: {
									designation: frm.doc.designation || ""
								}
							};
						}
					},
					function(values) {
						frappe.call({
							method: "invite_for_interview",
							doc: frm.doc,
							args: {
								interview_round: values.interview_round
							},
							callback(r){
								frappe.msgprint("Invite sent");
								if (r.message && r.message.custom_shortlisted == "Yes") { 
									frm.reload_doc();
								}
							}
						});
					},
					__("Select Interview Round"),
					__("Send")
				);
			});
		}
	}
});