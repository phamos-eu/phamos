function parse_duration_to_seconds(input) {
  if (!input || typeof input !== "string") return null;
  const str = input.trim();
  if (!str) return null;

  // Normalize full-width separator to ASCII
  const normalized = str.replace(/\uFF0E/g, ".").replace(/\uFF0C/g, ",");

  // Split by separator
  const hasDotOrComma = /[.,]/.test(normalized) && !normalized.includes(":");
  const rawParts = hasDotOrComma ? normalized.split(/[.,]/) : normalized.split(":");
  const parts = rawParts.map((p) => parseInt(String(p).trim(), 10));

  if (parts.some((n) => isNaN(n))) return null;

  // Only hours, minutes and seconds
  const SEC_PER_MIN = 60;
  const SEC_PER_HOUR = 3600;
  const MAX_SECONDS = 23 * SEC_PER_HOUR + 59 * SEC_PER_MIN + 59;

  let seconds;
  switch (parts.length) {
    case 1:
      seconds = parts[0] * SEC_PER_MIN;
      break;
    case 2:
      seconds = parts[0] * SEC_PER_HOUR + parts[1] * SEC_PER_MIN;
      break;
    case 3:
      seconds = parts[0] * SEC_PER_HOUR + parts[1] * SEC_PER_MIN + parts[2];
      break;
    default:
      return null;
  }
  return Math.min(seconds, MAX_SECONDS);
}

