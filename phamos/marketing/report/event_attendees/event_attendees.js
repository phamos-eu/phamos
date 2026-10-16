frappe.query_reports["Event Attendees"] = {
	filters: [
		{ fieldname: "event", label: __("Event"), fieldtype: "Link", options: "Marketing Content", reqd: 1 },
		{ fieldname: "role", label: __("Role"), fieldtype: "Select", options: "\nGuest\nSpeaker\nSponsor\nPartner\nEmployee\nPress\nOther" },
		{ fieldname: "status", label: __("Status"), fieldtype: "Select", options: "\nInvited\nRegistered\nConfirmed\nWaitlisted\nAttended\nNo Show\nCancelled" },
		{ fieldname: "payment_status", label: __("Payment"), fieldtype: "Select", options: "\nNot Required\nPending\nOrdered\nInvoiced\nPaid\nCancelled" },
		{ fieldname: "crm_status", label: __("CRM"), fieldtype: "Select", options: "\nUnlinked\nLinked\nNeeds Review" },
		{ fieldname: "follow_up_status", label: __("Follow-up"), fieldtype: "Select", options: "\nPending\nDone\nNot Needed" },
		{ fieldname: "vip", label: __("VIP only"), fieldtype: "Check" },
	],
};
