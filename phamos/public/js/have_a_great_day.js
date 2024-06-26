// Define a class for the dialog
class MorningFeedbackDialog {
    constructor() {
        this.dialog = null;
        this.init();
    }

    init() {
        var now = new Date();
        var hours = now.getHours();
        // Check if current time is between 8 am and 9 pm
        if (hours >= 8 && hours <= 21) {
            frappe.call({
                method: "frappe.client.get_value",
                args: {
                    doctype: "Have a Great Day",
                    filters: {
                        user: frappe.session.user,
                        feedback_date: ["between", frappe.datetime.get_today() + " 00:00:00", frappe.datetime.get_today() + " 23:59:59"]
                    },
                    fieldname: ["name", "user"]
                },
                callback: (response) => {
                    if (response.message && response.message.user) {
                        // Value found
                        console.log("Feedback found:", response.message.user);
                        // Add your code here to handle the found value
                    } else {
                        // Value not found
                        console.log("No feedback found for today.");
                        this.dialog = new frappe.ui.Dialog({
                            title: __("Have a Great Day!"),
                            fields: [
                                
                                {
                                    fieldtype: "Small Text",
                                    label: __("What are you most looking forward today?"),
                                    fieldname: "what_are_you_most_looking_forward_today",
                                    in_list_view: 1,
                                    reqd: 1, // Required field
                                },
                                {
                                    fieldtype: "Column Break",
                                  
                                },
                                {
                                    fieldtype: "Small Text",
                                    label: __("What challange will you tackle today?"),
                                    fieldname: "what_challange_will_you_tackle_today",
                                    in_list_view: 1,
                                    reqd: 1, // Required field
                                },

                            ],
                            primary_action_label: __("Save"),
                            primary_action: (values) => {
                                this.submit(values);
                                this.dialog.hide();
                                
                            }
                            
                        });
                        
                        this.dialog.$wrapper.find('.modal-dialog').css('max-width', '500px');
                        this.dialog.show();
                    }
                }
            });
        } else {
            console.log("Dialog cannot be shown now, as current time is not between 8 am to 21 pm.");
        }
    }

    submit(values) {
        // Handle form submission or call backend metho
        // Example: Call backend function to create a record
        this.createRecord(values.what_are_you_most_looking_forward_today,values.what_challange_will_you_tackle_today);
        // Hide the dialog after submission
        this.dialog.hide();
    }

    createRecord(lookingForward,todaysChallange) {
        // Example: Use frappe.call or any backend API to create a record
        frappe.call({
            method: "phamos.phamos.doctype.have_a_great_day.have_a_great_day.create_todays_feedback",
            args: {
                lookingForward:lookingForward,
                todaysChallange:todaysChallange
            },
            callback: function(response) {
                frappe.msgprint(__("Form submitted successfully!"));
            }
        });
    }
}

// Instantiate the dialog class when the document is ready
$(document).on('app_ready', function() {
    new MorningFeedbackDialog();
});