frappe.pages["project-action-panel"].on_page_load = function (wrapper) {
  // Ensure wrapper is defined
  if (!wrapper) {
    return;
  }

  // Set the title of the page
  if (wrapper.page) {
    wrapper.page.set_title(
      '<span style="font-size: 14px;">Project Action Panel</span>'
    );
  }

  function render_datatable() {
    frappe.call({
      method:
        "phamos.phamos.page.project_action_panel.project_action_panel.fetch_projects",
      callback: function (r) {
        if (r.message) {
          // Render DataTable with the fetched data
          renderDataTable(wrapper, r.message);
          //console.log(window.location.href)
        } else {
          // Handle error or empty data
        }
      },
    });
  }
 
  // Fetch project data from the server on page load
  render_datatable();

  // Function to create timesheet record
  function create_timesheet_record(
    project_name,
    task,
    customer,
    from_time,
    expected_time,
    goal
  ) {
    frappe.call({
      method:
        "phamos.phamos.page.project_action_panel.project_action_panel.create_timesheet_record",
      args: {
        project_name: project_name,
        task:task,
        customer: customer,
        from_time: from_time,
        expected_time: expected_time,
        goal: goal,
      },
      freeze: true,
      freeze_message: __("Creating Timesheet Record......"),
      callback: function (r) {
        if (r.message) {
          let doc = frappe.model.sync(r.message);
          frappe.show_alert(
            "Timesheet Record: " + doc[0].name + " Created Successfully."
          );
          render_datatable();
        }
      },
    });
  }

function update_and_submit_timesheet_record(
  timesheet_record,
  task,
  to_time,
  percent_billable,
  activity_type,
  result,
  productivity
) {
  frappe.call({
    method: "frappe.client.get",
    args: {
      doctype: "Timesheet Record",
      name: timesheet_record
    },
    callback: function (res) {
      if (!res.message) {
        frappe.show_alert("Timesheet Record not found.");
        return;
      }

      let doc = res.message;

      if (!doc.item || doc.item.length === 0) {
        frappe.show_alert("No time logs found.");
        return;
      }

      let lastRow = doc.item[doc.item.length - 1];

      if (lastRow.to_time) {
        frappe.show_alert("Please Pause it first (▶️)");
        return;
      }

      frappe.call({
        method: "phamos.phamos.page.project_action_panel.project_action_panel.update_and_submit_timesheet_record",
        args: {
          name: timesheet_record,
          task: task,
          to_time: to_time,
          percent_billable: percent_billable,
          activity_type: activity_type,
          result: result,
          productivity: productivity
        },
        freeze: true,
        freeze_message: __("Updating Timesheet Record......"),
        callback: function (r) {
          if (r.message) {
            let timesheet_name = r.message.timesheet_name;
            frappe.show_alert({
              message: `Timesheet <a href="${frappe.utils.get_form_link("Timesheet-Record", timesheet_name)}" target="_blank">${timesheet_name}</a> Updated Successfully.`,
              indicator: 'green'
            });            
          render_datatable();
          }
        },
      });
    }
  });
}

 window.toggleDropdown = function (event, dropdownId) {
  event.stopPropagation(); // Prevent click from bubbling

  const dropdown = document.getElementById(dropdownId);
  const button = event.currentTarget;

  if (!dropdown) {
    console.error(`Dropdown with ID ${dropdownId} not found`);
    return;
  }

  // Close other custom dropdowns only (not global Frappe dropdowns)
  document.querySelectorAll('.custom-dropdown .dropdown-menu').forEach((menu) => {
    if (menu !== dropdown) {
      menu.style.display = 'none';
    }
  });

  // Toggle the dropdown visibility
  const isVisible = dropdown.style.display === 'block';
  dropdown.style.display = isVisible ? 'none' : 'block';

  if (!isVisible) {
    // Wait for dropdown to render before measuring
    setTimeout(() => {
      const buttonRect = button.getBoundingClientRect();
      const dropdownHeight = dropdown.offsetHeight || 100;

      // Instead of window.innerHeight, get the nearest scrollable parent height
      let scrollContainer = button.closest(".datatable") || document.documentElement;
      const containerRect = scrollContainer.getBoundingClientRect();

      const spaceBelow = containerRect.bottom - buttonRect.bottom;
      const spaceAbove = buttonRect.top - containerRect.top;

      dropdown.style.position = 'absolute';
      dropdown.style.left = '0px';

      if (spaceBelow < dropdownHeight && spaceAbove > dropdownHeight) {
        // Open upward
        dropdown.style.top = `-${dropdownHeight + 5}px`;
      } else {
        // Open downward (default)
        dropdown.style.top = `${button.offsetHeight + 5}px`;
      }
    }, 0);
  }
};

  // Close custom dropdowns when clicking outside (only on this page)
  document.addEventListener('click', (e) => {
    // Only close dropdowns that are part of the custom-dropdown component
    document.querySelectorAll('.custom-dropdown .dropdown-menu').forEach((menu) => {
      // Check if the click was outside this dropdown
      const dropdown = menu.closest('.custom-dropdown');
      if (dropdown && !dropdown.contains(e.target)) {
        menu.style.display = 'none';
      }
    });
  });
  

  window.handleCustomerClick = function (customer_name) {
    // Get the base URL of the current page
    let baseUrl = window.location.href.split("/").slice(0, 3).join("/"); // Extract protocol, hostname, and port

    // Construct the URL for the customer details page
    let url = `${baseUrl}/app/customer/${encodeURIComponent(customer_name)}`;

    // Open the URL in a new window
    window.open(url);

    // Optionally, return false to prevent the default link behavior (not necessary in this case)
    return false;
  };


  window.handleProjectClick = function (project_name) {
    // Get the base URL of the current page
    let baseUrl = window.location.href.split("/").slice(0, 3).join("/"); // Extract protocol, hostname, and port

    // Construct the URL for the project details page
    let url = `${baseUrl}/app/project/${encodeURIComponent(project_name)}`;

    // Open the URL in a new window
    window.open(url);

    // Optionally, return false to prevent the default link behavior (not necessary in this case)
    return false;
  };


  window.handleTimesheetClick = function (timesheet) {
    // Get the base URL of the current page
    let baseUrl = window.location.href.split("/").slice(0, 3).join("/"); // Extract protocol, hostname, and port

    // Construct the URL for the customer details page
    let url = `${baseUrl}/app/timesheet-record/${encodeURIComponent(
      timesheet
    )}`;

    // Open the URL in a new window
    window.open(url);

    // Optionally, return false to prevent the default link behavior (not necessary in this case)
    return false;
  };


  window.stopProject = function (timesheet_record, percent_billable, project, task, task_in_timesheet_record) {

  // Fetch Timesheet Record
  frappe.call({
    method: "frappe.client.get",
    args: {
      doctype: "Timesheet Record",
      name: timesheet_record
    },
    callback: function (res) {
      if (!res.message) {
        frappe.show_alert("Timesheet Record not found.");
        return;
      }

      let doc = res.message;

      // Check: Child table 'item' exists
      if (!doc.item || doc.item.length === 0) {
        frappe.show_alert("No time logs found.");
        return;
      }

      let items = doc.item || [];
      let rowCount = items.length;
      let lastRow = items[rowCount - 1];

      // Even row count means timer is paused (not running)
      if (rowCount % 2 === 0) {
        frappe.show_alert({
          message: "⏸️ Please Pause it first (▶️)",
          indicator: "orange"
        });
        return;
      }

      // Get the minimum valid to_time (current row's from_time)
      let min_to_time = lastRow.from_time || null;
      openStopProjectDialog(timesheet_record, percent_billable, project, task, task_in_timesheet_record, min_to_time);
    }
  });
};

// Separate function for dialog
function openStopProjectDialog(timesheet_record, percent_billable, project, task, task_in_timesheet_record, min_to_time) {
  let from_time = '';
  let expected_time = '';
  let timesheet_record_info = " Info from timesheet record";


  frappe.db.get_value("Timesheet Record", { name: timesheet_record }, ["goal", "from_time"], function (value) {

    from_time_formatted = frappe.datetime.str_to_user(value.from_time);
    timesheet_record_info = "From time: " + from_time_formatted + ",<br>Goal is: " + value.goal;

    frappe.db.get_value("Employee", { user_id: frappe.session.user }, "activity_type", function (value) {

      let task_field_properties = {
        fieldtype: "Link",
        options: "Task",
        label: __("Task"),
        fieldname: "task",
        in_list_view: 1,
        read_only: 0,
        default: task,
        description: "Please consult the Project Manager if unsure which task to choose.",
        get_query: function () {
          if (project) {
            return { filters: { project: project } };
          } else {
            return {};
          }
        }
      };

      if (task_in_timesheet_record === "Task is hidden") {
        task_field_properties.hidden = 1;
      } else if (task_in_timesheet_record === "Task is optional") {
        task_field_properties.reqd = 0;
      } else if (task_in_timesheet_record === "Task is mandatory") {
        task_field_properties.reqd = 1;
      }

      let dialog = new frappe.ui.Dialog({
        title: __("Mark Complete Timesheet record."),
        fields: [
          {
            fieldtype: "Data",
            label: __("Timesheet Record"),
            fieldname: "timesheet_record",
            read_only: 1,
            default: timesheet_record,
          },
          task_field_properties,
          {
            fieldtype: "Small Text",
            label: __("Timesheet Record Info"),
            fieldname: "timesheet_record_info",
            read_only: 1,
            default: timesheet_record_info,
          },
          { fieldtype: "Column Break" },
          {
            label: "What I did ",
            fieldname: "result",
            fieldtype: "Small Text",
            reqd: 1,
            description:
                    "⚠️ This information is sent to the customer next day. Please make sure to wright meaningful text. Adding Issues ID's and or URL is helpful.",

          },
          { fieldtype: "Column Break" },
          {
            fieldtype: "Link",
            options: "Activity Type",
            label: __("Activity Type"),
            fieldname: "activity_type",
            reqd: 1,
            default: value.activity_type,
             description:
                    'The "Activity Type" allows for categorizing tasks into specific types, such as planning, execution, communication, and proposal writing, streamlining task management and organization within the system.',
          },
          { fieldtype: "Column Break" },
          {
            label: "Time",
            fieldname: "to_time",
            fieldtype: "Datetime",
            reqd: 1,
            default: (function() {
              // Get current server time
              var current = frappe.datetime.system_datetime();
              // Ensure it's not earlier than the row's from_time
              if (min_to_time && frappe.datetime.get_diff(current, min_to_time) < 0) {
                return min_to_time;
              }
              return current;
            })(),
            description: "Time updates live. Edit manually to stop auto-update.",
          },
          {
            fieldtype: "Select",
            options: [0, 25, 50, 75, 100],
            label: __("Percent Billable"),
            fieldname: "percent_billable",
            reqd: 1,
            default: percent_billable,
            description:
                    "This is a personal indicator to your own performance on the work you have done. It will influence the billable time of the Timesheet created.",

          },
          {
            fieldtype: "Select",
            options: [0, 25, 50, 75, 100],
            label: __("Productivity (%)"),
            fieldname: "productivity",
            reqd: 0,
            default: 100,
            description: "This field is used to indicate your productivity level on internal (non-billable) project work. It helps measure performance and effort for internal activities.",
          },
        ],
        primary_action_label: __("Update Timesheet Record."),
        primary_action(values) {
          // Use actual_to_time if available (from auto-updater), otherwise use form value
          // This prevents the datetime field from stripping seconds
          let final_to_time = actual_to_time || values.to_time;

          // Validate using Date comparison for better precision
          if (min_to_time) {
            let to_date = frappe.datetime.str_to_obj(final_to_time);
            let min_date = frappe.datetime.str_to_obj(min_to_time);

            if (to_date < min_date) {
              final_to_time = min_to_time;
            }
          }

          update_and_submit_timesheet_record(
            values.timesheet_record,
            values.task,
            final_to_time,
            values.percent_billable,
            values.activity_type,
            values.result,
            values.productivity
          );
          dialog.hide();
        }
      });

      // Hide productivity by default; it replaces percent_billable for internal projects
      dialog.set_df_property("productivity", "hidden", 1);
      dialog.set_df_property("productivity", "reqd", 0);

      dialog.$wrapper.find(".modal-dialog").css("max-width", "800px");
      dialog.show();

      if (project) {
        frappe.db.get_value("Project", project, ["custom_is_internal_project"], function(r) {
          let is_internal = r && r.custom_is_internal_project === 1;
          // Internal: hide Percent Billable, show Productivity
          // Non-internal: show Percent Billable, hide Productivity
          dialog.set_df_property("percent_billable", "hidden", is_internal ? 1 : 0);
          dialog.set_df_property("percent_billable", "reqd",   is_internal ? 0 : 1);
          dialog.set_df_property("productivity",     "hidden", is_internal ? 0 : 1);
          dialog.set_df_property("productivity",     "reqd",   is_internal ? 1 : 0);
          if (is_internal) {
            dialog.set_value("productivity", 100);
          }
        });
      }

      // Implement live time update for to_time field
      var time_update_interval = null;
      var user_interacted = false;
      // Store the actual full datetime with seconds (initialize with current or min)
      var actual_to_time = min_to_time && frappe.datetime.get_diff(frappe.datetime.system_datetime(), min_to_time) < 0
        ? min_to_time
        : frappe.datetime.system_datetime();
      
      setTimeout(function() {
        var to_time_field = dialog.fields_dict.to_time;
        
        if (to_time_field && to_time_field.$input && to_time_field.$input.length > 0) {
          // Mark as user-interacted on focus or manual typing
          to_time_field.$input.on('focus mousedown keydown', function() {
            if (!user_interacted) {
              user_interacted = true;
              actual_to_time = null;
              if (time_update_interval) {
                clearInterval(time_update_interval);
                time_update_interval = null;
              }
            }
          });
          
          // Function to update the time field
          var update_time = function() {
            if (!user_interacted) {
              // Get current time from server (in system timezone)
              var current_time = frappe.datetime.system_datetime();
              
              // Ensure it's not earlier than the row's from_time
              if (min_to_time && frappe.datetime.get_diff(current_time, min_to_time) < 0) {
                current_time = min_to_time;
              }
              
              // Store the actual full datetime
              actual_to_time = current_time;
              
              // Update field using multiple approaches to ensure sync
              to_time_field.$input.val(current_time);
              
              try {
                dialog.set_value('to_time', current_time);
              } catch(e) {}
              
              if (to_time_field.set_model_value) {
                to_time_field.set_model_value(current_time);
              }
            }
          };
          
          // Sync to system clock - wait until next full second
          var now = new Date();
          var ms_until_next_second = 1000 - now.getMilliseconds();
          
          setTimeout(function() {
            // Update immediately at the second boundary
            update_time();
            
            // Then continue updating every second, now synced
            time_update_interval = setInterval(update_time, 1000);
          }, ms_until_next_second);
        }
      }, 500);
      
      // Cleanup interval when dialog closes
      var original_hide = dialog.hide;
      dialog.hide = function() {
        if (time_update_interval) {
          clearInterval(time_update_interval);
          time_update_interval = null;
        }
        original_hide.call(this);
      };
    });
  });
}

  //return record.timesheet_record_draft;

  window.selfAssignProject = function(project_name){
    frappe.call({
      method:"phamos.phamos.page.project_action_panel.project_action_panel.self_assign_project",
      args:{
        project_name :project_name
      },
      callback:function(r){
        if(r.message){
          frappe.show_alert({
            title:__("Success"),
            message:__("Project Assigned Successfully."),
            indicator:"green"
          });
          render_datatable() 
        }
      },
      error:function(err){
        frappe.show_alert({
          title:__("Error"),
          message:__("Failed to assign project. Please Check the error logs."),
          indicator:"red"
        });
      }
    })
  }

  window.assignProject = function(project_name) {
    // Instantiate AssignToDialog if not already done
    let assign_to = new frappe.ui.form.AssignToDialog({
        method: "frappe.desk.form.assign_to.add", // Method for assignment
        doctype: "Project", // The doctype of the document being assigned
        docname: project_name, // The document name to be assigned
        callback: function (r) {
            // Handle the response from the assignment action
            if (r.message) {
                // You can add logic here to update the UI or provide user feedback
                frappe.show_alert({
                    message: __('Users assigned successfully!'),
                    indicator: 'green'
                });
                render_datatable() 
            }
        },
    });

    // Ensure the dialog is ready to show
    if (assign_to.dialog) {
        // Check if the show method exists
        if (typeof assign_to.dialog.show === 'function') {
            assign_to.dialog.show(); // Show the dialog
        } else {
            console.error("Error: show() method is not available on assign_to.dialog");
        }
    } else {
        console.error("Error: AssignToDialog was not instantiated correctly.");
    }
  };


  window.startProject = function (project_name, customer,project,task_in_timesheet_record) {
    frappe.call({
      method:
        "phamos.phamos.page.project_action_panel.project_action_panel.check_draft_timesheet_record",
      callback: function (r) {
        if (r.message) {
          let timesheetRecordDrafts = r.message;
          let doc = frappe.model.sync(r.message);
          let draftTimesheets = timesheetRecordDrafts
            .map(function (record) {
              return `<a href="https://phamos.eu/app/timesheet-record/${record.timesheet_record_draft}" target="_blank">${record.timesheet_record_draft}</a>`;
            })
            .join(", ");
          {
            let task_field_properties = {
              fieldtype: "Link",
              options: "Task",
              label: __("Task"),
              fieldname: "task",
              in_list_view: 1,
              read_only: 0,
              description:"Please consult the Project Manager if unsure which task to choose.",
              get_query: function () {
                if (project) {
                  return {
                    filters: {
                      project: project
                    }
                  };
                } else {
                  return {};
                }
              }
            };

            // Modify visibility/requirement of the task field based on task_in_timesheet_record value
          if (task_in_timesheet_record === "Task is hidden") {
            task_field_properties.hidden = 1; // Hide the field
          } else if (task_in_timesheet_record === "Task is optional") {
            task_field_properties.reqd = 0; // Make it optional (non-mandatory)
            task_field_properties.description = "Please consult the Project Manager if unsure which task to choose."
          } else if (task_in_timesheet_record === "Task is mandatory") {
            task_field_properties.reqd = 1; // Make it mandatory
            task_field_properties.description = "Please consult the Project Manager if unsure which Task to choose."
          }
            var dialog = new frappe.ui.Dialog({
              title: __("Add Timesheet record."),
              fields: [
                {
                  fieldtype: "Data",
                  options: "Project",
                  label: __("Project Name"),
                  fieldname: "project_name",
                  in_list_view: 1,
                  read_only: 1,
                  default: project_name,
                },
                task_field_properties,
                {
                  fieldtype: "Data",
                  options: "Customer",
                  label: __("Customer"),
                  fieldname: "customer",
                  in_list_view: 1,
                  read_only: 1,
                  default: customer,
                },
                {
                  fieldtype: "Data",
                  label: __("Expected Time (quick input)"),
                  fieldname: "expected_time_quick",
                  description: __("Type the expected duration as minutes (20) or as hours and minutes (1:20, 1.20, or 1,20) or as hours, minutes, and seconds (1:20:30) and it will auto-fill Expected Time."),
                  in_list_view: 1,
                  reqd: 1,
                },
                {
                  fieldtype: "Duration",
                  label: __("Expected Time"),
                  fieldname: "expected_time",
                  in_list_view: 1,
                  reqd: 1,
                  read_only: 1,
                },
                {
                  fieldtype: "Column Break",
                },
                {
                  fieldtype: "Datetime",
                  label: __("From Time"),
                  fieldname: "from_time",
                  in_list_view: 1,
                  reqd: 1,
                  read_only: 0,
                  description: "Auto-filled with current time. Adjust if needed.",
                },
                { 
                  fieldtype: "Small Text",
                  label: __("Goal"),
                  fieldname: "goal",
                  in_list_view: 1,
                  reqd: 1,
                  description:
                    "⚠️ User need to manifest on what you are working and going to do. This will be shared with the customer next day.",
                },
              ],
              primary_action_label: __("Create Timesheet Record."),
              primary_action(values) {
                create_timesheet_record(
                  values.project_name,
                  values.task,
                  values.customer,
                  values.from_time,
                  values.expected_time,
                  values.goal
                );
                dialog.hide();
              },
            });

            // Set the width using CSS
            dialog.$wrapper.find(".modal-dialog").css("max-width", "800px");
            dialog.show();

            setTimeout(function() {
              var field = dialog.fields_dict.from_time;
              if (field && field.datepicker) {
                field.datepicker.selectDate(frappe.datetime.now_datetime(true));
              }
            }, 0);

            setTimeout(function () {
              const $quick = dialog.$wrapper.find('[data-fieldname="expected_time_quick"]').find("input");
              if ($quick.length) {
                $quick.on("input change", function () {
                  const val = $(this).val();
                  if (!val || !val.trim()) {
                    dialog.set_value("expected_time", 0);
                  } else {
                    const seconds = parse_duration_to_seconds(val);
                    if (seconds !== null && seconds >= 0) {
                      dialog.set_value("expected_time", seconds);
                    }
                  }
                });
              }
            }, 0);

          }
        } else {
          frappe.show_alert(__("No response from server. Please try again."));
        }
      },
    });
  };

  // Function to render number cards
  function render_cards(wrapper, card_names, tab='') {
    return frappe.call({
      method: "phamos.phamos.page.project_action_panel.project_action_panel.get_permitted_cards",
      args: { 
        dashboard_name: "Project Management",
      },
      callback: function (response) {
        var cards = response.message;
        if (!cards || !cards.length) {
          return;
        }
    
        // Filter the cards based on card_names
        var filtered_cards = cards.filter(function(card) {
          return card_names.includes(card.card);
        });
    
        var number_cards = filtered_cards.map(function (card) {
          return {
            name: card.card,
          };
        });
    
        // Create a widget group for number cards
        var number_card_group = new frappe.widget.WidgetGroup({
          container: wrapper, 
          type: "number_card",
          columns: 3,
          options: {
            allow_sorting: false,
            allow_create: false,
            allow_delete: false,
            allow_hiding: false,
            allow_edit: false,
          },
          widgets: number_cards,
        });
    
        // Style the number card widgets
        $(wrapper).find(".widget.number-widget-box").css({
          width: "250px", 
        });
    
        $(wrapper).find(".widget-group-body.grid-col-3").css({
          display: "flex", 
          "flex-wrap": "nowrap", 
        });
    
        // Custom widget logic to dynamically inject data
        let widgetGroupBody = $(wrapper).find(".widget-group-body");
        widgetGroupBody.empty(); // Clear existing widgets before appending new ones
    
        // Fetch data for the cards using API calls
        let fetch_projects = "phamos.phamos.page.project_action_panel.project_action_panel.get_project_count"
        if(tab == "All Projects"){
          fetch_projects = "phamos.phamos.page.project_action_panel.project_action_panel.get_project_count_all"
        }
        Promise.all([
          frappe.call({ method:  fetch_projects}),
          frappe.call({ method: "phamos.phamos.page.project_action_panel.project_action_panel.total_hours_worked_today" }),
          frappe.call({ method: "phamos.phamos.page.project_action_panel.project_action_panel.total_hours_worked_in_this_week" }),
          frappe.call({ method: "phamos.phamos.page.project_action_panel.project_action_panel.total_hours_worked_in_this_month" })
        ])
        .then(function (results) {
          // Assuming the results are in the same order as the requests
          const [projectCountResult, totalTodayResult, totalWeekResult, totalMonthResult] = results;
          
          // Handle the result for each card type
          let projectCount = projectCountResult.message;
          let monthly_working = totalMonthResult.message;
          let weekly_working = totalWeekResult.message;
          let today_working = totalTodayResult.message;

          
          // Add custom widgets to the page based on the fetched data
          let customCards = [
            { name: "Total Projects", labels: ["Projects"], values: [projectCount.value || 0] },
            { name: "Total Hours Worked Today", labels: ["Working", "Billable"], values: [today_working.value || 0, today_working.billable || 0] },
            { name: "Total Hours Worked This Week", labels: ["Working", "Billable"], values: [weekly_working.value || 0, weekly_working.billable || 0]},
            { name: "Total Hours Worked This Month", labels: ["Working", "Billable"], values: [monthly_working.value || 0, monthly_working.billable || 0]}
          ];
  
          customCards.forEach(card => {
            let widgetTitle = card.name;
            let labels = card.labels;
            let values = card.values;
  
            let gradientStyle = "";
            let tooltip = "";

            if (
              widgetTitle === "Total Hours Worked Today" ||
              widgetTitle === "Total Hours Worked This Week" ||
              widgetTitle === "Total Hours Worked This Month"
            ) {
              let workingData =
                widgetTitle === "Total Hours Worked Today"
                  ? today_working
                  : widgetTitle === "Total Hours Worked This Week"
                  ? weekly_working
                  : monthly_working;

              const greenPercent = workingData.green || 0;
              const amberPercent = workingData.amber || 0;
              const redPercent = workingData.red || 0;

              const amberStop = greenPercent + amberPercent;
              const redStop = amberStop + redPercent;

                // If no records, make background white
                if (greenPercent === 0 && amberPercent === 0 && redPercent === 0) {
                  gradientStyle = `
                    background: white;
                    background-size: 100% 6px;
                    background-repeat: no-repeat;
                    background-position: bottom;
                    padding-bottom: 16px;
                  `;
                } else {
                  gradientStyle = `
                    background: linear-gradient(to right,
                      green 0%, green ${greenPercent}%,
                      orange ${greenPercent}%, orange ${amberStop}%,
                      red ${amberStop}%, red 100%);
                    background-size: 100% 6px;
                    background-repeat: no-repeat;
                    background-position: bottom;
                    padding-bottom: 16px;
                  `;
                }

              tooltip = `Green: ${greenPercent}% | Amber: ${amberPercent}% | Red: ${redPercent}%`;
            }

            let customWidgetHTML = `
              <div class="widget number-widget-box" style="width: 250px; padding: 12px; border-radius: 8px; border: 1px solid #ddd; background: white;">
                <div class="widget-head" style="display: flex; justify-content: space-between; align-items: center; font-size: 12px; font-weight: 600; color: #666;">
                  <span>${widgetTitle}</span>
                </div>
                <div class="widget-body" style="${gradientStyle}" title="${tooltip}">
                  <div class="widget-content" style="padding-top:0px !important">
                    <div style="display: flex; justify-content: space-between; font-size: 12px; font-weight: 600; color: #444; margin-top: 8px;">
                      <span>${labels[0]}</span>
                      ${labels[1] != undefined ? `<span>${labels[1]}</span>` : ''}
                    </div>
                    <div style="display: flex; justify-content: space-between; font-size: 18px; font-weight: bold; margin-top: 3px;">
                      <span class="text-dark">${values[0]}</span>
                      ${values[1] != undefined ? `<span class="text-dark">${values[1]}</span>` : ''}
                    </div>
                  </div>
                </div>
              </div>
            `;

  
            // Append the custom widget HTML to the widget group body
            widgetGroupBody.append(customWidgetHTML);
          });
        })
        .catch(function (error) {
          console.error("Error fetching data:", error);
        });
      },
    });
  }

  // Function to render DataTable with tabs
function renderDataTable(wrapper, projectData) {
 // Ensure wrapper is defined
    if (!wrapper) {
      return;
    }

    // Set the default active tab to 'Your Projects'
    wrapper.innerHTML = `
        <h2 style="display: inline; margin-left: 50px; margin-top: 10px; font-size:30px">
          Project Action Panel
          <!-- Info Icon -->
        </h2>
        <div class="form-tabs-list">
          <ul class="nav form-tabs" id="form-tabs" role="tablist">
            <li class="nav-item show">
              <!-- 'Your Projects' tab is the default active tab -->
              <a class="nav-link active" id="DAP-your-project-tab" role="tab" aria-controls="your-projects" aria-selected="true">
                  Your Projects
              </a>
            </li>
            <li class="nav-item show">
              <!-- 'All Projects' tab is inactive by default -->
              <a class="nav-link" id="DAP-all-project-tab" role="tab" aria-controls="all-projects" aria-selected="false">
                  All Projects
              </a>
            </li>
            <li class="nav-item show">
              <!-- 'MY Calender' tab is inactive by default -->
              <a class="nav-link" id="my-calender" role="tab" aria-controls="my-calender" aria-selected="false">
                  My Calender
              </a>
            </li>
            <li class="nav-item show">
              <!-- 'Team Calender' tab is inactive by default -->
              <a class="nav-link" id="team-calender" role="tab" aria-controls="team-calender" aria-selected="false">
                  Team Calender
              </a>
            </li>
          </ul>
        </div>
        <div id="content-wrapper" style="margin-top: 20px; margin-left: 30px;">
          <div id="card-wrapper"></div>
          <div id="datatable-wrapper"></div>
        </div>
      `;
// Add CSS for the hover-over box
    const tooltipStyle = document.createElement("style");
    tooltipStyle.innerHTML = `
    #info-icon {
      position: relative;
      cursor: pointer;
    }

    #info-icon:hover::after {
        content: "Label Descriptions:\\A blue Color = Planned Hrs(P)\\A Orange Color = Spent Draft Hrs(D)\\A Green Color = Spent Submitted Hrs(S)";
        white-space: pre-wrap;
        position: absolute;
        left: 50%;
        top: 100%;
        transform: translateX(-50%);
        padding: 15px;
        background-color: rgba(0, 0, 0, 0.8);
        color: white;
        border-radius: 5px;
        font-size: 12px;
        line-height: 1.5;
        z-index: 1000;
        box-shadow: 0 4px 6px rgba(0, 0, 0, 0.1);
        width: 250px;
      }
    `;
    document.head.appendChild(tooltipStyle);

    // Add the info icon with hover functionality
    const infoIcon = document.createElement("span");
    infoIcon.id = "info-icon";
    infoIcon.innerHTML = "ℹ️"; // Info icon text or HTML (e.g., an SVG or font icon)
    infoIcon.style.fontSize = "20px";
    infoIcon.style.marginLeft = "10px";

    // Append the info icon next to the title
    const header = document.querySelector("h2");
    header.appendChild(infoIcon);

    // Get references to the tabs
    const your_projectsTab = document.getElementById("DAP-your-project-tab");
    const all_projectsTab = document.getElementById("DAP-all-project-tab");
    const my_calenderTab = document.getElementById("my-calender");
    const team_calenderTab = document.getElementById("team-calender");


    // Event listener for the Your Projects tab
    your_projectsTab.addEventListener("click", () => {
      // Remove 'active' class from All Projects tab and set to Your Projects
      all_projectsTab.classList.remove("active");
      your_projectsTab.classList.add("active");
      team_calenderTab.classList.remove("active");
      my_calenderTab.classList.remove("active");


      // Set visual feedback for selection
      your_projectsTab.setAttribute("aria-selected", "true");
      all_projectsTab.setAttribute("aria-selected", "false");

    // Show content for the Your Projects tab
      show_tab("Your Projects", projectData);
    });
    // Event listener for the my calender tab
    my_calenderTab.addEventListener("click", () => {
        // Remove 'active' class from Your Projects tab and set to All Projects
        your_projectsTab.classList.remove("active");
        my_calenderTab.classList.add("active");
        team_calenderTab.classList.remove("active");
        all_projectsTab.classList.remove("active");
        // Show content for the my Calender tab
      show_tab("My Calender", projectData);
    });
    // Event listener for the team calender tab
    team_calenderTab.addEventListener("click", () => {
        // Remove 'active' class from Your Projects tab and set to All Projects
        your_projectsTab.classList.remove("active");
        team_calenderTab.classList.add("active");
        my_calenderTab.classList.remove("active");
        all_projectsTab.classList.remove("active");
        // Show content for the Team Calender tab
      show_tab("Team Calender", projectData);
    });

    // Event listener for the All Projects tab
    all_projectsTab.addEventListener("click", () => {
        // Remove 'active' class from Your Projects tab and set to All Projects
        your_projectsTab.classList.remove("active");
        all_projectsTab.classList.add("active");
        my_calenderTab.classList.remove("active");
        team_calenderTab.classList.remove("active");



        // Set visual feedback for selection
        all_projectsTab.setAttribute("aria-selected", "true");
        your_projectsTab.setAttribute("aria-selected", "false");

        // Show content for the All Projects tab
      show_tab("All Projects", projectData);
    });

  // Initial tab content setup: Show content for 'Your Projects' by default
  show_tab("Your Projects", projectData); // Set 'Your Projects' as default
}

// Show tab content based on the selected tab
function show_tab(tab, projectData) {
    const cardWrapper = document.getElementById("card-wrapper");
    const datatableWrapper = document.getElementById("datatable-wrapper");
    // Clear previous content of cardWrapper and datatableWrapper
    cardWrapper.innerHTML = "";  // This will ensure the number cards don't duplicate
    datatableWrapper.innerHTML = ""; // Clear previous DataTable content

    if (tab === "Your Projects") {
      // style inject (sirf table aur cards ke liye zaroori CSS)
      let style = document.createElement("style");
      style.innerHTML = `
        .dt-cell__content--col-14, .dt-cell__content--header-14 { display: none; width: 0; }
        .dt-cell__content--col-6, .dt-cell__content--header-6 { display: table-cell; }
        .dt-cell__content--col-9, .dt-cell__content--header-9 { display: table-cell;}
        .dt-cell__content--col-3, .dt-cell__content--header-3 { display: table-cell; }
      `;
      document.head.appendChild(style);

      // Render cards
      card_names = [
        "Your Total Projects", 
        "Total Hrs Worked Today", 
        "Total Hrs Worked This Week", 
        "Total Hrs Worked This Month"
      ];
      render_cards(cardWrapper, card_names);

      // LEFT: Projects table container
      const tableDiv = document.createElement("div");
      tableDiv.id = "datatable-inner";
      tableDiv.style.flex = "2"; 

      datatableWrapper.appendChild(tableDiv);

      // Render projects table
      renderProjectDataTable(tableDiv, projectData);

    }

    else if (tab === "All Projects") {
      let style = document.createElement("style");
      style.innerHTML = `
        /* unHide the "Name" column cells and header */
        .dt-cell__content--col-14, .dt-cell__content--header-14 { display: table-cell; }
        .dt-cell__content--col-6, .dt-cell__content--header-6 { display: table-cell; }
        .dt-cell__content--col-3, .dt-cell__content--header-3 { display: table-cell; }
        .dt-cell__content--col-9, .dt-cell__content--header-9 { display: table-cell; }

        /* 🌟 Add width to the scrollable DataTable only for All Projects */
        #datatable-wrapper .dt-scrollable {
            width: 1225px !important;
            max-width: 1225px !important;
            overflow: auto !important;
         }
        `;
      document.head.appendChild(style);

      // Define the cards to display
      card_names = ["Total Projects", "Total Hrs Worked Today", "Total Hrs Worked This Week", "Total Hrs Worked This Month"];
  
      // Render the cards immediately to improve perceived speed
      render_cards(cardWrapper, card_names, tab);

      // Make an API call to fetch all projects data asynchronously
        frappe.call({
          method: "phamos.phamos.page.project_action_panel.project_action_panel.fetch_all_projects",
          callback: function (r) {
            if (r.message) {
              // Render DataTable with the fetched data once API response is received
              renderProjectDataTable(datatableWrapper, r.message);
            } else {
              // Handle case with no data or error
              datatableWrapper.innerHTML = `<p>No projects found.</p>`;
            }
          },
          freeze: true,  // Optional: Add a freeze effect to indicate loading
          freeze_message: "Loading projects...",  // Custom loading message
        });
    }
    else if (tab === "My Calender") {
      // style inject (calendar styles)
      let style = document.createElement("style");
      style.innerHTML = `
        table.timezone-table {
          border-collapse: collapse;
          width: 100%;
          text-align: center;
          font-size: 12px;
          background: var(--bg-color, #fff);
          color: var(--text-color, #222);
        }
        table.timezone-table th,
        table.timezone-table td {
          border: 1px solid var(--border-color, #999);
          padding: 6px 4px 14px 4px;
          position: relative;
          vertical-align: top;
          height: 40px;
        }
        table.timezone-table th {
          background: var(--control-bg, #ddd);
          color: var(--text-color, #222);
        }

        table.timezone-table td::after {
          content: "";
          position: absolute;
          left: 0;
          right: 0;
          top: 50%;
          border-top: 1px dotted var(--border-color, #aaa);
          z-index: 0;
        }

        table.timezone-table td span {
          position: relative;
          z-index: 1;
          background: var(--bg-light, #f9f9f9);
          color: var(--text-color, #222);
          padding: 2px 4px;
        }

        /* Timesheet record box */
        .timesheet-box {
          border-radius: 4px;
          font-size: 11px;
          padding: 4px;
          text-align: center;
          position: absolute;
          left: 10px;
          right: 10px;
          overflow: hidden;
          color: var(--text-color, #222);
        }

        /* parent container for calendar + records */
        .calendar-wrapper {
          flex-direction: row;
          border: 1px solid var(--border-color, #ccc);
          border-radius: 8px;
          overflow: hidden;
          background: var(--bg-color, #181c32);
        }
        .calendar-left {
          flex: 1;
          border-right: 1px solid var(--border-color, #ccc);
        }
        .calendar-right {
          flex: 1;
          padding: 10px;
          background: var(--bg-color, #fff);
          color: var(--text-color, #222);
          position: relative;
        }
        .calendar-right::before {
          content: "";
          position: absolute;
          top: 0;
          left: 0;
          right: 0;
          bottom: 0;
          background: repeating-linear-gradient(
            to bottom,
            transparent,
            transparent 39px,
            var(--border-color, #ddd) 40px
          );
          pointer-events: none;
        }
      `;
      document.head.appendChild(style);

      // Container for calendar
      const calendarWrapper = document.createElement("div");
      calendarWrapper.className = "calendar-wrapper";
      calendarWrapper.style.flex = "1"; 
      calendarWrapper.style.width = "440px";

      datatableWrapper.appendChild(calendarWrapper);

      // Render calendar view
      renderTimesheetCalendar(calendarWrapper);
    }
    else if (tab === "Team Calender") {
        cardWrapper.innerHTML = "";
        datatableWrapper.innerHTML = "";

        const topBar = document.createElement("div");
        topBar.style.display = "flex";
        topBar.style.justifyContent = "space-between";
        topBar.style.alignItems = "center";
        topBar.style.marginBottom = "10px";

        // legend (color codes)
        const legend = document.createElement("div");
        legend.innerHTML = `
            <div style="font-size:14px;">
                <span style="display:inline-block; width:15px; height:15px; background:#28a745; margin-right:5px;"></span>
                Public Holidays
                <span style="display:inline-block; width:15px; height:15px; background:#ff69b4; margin-left:15px; margin-right:5px;"></span>
                Half Day Leaves
                <span style="display:inline-block; width:15px; height:15px; background:#6b9eeb; margin-left:15px; margin-right:5px;"></span>
                Full Day Leaves
            </div>
        `;

        // filters (checkboxes)
        const filterDiv = document.createElement("div");
        filterDiv.innerHTML = `
            <label style="margin-right:15px;">
                <input type="checkbox" id="filter-holidays"> Show Only Holidays
            </label>
            <label>
                <input type="checkbox" id="filter-leaves"> Show Only Leaves
            </label>
        `;

        // add both in topBar
        topBar.appendChild(legend);
        topBar.appendChild(filterDiv);

        // prepend topBar to datatableWrapper
        datatableWrapper.prepend(topBar);

        const calendarContainer = document.createElement("div");
        calendarContainer.id = "team-calendar";
        calendarContainer.style.minHeight = "650px";
        datatableWrapper.appendChild(calendarContainer);

        frappe.require([
            "/assets/frappe/js/lib/moment/moment.min.js",
            "/assets/frappe/js/lib/fullcalendar/fullcalendar.min.js"
        ], function () {
            frappe.require("/assets/frappe/js/lib/fullcalendar/fullcalendar.min.css");

            const $el = $("#team-calendar");

            if ($el.data("fullCalendar")) {
                $el.fullCalendar("destroy");
            }

            // holidays fetch
            frappe.call({
                method: "phamos.phamos.page.project_action_panel.project_action_panel.get_team_holidays",
                args: {
                    from_date: frappe.datetime.month_start(),
                    to_date: frappe.datetime.month_end()
                },
                callback: function (r) {
                    let holidays = r.message || [];

                    // leaves fetch
                    frappe.call({
                        method: "phamos.phamos.page.project_action_panel.project_action_panel.get_employee_leaves",
                        args: {},
                        callback: function (res) {
                            let leaves = res.message || [];
                            let allEvents = holidays.concat(leaves);

                            $el.fullCalendar({
                              header: {
                                left: "prev,next today",
                                center: "title",
                                right: "month,agendaWeek,agendaDay"
                              },

                              // 🔧 Use text instead of icon fonts (avoids the split/duplicate issue)
                              buttonIcons: false,
                              buttonText: {
                                prev: '‹',
                                next: '›',
                                today: 'Today',
                                month: 'Month',
                                week: 'Week',
                                day: 'Day'
                              },

                              defaultView: "month",
                              height: "auto",
                              contentHeight: "auto",
                              fixedWeekCount: false,
                              editable: false,
                              eventLimit: false,
                              events: allEvents,
                              eventClick: function (calEvent) {
                                frappe.show_alert(calEvent.title);
                              },
                              eventRender: function(event, element) {
                                element.find('.fc-title').html(event.title);
                              }
                            });

                            // ⬇️ After init, style the buttons the way you like
                            const $tb = $el.find('.fc-toolbar');
                            $tb.find('.fc-prev-button, .fc-next-button').css({
                              "font-size": "20px",
                              "line-height": "1",
                              "padding": "0 10px"
                            });
                            $tb.find('.fc-button').css({
                              "text-transform": "none",
                              "letter-spacing": "0"
                            });
                            // filter function
                            function applyFilter() {
                                let showHolidays = document.getElementById("filter-holidays").checked;
                                let showLeaves = document.getElementById("filter-leaves").checked;

                                $el.fullCalendar("removeEvents");

                                if (showHolidays && !showLeaves) {
                                    $el.fullCalendar("addEventSource", holidays);
                                } else if (showLeaves && !showHolidays) {
                                    $el.fullCalendar("addEventSource", leaves);
                                } else {
                                    $el.fullCalendar("addEventSource", allEvents); // default
                                }
                            }

                            // checkbox event listeners
                            document.getElementById("filter-holidays").addEventListener("change", applyFilter);
                            document.getElementById("filter-leaves").addEventListener("change", applyFilter);
                        }
                    });
                }
            });
        });
    }

}
function renderTimesheetCalendar(container) {
  const rowHeight = 40;

  // Date picker container
  const dateWrapper = document.createElement("div");
  dateWrapper.className = "mb-2";
  dateWrapper.style.background = "var(--bg-color, #fff)";
  dateWrapper.style.borderRadius = "8px";
  dateWrapper.style.padding = "10px 0";                                                                                                                                                                                                                                                                                                                                                                                                                   

  const dateInput = document.createElement("input");                                                                                                                                                                                                                                                                                                                                      
  dateInput.type = "date";
  dateInput.value = new Date().toISOString().split("T")[0]; // default today
  dateInput.className = "border px-2 py-1 rounded";

  dateWrapper.appendChild(dateInput);

    // Day name span
    const dayName = document.createElement("span");
    dayName.className = "font-bold";
    dayName.style.fontSize = "14px";
    dayName.style.marginLeft = "150px";
    dayName.style.verticalAlign = "middle";
    dateWrapper.appendChild(dayName);

    container.innerHTML = "";
    container.appendChild(dateWrapper);

    // Function to show day name
    function updateDayName(selectedDate) {
      const dateObj = new Date(selectedDate);
      const options = { weekday: 'long' };
      const day = dateObj.toLocaleDateString('en-US', options);
      dayName.innerText = day;
    }


  // Load calendar for a given date
  function loadCalendar(selectedDate) {
    frappe.call({
      method: "phamos.phamos.page.project_action_panel.project_action_panel.get_timesheet_records_by_date",
      args: { selected_date: selectedDate },
      callback: function(r) {
        if (r.message) {
          const userTZ = r.message.user_timezone || "User";

          const tbl = document.createElement("table");
          tbl.className = "timezone-table";

          // Header
          const thead = document.createElement("thead");
          const headRow = document.createElement("tr");
          headRow.innerHTML = `<th>${userTZ}</th><th>Germany</th>`;
          thead.appendChild(headRow);
          tbl.appendChild(thead);

          // Body (slots)
          const tbody = document.createElement("tbody");
          r.message.slots.forEach(slot => {
            const tr = document.createElement("tr");
            tr.innerHTML = `<td>${slot.user}</td><td>${slot.germany}</td>`;
            tbody.appendChild(tr);
          });
          tbl.appendChild(tbody);

          // Left side table
          const tableDiv = document.createElement("div");
          tableDiv.className = "calendar-left";
          tableDiv.appendChild(tbl);

          // Right side (records)
          const calendarRight = document.createElement("div");
          calendarRight.className = "calendar-right relative flex-1 border";
          calendarRight.style.height = r.message.slots.length * rowHeight + "px";

          r.message.records.forEach(rec => {
            const from_user = rec.from_time_user;
            const to_user   = rec.to_time_user;

            const [fh, fm] = from_user.split(":").map(Number);
            const [th, tm] = to_user.split(":").map(Number);

            const startMins = (fh * 60 + fm) - (8 * 60);
            const endMins   = (th * 60 + tm) - (8 * 60);
            const offset = 78;
            const top = (startMins / 60) * rowHeight + offset;
            const height = ((endMins - startMins) / 60) * rowHeight;

            const box = document.createElement("div");
            box.className = "timesheet-box absolute left-2 right-2 border rounded p-1 text-xs";
            box.innerText = `${rec.project || "Work"} (${from_user.substring(0,5)} - ${to_user.substring(0,5)})`;

            box.style.top = top + "px";
            box.style.height = height + "px";

            // ===== Background logic =====
            if (rec.creation && rec.to_time) {
              const creationDate = new Date(rec.creation.replace(" ", "T"));
              const toDate       = new Date(rec.to_time.replace(" ", "T"));

              if (!isNaN(creationDate) && !isNaN(toDate)) {
                const creationDay = creationDate.toISOString().split("T")[0];
                const toDay       = toDate.toISOString().split("T")[0];

                if (creationDay !== toDay) {
                  box.style.backgroundColor = "rgba(255, 0, 0, 0.3)";   // red
                  box.style.borderColor = "red";
                } else {
                  const diffHours = (creationDate - toDate) / (1000 * 60 * 60);
                  if (diffHours < 1) {
                    box.style.backgroundColor = "rgba(0, 128, 0, 0.3)"; // green
                    box.style.borderColor = "green";
                  } else {
                    box.style.backgroundColor = "rgba(255, 165, 0, 0.3)"; // amber
                    box.style.borderColor = "orange";
                  }
                }
              }
            }

            calendarRight.appendChild(box);
          });

          // Final wrapper
          const calendarWrapper = document.createElement("div");
          calendarWrapper.className = "calendar-wrapper flex gap-4";
          calendarWrapper.appendChild(tableDiv);
          calendarWrapper.appendChild(calendarRight);

          // Replace old content
          const oldCalendar = container.querySelector(".calendar-wrapper");
          if (oldCalendar) oldCalendar.remove();
          container.appendChild(calendarWrapper);
        }
      }
    });
  }

  // Load first time with today's date
  loadCalendar(dateInput.value);
  updateDayName(dateInput.value);


  // Reload on date change
  dateInput.addEventListener("change", function() {
    loadCalendar(this.value);
    updateDayName(this.value);

  });
}





// Function to render DataTable
function renderProjectDataTable(datatableWrapper, projectData) {
  // Assign Button
  let button_formatter1 = (value, row) => {
    return `<button type="button" style="height: 23px; width: 60px; display: flex; align-items: center; justify-content: center; background-color: rgb(255, 165, 0);" class="btn btn-primary btn-sm btn-modal-primary" onclick="assignProject('${row[10].content}')">Assign</button>`;
  };

 let button_formatter = (value, row) => {
  const taskId = row[10].content;
  const logId = row[9].content;
  const user = row[1].content;
  const project = row[4].content;
  const status = row[13]?.content;
  const parent = row[12]?.content || '';
  const emp_id = row[11]?.content;

  let buttons = '';

  if (!logId) {
    // Start button only
    buttons += `
      <button id="start-${taskId}" type="button"
        style="height: 23px; width: 60px; display: flex; align-items: center;
        justify-content: center; background-color: rgb(0, 100, 0);"
        class="btn btn-primary btn-sm btn-modal-primary"
        onclick="startProject('${user}', '${project}', '${taskId}', '${status}')">
        Start
      </button>`;
  } else {
    // Stop + Pause (icon-only) button side by side
    buttons += `
      <div style="display: flex; align-items: center; gap: 5px;">
        <button id="stop-${taskId}" type="button"
          style="height: 23px; width: 60px; display: flex; align-items: center;
          justify-content: center; background-color: rgb(139, 0, 0);"
          class="btn btn-primary btn-sm btn-modal-primary"
          onclick="stopProject('${logId}', '${emp_id}', '${taskId}', '${parent}', '${status}')">
          Stop
        </button>

        <button id="toggle-${taskId}" type="button"
        style="height: 23px; width: 23px; padding: 0; border: none; background: none;"
        class="btn btn-sm"
        data-paused="false"
        data-timesheet="${logId}"
        onclick="togglePausePlay('${taskId}', '${logId}')">
        ⏸️
      </button>
      </div>`;
  }
  console.log("clicked", onclick)

  return buttons;

};

  
  const button_formatter2 = (value, row, column, rowIndex, columnIndex, data) => {
    // Extract the actual row index
    const actualRowIndex = row[0]?.rowIndex;
    
    // Fallback for unique ID
    const uniqueId = actualRowIndex !== undefined ? actualRowIndex : `row-${Math.random().toString(36).substring(7)}`;
    const dropdownId = `dropdownMenu-${uniqueId}`;
  
    return `
      <div class="custom-dropdown">
        <button
          class="btn btn-primary btn-sm btn-modal-primary dropdown-btn"
          type="button"
          style="height: 23px; width: 60px; display: flex; align-items: center; justify-content: center; background-color: rgb(255, 140, 0);"
          onclick="toggleDropdown(event, '${dropdownId}')"
        >
          Assign
        </button>
        <div class="dropdown-menu" id="${dropdownId}">
          <a class="dropdown-item" href="#" data-option="Self" onclick="selfAssignProject('${row?.[10]?.content || ''}')">Self</a>
          <a class="dropdown-item" href="#" data-option="Others" onclick="assignProject('${row?.[10]?.content || ''}')">Others</a>
        </div>
      </div>
    `;
  };
  

  let columns = [
    { label: "<b>Project Name</b>", id: "project_name", fieldtype: "Data", width: 180, editable: false, visible: false },
    { label: "<b>Project</b>", id: "project_desc", fieldtype: "Data", width: 340, editable: false, format: linkFormatter1 },
    { label: "<b>Action</b>", focusable: false, format: button_formatter, width: 100 },
    { label: "<b>Customer Name</b>", id: "customer", fieldtype: "Link", width: 120, editable: false },
    { label: "<b>Customer</b>", id: "customer_desc", fieldtype: "Link", width: 340, editable: false, format: linkFormatter },
    { label: "<b>Hours Status</b>", id: "planned_hours", fieldtype: "Data", width: 230, editable: false,format: hoursFormatter },
    { label: "<b></b>", id: "spent_hours_draft", fieldtype: "Float", width: 70, editable: false },
    { label: "<b></b>", id: "spent_hours_submitted", fieldtype: "Float", width: 70, editable: false },
    { label: "<b>Timesheet Record</b>", id: "timesheet_record", fieldtype: "Link", width: 180, editable: false, format: linkFormatter2 },
    { label: "<b>Name</b>", id: "name", fieldtype: "Link", width: 140, editable: false },
    { label: "<b>percent_billable</b>", id: "percent_billable", fieldtype: "Data", width: 0, editable: false },
    { label: "<b>Task</b>", id: "task", fieldtype: "Link", width: 0, editable: false },
    { label: "<b>task_in_timesheet_record</b>", id: "task_in_timesheet_record", fieldtype: "Data", width: 0, editable: false },
    {
      label: '<svg class="icon icon-sm"><use href="#icon-assign"></use></svg> <b>Assign To</b>', 
      focusable: false, 
      format: button_formatter2, 
      width: 120 
    }
  ];
  function hoursFormatter(value, row) {
    const plannedHours = row[6]?.content || 0; // Planned hours
    const spentDraft = row[7]?.content || 0;  // Spent hours (Draft)
    const spentSubmitted = row[8]?.content || 0; // Spent hours (Submitted)
  
    // Combine into a styled display
    return `
    <div style="
      text-align: center;
      font-size: 10px;
      border: 1px solid #ccc;
      border-radius: 5px;
      padding: 3px 5px;
      white-space: nowrap;
      overflow: hidden;
      text-overflow: ellipsis;
    ">
      <span style="color: #4682B4; font-weight: bold;">P: ${plannedHours} hrs</span> | 
      <span style="color: #FFA500;">D: ${spentDraft} hrs</span> | 
      <span style="color: #32CD32;">S: ${spentSubmitted} hrs</span>
    </div>
  `;
  }
  
  
  function linkFormatter1(value, row) {
    return `<a href="#" onclick="handleProjectClick('${row[10].content}');">${row[2].content}</a>`;
  }
  function linkFormatter(value, row) {
    return `<a href="#" onclick="handleCustomerClick('${row[5].content}');">${row[5].content}</a>`;
  }
  function linkFormatter2(value, row) {
    return row[9]?.content ? `<a href="#" onclick="handleTimesheetClick('${row[9].content}');">${row[9].content}</a>` : "";
  }
  // Add a combined style element to hide the specified columns and headers
let style = document.createElement("style");
style.innerHTML = `

/* Hide the "Name" column cells and header */
.dt-cell__content--col-10, .dt-cell__content--header-10 { display: none; }

/* Hide the "Customer Name" column cells and header */
.dt-cell__content--col-4, .dt-cell__content--header-4 { display: none; }

/* Hide the "Project Name" column cells and header */
.dt-cell__content--col-1, .dt-cell__content--header-1 { display: none; }

/* Hide the "percent_billable" column cells and header */
.dt-cell__content--col-11, .dt-cell__content--header-11 { display: none; }

/* Hide the "task" column cells and header */
.dt-cell__content--col-12, .dt-cell__content--header-12 { display: none; }

/* Hide the "task_in_timesheet_record" column cells and header */
.dt-cell__content--col-13, .dt-cell__content--header-13 { display: none; }

/* Hide additional columns */
.dt-cell__content--col-7, .dt-cell__content--header-7 { display: none; }
.dt-cell__content--col-8, .dt-cell__content--header-8 { display: none; }

`;
document.head.appendChild(style);
  // Initialize DataTable with the data and column configuration
  let datatable = new frappe.DataTable(
    datatableWrapper,
    {
      columns: columns.map((col) => ({ content: col.label, ...col })), // Include the column headers
      data: projectData,
      inlineFilters: true,
      language: frappe.boot.lang,
      translations: frappe.utils.datatable.get_translations(),
      layout: "fixed",
      cellHeight: 33,
      direction: frappe.utils.is_rtl() ? "rtl" : "ltr",
      header: true, // Ensure that column headers are shown
      width: "100%",
    }
  );

  // Move the table to the center and add margin on top
  $(datatableWrapper).css({
    "margin-top": "50px",
    "text-align": "center",
    "margin-left": "10px",
    width: "1220px",
  });

  // Apply styling to the card wrapper
 
}

window.togglePausePlay = function(taskId, timesheetName) {
  const btn = document.getElementById(`toggle-${taskId}`);
  const isPaused = btn.getAttribute('data-paused') === 'true';

  if (isPaused) {
    btn.textContent = '⏸️';
    btn.setAttribute('data-paused', 'false');

    frappe.confirm(
      "Do you want to create a timesheet record for this Break?",
      function() {
          frappe.call({
              method: "phamos.phamos.page.project_action_panel.project_action_panel.close_open_row_and_add_break",
              args: { name: timesheetName },
              callback: function(r) {
                  if (r.message && r.message.status === "success") {
                      show_break_task_dialog(r.message.new_row_name, r.message.previous_from_time, r.message.previous_to_time, );
                  } else {
                      frappe.show_alert("Error: " + (r.message.message || "Something went wrong."));
                  }
              }
          });
      },
      function() {
          // ❌ NO → create new row but don't show popup
          frappe.call({
              method: "phamos.phamos.page.project_action_panel.project_action_panel.close_open_row_and_add_break",
              args: { name: timesheetName },
              callback: function(r) {
                  if (r.message && r.message.status === "success") {
                      frappe.show_alert("Break Time noted");
                  } else {
                      frappe.show_alert("Error: " + (r.message.message || "Something went wrong."));
                  }
              }
          });
      }
  );


  } else {
    // Pause clicked → Close current row
    btn.textContent = '▶️';
    btn.setAttribute('data-paused', 'true');
    console.log(`Paused Task: ${taskId}`);

    frappe.call({
      method: "phamos.phamos.page.project_action_panel.project_action_panel.update_to_time",
      args: {
        name: timesheetName
      },
      callback: function(r) {
        if (r.message && r.message.status === "success") {
          frappe.show_alert("First Task paused. Time updated successfully.");
        } else {
          frappe.show_alert("Error: " + (r.message.message || "Something went wrong."));
        }
      }
    });
  }
};
frappe.after_ajax(() => {
  console.log("frappe.after_ajax started");
  const taskButtons = document.querySelectorAll("[id^='toggle-']");
  console.log("Buttons found:", taskButtons.length);

  taskButtons.forEach(btn => {
    const taskId = btn.id.split("toggle-")[1];
    const timesheetName = btn.getAttribute("data-timesheet");

    console.log("Checking task:", taskId, "timesheet:", timesheetName);

    frappe.call({
      method: "phamos.phamos.page.project_action_panel.project_action_panel.is_task_running",
      args: {
        name: timesheetName
      },
      callback: function (r) {
        if (r.message && r.message.is_running) {
          btn.textContent = '⏸️';
          btn.setAttribute('data-paused', 'false');
          btn.setAttribute('title', 'Pause ⏸️');
        } else {
          btn.textContent = '▶️';
          btn.setAttribute('data-paused', 'true');
          btn.setAttribute('title', 'Resume ▶️');
        }

      }
    });
  });
});
};

