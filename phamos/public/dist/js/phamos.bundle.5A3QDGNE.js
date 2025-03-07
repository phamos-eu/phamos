(() => {
  // ../phamos/phamos/public/js/have_a_great_day.js
  var MorningFeedbackDialog = class {
    constructor() {
      this.dialog = null;
      this.init();
    }
    init() {
      var self = this;
      function timeToSeconds(timeStr) {
        var parts = timeStr.split(":");
        var hours = parseInt(parts[0], 10) || 0;
        var minutes = parseInt(parts[1], 10) || 0;
        var seconds = parseInt(parts[2], 10) || 0;
        return hours * 3600 + minutes * 60 + seconds;
      }
      frappe.call({
        method: "phamos.phamos.doctype.have_a_great_day.have_a_great_day.get_user_time",
        args: { user: frappe.session.user },
        callback: function(response) {
          if (response.message) {
            var userTimeStr = response.message.user_time_str || "00:00:00";
            var fromTimeStr = response.message.from_time || "00:00:00";
            var tillTimeStr = response.message.till_time || "23:59:59";
            var enable_feedback_dialog = response.message.enable_feedback_dialog;
            var userTimeSeconds = timeToSeconds(userTimeStr);
            var fromTimeSeconds = timeToSeconds(fromTimeStr);
            var tillTimeSeconds = timeToSeconds(tillTimeStr);
            if (fromTimeSeconds <= userTimeSeconds && userTimeSeconds <= tillTimeSeconds && enable_feedback_dialog == 1) {
              self.showFeedbackDialog();
            } else {
            }
          } else {
            console.error("Failed to fetch user time.");
          }
        },
        error: function(error) {
          console.error("Error:", error);
        }
      });
    }
    showFeedbackDialog() {
      var self = this;
      const user_date_fmt = frappe.datetime.get_user_date_fmt().toUpperCase();
      const user_time_fmt = frappe.datetime.get_user_time_fmt();
      frappe.db.get_value(
        "phamos Settings",
        {},
        "is_employee_feedback",
        function(value) {
          if (value && value.is_employee_feedback == 1) {
            frappe.db.get_value(
              "Employee",
              { user_id: frappe.session.user },
              "name",
              function(value_user) {
                if (value_user && value_user.name) {
                  var today_date2 = frappe.datetime.nowdate();
                  frappe.db.get_value(
                    "Have a Great Day",
                    {
                      user: frappe.session.user,
                      creation_date: today_date2
                    },
                    "name",
                    function(value_feedback) {
                      if (value_feedback && value_feedback.name) {
                      } else {
                        self.dialog_box();
                      }
                    }
                  );
                } else {
                }
              }
            );
          } else if (value && value.is_employee_feedback == 0) {
            var today_date = frappe.datetime.nowdate();
            frappe.db.get_value(
              "Have a Great Day",
              {
                user: frappe.session.user,
                creation_date: today_date
              },
              "name",
              function(value_feedback) {
                if (value_feedback && value_feedback.name) {
                } else {
                  self.dialog_box();
                }
              }
            );
          }
        }
      );
    }
    dialog_box() {
      this.dialog = new frappe.ui.Dialog({
        title: __("Have a Great Day!"),
        fields: [
          {
            fieldtype: "Small Text",
            label: __("What are you most looking forward to today?"),
            fieldname: "lookingForward",
            in_list_view: 1,
            reqd: 1
          },
          {
            fieldtype: "Column Break"
          },
          {
            fieldtype: "Small Text",
            label: __("What challenge will you tackle today?"),
            fieldname: "todaysChallenge",
            in_list_view: 1,
            reqd: 1,
            default: ""
          }
        ],
        primary_action_label: __("Save"),
        primary_action: (values) => {
          this.submit(values);
          this.dialog.hide();
        }
      });
      this.dialog.$wrapper.find(".modal-dialog").css("max-width", "500px");
      this.dialog.show();
    }
    submit(values) {
      this.createRecord(values.lookingForward, values.todaysChallenge);
      this.dialog.hide();
    }
    createRecord(lookingForward, todaysChallenge) {
      var self = this;
      frappe.call({
        method: "phamos.phamos.doctype.have_a_great_day.have_a_great_day.create_todays_feedback",
        args: {
          lookingForward,
          todaysChallenge
        },
        callback: function(response) {
          frappe.msgprint(__("Feedback submitted successfully!"));
        }
      });
    }
  };
  $(document).on("app_ready", function() {
    new MorningFeedbackDialog();
  });
})();
//# sourceMappingURL=phamos.bundle.5A3QDGNE.js.map
