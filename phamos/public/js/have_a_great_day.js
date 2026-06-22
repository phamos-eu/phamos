class MorningFeedbackDialog {
  constructor() {
    this.dialog = null;
    this.pendingBirthdays = [];
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
      method:
        "phamos.phamos.doctype.have_a_great_day.have_a_great_day.get_user_time",
      args: { user: frappe.session.user },
      callback: function (response) {
        if (response.message) {
          var userTimeStr = response.message.user_time_str || "00:00:00";
          var fromTimeStr = response.message.from_time || "00:00:00";
          var tillTimeStr = response.message.till_time || "23:59:59";
          var enable_feedback_dialog = response.message.enable_feedback_dialog;

          var userTimeSeconds = timeToSeconds(userTimeStr);
          var fromTimeSeconds = timeToSeconds(fromTimeStr);
          var tillTimeSeconds = timeToSeconds(tillTimeStr);

          if (
            fromTimeSeconds <= userTimeSeconds &&
            userTimeSeconds <= tillTimeSeconds &&
            enable_feedback_dialog == 1
          ) {
            self.showFeedbackDialog();
          }
        } else {
          console.error("Failed to fetch user time.");
        }
      },
      error: function (error) {
        console.error("Error:", error);
      },
    });
  }

  showFeedbackDialog() {
    var self = this;

    frappe.call({
      method:
        "phamos.phamos.doctype.birthday_wish.birthday_wish.get_pending_birthday_wish_prompts",
      callback: function (response) {
        self.pendingBirthdays = response.message || [];
        if (!Array.isArray(self.pendingBirthdays)) {
          self.pendingBirthdays = [];
        }
        self._checkAndOpenDailyDialog();
      },
      error: function (error) {
        console.error("Birthday wish prompts failed:", error);
        self.pendingBirthdays = [];
        self._checkAndOpenDailyDialog();
      },
    });
  }

  _checkAndOpenDailyDialog() {
    var self = this;
    var today_date = frappe.datetime.nowdate();

    function openDailyDialog() {
      frappe.db.get_value(
        "Have a Great Day",
        {
          user: frappe.session.user,
          creation_date: today_date,
        },
        "name",
        function (value_feedback) {
          if (!value_feedback || !value_feedback.name) {
            self.dialog_box();
          } else if (self.pendingBirthdays.length) {
            self.birthday_wishes_dialog();
          }
        }
      );
    }

    function openBirthdayOnlyIfNeeded() {
      if (self.pendingBirthdays.length) {
        self.birthday_wishes_dialog();
      }
    }

    frappe.db.get_value(
      "phamos Settings",
      {},
      "is_employee_feedback",
      function (value) {
        if (value && value.is_employee_feedback == 1) {
          frappe.db.get_value(
            "Employee",
            { user_id: frappe.session.user },
            "name",
            function (value_user) {
              if (value_user && value_user.name) {
                openDailyDialog();
              } else {
                openBirthdayOnlyIfNeeded();
              }
            }
          );
        } else {
          openDailyDialog();
        }
      }
    );
  }

  _getDailyDialogFields() {
    return [
      {
        fieldtype: "Small Text",
        label: __("What are you most looking forward to today?"),
        fieldname: "lookingForward",
        reqd: 1,
      },
      {
        fieldtype: "Column Break",
      },
      {
        fieldtype: "Small Text",
        label: __("What challenge will you tackle today?"),
        fieldname: "todaysChallenge",
        reqd: 1,
      },
    ];
  }

  _buildDialogFields() {
    var fields = this._getDailyDialogFields();

    if (this.pendingBirthdays.length) {
      fields.push({
        fieldtype: "Section Break",
        fieldname: "birthday_wishes_section",
        label: __("Birthday wishes for colleagues"),
      });
      fields = fields.concat(this._getBirthdayWishFields());
    }

    return fields;
  }

  dialog_box() {
    var self = this;

    this.dialog = new frappe.ui.Dialog({
      title: __("Have a Great Day!"),
      fields: this._buildDialogFields(),
      primary_action_label: __("Save"),
      primary_action: function (values) {
        self.submitDailyFeedback(values);
      },
    });

    this._styleDialog(this.dialog, this.pendingBirthdays.length > 0);
    this.dialog.show();
  }

  birthday_wishes_dialog() {
    if (!this.pendingBirthdays.length) {
      return;
    }

    var self = this;
    this.dialog = new frappe.ui.Dialog({
      title: __("Birthday wishes"),
      fields: this._getBirthdayDialogFields(),
      primary_action_label: __("Save wishes"),
      primary_action: function (values) {
        self.submitBirthdayWishes(values, function () {
          self.dialog.hide();
          frappe.show_alert({
            message: __("Birthday wishes saved."),
            indicator: "green",
          });
        });
      },
    });

    this._styleDialog(this.dialog, true);
    this.dialog.show();
  }

  _getBirthdayWishFieldname(item, index) {
    if (this.pendingBirthdays.length === 1) {
      return "addBirthdayWishes";
    }
    return "addBirthdayWishes_" + item.birthday_employee;
  }

  _getBirthdayWishMessage(values, item, index) {
    var fieldname = this._getBirthdayWishFieldname(item, index);
    return values[fieldname];
  }

  _getBirthdayDialogFields() {
    if (!this.pendingBirthdays.length) {
      return [];
    }

    return [
      {
        fieldtype: "Section Break",
        fieldname: "birthday_wishes_section",
        label: __("Birthday wishes for colleagues"),
      },
    ].concat(this._getBirthdayWishFields());
  }

  _getBirthdayWishFields() {
    var self = this;
    var fields = [];

    this.pendingBirthdays.forEach(function (item, index) {
      var birthdayLabel = frappe.datetime.str_to_user(item.birthday_date);
      var dueLabel = frappe.datetime.str_to_user(item.due_date);
      var fieldname = self._getBirthdayWishFieldname(item, index);

      fields.push({
        fieldtype: "HTML",
        fieldname: "birthday_intro_" + index,
        options:
          "<p class='text-muted small'>" +
          __(
            "<strong>{0}</strong>'s birthday is in {1} days ({2}). Please add your message by <strong>{3}</strong>.",
            [item.employee_name, item.days_until, birthdayLabel, dueLabel]
          ) +
          "</p>",
      });

      fields.push({
        fieldtype: "Small Text",
        label: __("Add birthday wishes for {0}", [item.employee_name]),
        fieldname: fieldname,
        reqd: 0,
        description: __(
          "We collect these messages to wish your colleagues on their special day. Your note will be included in the team birthday post in Raven."
        ),
      });

      if (index < self.pendingBirthdays.length - 1) {
        fields.push({
          fieldtype: "Section Break",
          fieldname: "birthday_wish_break_" + index,
        });
      }
    });

    return fields;
  }

  _styleDialog(dialog, hasBirthdaySection) {
    dialog.$wrapper.find(".modal-dialog").css({
      "max-width": hasBirthdaySection ? "720px" : "680px",
      width: hasBirthdaySection ? "720px" : "680px",
    });
    dialog.$wrapper.find(".modal-body").css({
      "max-height": "80vh",
      "overflow-y": "auto",
    });
  }

  submitDailyFeedback(values) {
    var self = this;

    frappe.call({
      method:
        "phamos.phamos.doctype.have_a_great_day.have_a_great_day.create_todays_feedback",
      args: {
        lookingForward: values.lookingForward,
        todaysChallenge: values.todaysChallenge,
      },
      callback: function () {
        self.dialog.hide();

        if (self.pendingBirthdays.length) {
          self.submitBirthdayWishes(values, function () {
            frappe.show_alert({
              message: __("Feedback and birthday wishes saved."),
              indicator: "green",
            });
          });
        } else {
          frappe.show_alert({
            message: __("Feedback submitted successfully!"),
            indicator: "green",
          });
        }
      },
    });
  }

  submitBirthdayWishes(values, onComplete) {
    if (!this.pendingBirthdays.length) {
      if (onComplete) {
        onComplete();
      }
      return;
    }

    var self = this;
    var queue = this.pendingBirthdays.slice();
    var index = 0;

    function saveNext() {
      if (!queue.length) {
        if (onComplete) {
          onComplete();
        }
        return;
      }

      var item = queue.shift();
      var message = self._getBirthdayWishMessage(values, item, index);
      index += 1;

      if (!message || !message.trim()) {
        saveNext();
        return;
      }

      frappe.call({
        method:
          "phamos.phamos.doctype.birthday_wish.birthday_wish.save_birthday_wish_message",
        args: {
          birthday_wish: item.birthday_wish,
          message: message.trim(),
        },
        callback: function () {
          saveNext();
        },
        error: function () {
          saveNext();
        },
      });
    }

    saveNext();
  }
}

$(document).on("app_ready", function () {
  new MorningFeedbackDialog();
});