function show_break_task_dialog(new_row_name, previous_from_time, previous_to_time) {
    let task_field_properties = {
        fieldtype: "Link",
        options: "Task",
        label: __("Task"),
        fieldname: "task",
        in_list_view: 1,
        read_only: 0,
        reqd: 1,
        description:"Please select a task."
    };

    var dialog = new frappe.ui.Dialog({
        title: __("Add Timesheet record."),
        fields: [
                {
                  fieldtype: "Link",
                  options: "Project",
                  label: __("Project Name"),
                  fieldname: "project_name",
                  in_list_view: 1,
                  reqd: 1,
                  get_query: function() {
                    return {
                        query: "phamos.phamos.page.project_action_panel.project_action_panel.get_assigned_projects"
                    };
                  }
                },
                {
                  fieldtype: "Link",
                  options: "Activity Type",
                  label: __("Activity Type"),
                  fieldname: "activity_type",
                  reqd: 1,
                  description:
                          'The "Activity Type" allows for categorizing tasks into specific types, such as planning, execution, communication, and proposal writing, streamlining task management and organization within the system.',
                },
                {
                  fieldtype: "Data",
                  label: __("Expected Time (quick input)"),
                  fieldname: "expected_time_quick",
                  description: __("Type the expected duration as minutes (20) or as hours and minutes (1:20, 1.20, or 1,20) or as hours, minutes, and seconds (1:20:30) and it will auto-fill Expected Time."),
                  in_list_view: 1,
                },
                {
                  fieldtype: "Duration",
                  label: __("Expected Time"),
                  fieldname: "expected_time",
                  in_list_view: 1,
                  reqd: 1,
                  read_only: 1,
                },
                {
                  fieldtype: "Datetime",
                  label: __("From Time"),
                  fieldname: "from_time",
                  in_list_view: 1,
                  reqd: 1,
                  read_only: 1,
                  default: previous_from_time
                },
                { 
                  fieldtype: "Small Text",
                  label: __("Goal"),
                  fieldname: "goal",
                  in_list_view: 1,
                  reqd: 1,
                  description:
                    "⚠️ User need to manifest on what you are working and going to do. This will be shared with the customer next day.",
                },
                {
                  fieldtype: "Column Break",
                },
                {
                  fieldtype: "Datetime",
                  label: __("To Time"),
                  fieldname: "to_time",
                  in_list_view: 1,
                  reqd: 1,
                  read_only: 1,
                  default: previous_to_time
                },
                {
                  fieldtype: "Select",
                  options: [0, 25, 50, 75, 100],
                  label: __("Percent Billable"),
                  fieldname: "percent_billable",
                  reqd: 1,
                  description:
                          "This is a personal indicator to your own performance on the work you have done. It will influence the billable time of the Timesheet created.",

                },
                {
                  label: "What I did ",
                  fieldname: "result",
                  fieldtype: "Small Text",
                  reqd: 1,
                  description:
                          "⚠️ This information is sent to the customer next day. Please make sure to wright meaningful text. Adding Issues ID's and or URL is helpful.",

                },
              ],
              primary_action_label: __("Create Timesheet Record."),
              primary_action(values) {
                frappe.call({
                method: "phamos.phamos.page.project_action_panel.project_action_panel.create_and_submit_timesheet",
                args: {
                    project_name: values.project_name,          
                    goal: values.goal,                          
                    from_time: values.from_time,                
                    to_time: values.to_time,                    
                    expected_time: values.expected_time,        
                    percent_billable: values.percent_billable,  
                    activity_type: values.activity_type,        
                    result: values.result,                      
                },
                callback: function(r) {
                    if (r.message && r.message.status === "success") {
                        frappe.show_alert(__("Timesheet Record {0} created and submitted", [r.message.name]));
                    } else {
                        frappe.show_alert(__("Error: {0}", [r.message.message]));
                    }
                }
            });
                dialog.hide();
              },
            });
            // Set the width using CSS
    dialog.$wrapper.find(".modal-dialog").css("max-width", "800px");
    dialog.show();

    setTimeout(function () {
      const $quick = dialog.$wrapper.find('[data-fieldname="expected_time_quick"]').find("input");
      if ($quick.length) {
        $quick.on("input change", function () {
          const val = $(this).val();
          if (!val || !val.trim()) {
            dialog.set_value("expected_time", 0);
          } else {
            const seconds = parse_duration_to_seconds(val);
            if (seconds !== null && seconds >= 0) {
              dialog.set_value("expected_time", seconds);
            }
          }
        });
      }
    }, 0);
}


