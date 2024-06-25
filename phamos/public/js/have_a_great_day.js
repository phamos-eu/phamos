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
            console.log("Document ready, initializing dialog...");

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
                                    fieldtype: "Check",
                                    label: __("Good Morning"),
                                    fieldname: "good_morning",
                                    in_list_view: 1,
                                    reqd: 1,
                                    description: "Between 8:00 AM and 21 PM, a dialog prompts users to rate their mood and sleep, select daily focuses, and submit, enhancing morning productivity and well-being.",
                                },
                                {
                                    fieldtype: "Rating",
                                    label: __("How are you feeling Today?"),
                                    fieldname: "how_are_you",
                                    in_list_view: 1,
                                    reqd: 1,
                                    description: "(Rate from 'Terrible' (1) to 'Great' (5))",
                                },
                                {
                                    fieldtype: "Rating",
                                    label: __("How well did you sleep Today?"),
                                    fieldname: "how_well_did_you_sleep_today",
                                    in_list_view: 1,
                                    reqd: 1,
                                    description: "(Rate from 'Not at all' (1) to 'Very' (5))",
                                },
                                {
                                    fieldtype: "MultiSelect",
                                    label: __("What's your main focus for today?"),
                                    fieldname: "whats_your_main_focus_for_today",
                                    options: ["Work", "Pets", "Family", "Self Care", "Study"],
                                    description: "(Pick up to 3.)",
                                    reqd: 1, // Required field
                                    validate: function(value) {
                                        if (value && value.length > 3) {
                                            return __("You can select up to 3 activities.");
                                        }
                                    }
                                }
                            ],
                            primary_action_label: __("Save"),
                            primary_action: (values) => {
                                this.submit(values);
                                this.dialog.hide();
                                
                            }
                            
                        });
                        

                        // Set the width using CSS
                        this.dialog.$wrapper.find('.modal-dialog').css('max-width', '500px');

                        // Show the dialog
                        this.dialog.show();

                        console.log("Dialog initialized and shown.");
                    }
                }
            });
        } else {
            console.log("Dialog cannot be shown now, as current time is not between 8 am to 21 pm.");
        }
    }

    submit(values) {
        // Handle form submission or call backend method
        console.log("Submitted values:", values);

        // Example: Call backend function to create a record
        this.createRecord(values.good_morning, values.how_are_you, values.how_well_did_you_sleep_today, values.whats_your_main_focus_for_today);

        // Hide the dialog after submission
        this.dialog.hide();
    }

    createRecord(goodMorning, moodRating, sleepRating, focusActivities) {
        // Example: Use frappe.call or any backend API to create a record
        frappe.call({
            method: "phamos.phamos.doctype.have_a_great_day.have_a_great_day.create_todays_feedback",
            args: {
                good_morning: goodMorning,
                mood_rating: moodRating,
                sleep_rating: sleepRating,
                focus_activities: focusActivities
            },
            callback: function(response) {
                frappe.msgprint(__("Form submitted successfully!"));
            }
        });
    }
}

// Instantiate the dialog class when the document is ready
$(document).on('app_ready', function() {
    console.log("in app ready");
    new MorningFeedbackDialog();
});
