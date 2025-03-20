frappe.ui.form.on("Timesheet", {
	refresh:function(frm){
		console.log('****************************')
		if(frm.doc.customer){
			frm.set_query("custom_delivery_note", function() {
	            return {
	                filters: {
	                    customer: frm.doc.customer,
	                    status:["!=","Completed"]
	                }
	            };
	        });
	    }
	},
});