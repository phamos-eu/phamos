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
          frappe.msgprint(
            "Timesheet Record: " + doc[0].name + " Created Successfully."
          );
          render_datatable();
        }
      },
    });
  }

  // Function to create timesheet record
  function update_and_submit_timesheet_record(
    timesheet_record,
    task,
    to_time,
    percent_billable,
    activity_type,
    result
  ) {
    frappe.call({
      method:
        "phamos.phamos.page.project_action_panel.project_action_panel.update_and_submit_timesheet_record",
      args: {
        name: timesheet_record,
        task:task,
        to_time: to_time,
        percent_billable: percent_billable,
        activity_type: activity_type,
        result: result,
      },
      freeze: true,
      freeze_message: __("Updating Timesheet Record......"),
      callback: function (r) {
        if (r.message) {
          let doc = frappe.model.sync(r.message);
          frappe.msgprint(
            "Timesheet Record: " + doc[0].name + " Updated Successfully."
          );
          render_datatable();
        }
      },
    });
  }

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

  window.stopProject = function (timesheet_record, percent_billable,project,task,task_in_timesheet_record) {
    let activity_type = "";
    let timesheet_record_info = " Info from timesheet record";
    frappe.db.get_value(
      "Timesheet Record",
      { name: timesheet_record },
      ["goal", "from_time"],
      function (value) {
        // Your code here
        from_time_formatted = frappe.datetime.str_to_user(value.from_time);
        timesheet_record_info =
          "From time: " + from_time_formatted + ",<br>Goal is: " + value.goal;

        frappe.db.get_value(
          "Employee",
          { user_id: frappe.session.user },
          "activity_type",
          function (value) {

            let task_field_properties = {
              fieldtype: "Link",
              options: "Task",
              label: __("Task"),
              fieldname: "task",
              in_list_view: 1,
              read_only: 0,
              default:task,
              description:"Please consult the Project Manager if unsure which task to choose.",
              get_query: function() {
                  if (project) {
                      return {
                          filters: {
                              project: project
                          }
                      };
                  } else {
                      return {};
                  }
              }}
  
              if (task_in_timesheet_record === "Task is hidden") {
                task_field_properties.hidden = 1; // Hide the field
              } else if (task_in_timesheet_record === "Task is optional") {
                task_field_properties.reqd = 0; // Make it optional (non-mandatory)
                task_field_properties.description = "Please consult the Project Manager if unsure which task to choose."
              } else if (task_in_timesheet_record === "Task is mandatory") {
                task_field_properties.reqd = 1; // Make it mandatory
                task_field_properties.description = "Please consult the Project Manager if unsure which Task to choose."
              }

            let dialog = new frappe.ui.Dialog({
              title: __("Mark Complete Timesheet record."),
              fields: [
                {
                  fieldtype: "Data",
                  label: __("Timesheet Record"),
                  fieldname: "timesheet_record",
                  in_list_view: 1,
                  read_only: 1,
                  default: timesheet_record,
                },
                task_field_properties, 

                {
                  fieldtype: "Small Text",
                  label: __("Timesheet Record Info"),
                  fieldname: "timesheet_record_info",
                  in_list_view: 1,
                  read_only: 1,
                  default: timesheet_record_info,
                },
                {
                  fieldtype: "Column Break",
                },
                {
                  label: "Time",
                  fieldname: "to_time",
                  fieldtype: "Datetime",
                  reqd: 1,
                },

                {
                  fieldtype: "Select",
                  options: [0, 25, 50, 75, 100],
                  label: __("Percent Billable"),
                  fieldname: "percent_billable",
                  in_list_view: 1,
                  reqd: 1,
                  default: percent_billable,
                  description:
                    "This is a personal indicator to your own performance on the work you have done. It will influence the billable time of the Timesheet created.",
                },
                {
                  fieldtype: "Column Break",
                },
                {
                  fieldtype: "Link",
                  options: "Activity Type",
                  label: __("Activity Type"),
                  fieldname: "activity_type",
                  in_list_view: 1,
                  reqd: 1,
                  default: value.activity_type,
                  description:
                    'The "Activity Type" allows for categorizing tasks into specific types, such as planning, execution, communication, and proposal writing, streamlining task management and organization within the system.',
                },
                {
                  fieldtype: "Column Break",
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
              primary_action_label: __("Update Timesheet Record."),
              primary_action(values) {
                update_and_submit_timesheet_record(
                  values.timesheet_record,
                  values.task,
                  values.to_time,
                  values.percent_billable,
                  values.activity_type,
                  values.result
                );
                dialog.hide();
              },
            });
            // Set the width using CSS
            dialog.$wrapper.find(".modal-dialog").css("max-width", "900px");
            dialog.show();
          }
        );
      }
    );
  };
  //return record.timesheet_record_draft;
 
  window.assignProject = function(project_name) {
    // Instantiate AssignToDialog if not already done
    let assign_to = new frappe.ui.form.AssignToDialog({
        method: "frappe.desk.form.assign_to.add", // Method for assignment
        doctype: "Project", // The doctype of the document being assigned
        docname: project_name, // The document name to be assigned
        callback: function (r) {
            // Handle the response from the assignment action
            console.log(r.message); // This will contain the result of the assignment
            if (r.message) {
                // You can add logic here to update the UI or provide user feedback
                frappe.show_alert({
                    message: __('Users assigned successfully!'),
                    indicator: 'green'
                });
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

          if (timesheetRecordDrafts && timesheetRecordDrafts.length > 0) {
            //frappe.msgprint(__("Draft Timesheet Records: "+ draftTimesheets+" found. Please submit them before creating a new one."));
            let confirm_msg =
              "Draft Timesheet Records: " +
              draftTimesheets +
              " found. If you want to submit before creating a new one, Click Yes?";
            frappe.confirm(
              confirm_msg,
              function () {
                // If user clicks "Yes"
                frappe.db.get_value(
                  "Timesheet Record",
                  { name: timesheetRecordDrafts[0].timesheet_record_draft },
                  "project",
                  function (value) {
                    frappe.db.get_value(
                      "Project",
                      { name: value.project },
                      "percent_billable",
                      function (value_pb) {
                        stopProject(
                          timesheetRecordDrafts[0].timesheet_record_draft,
                          value_pb.percent_billable
                        );
                      }
                    );
                  }
                );
                // Perform the action here
              },
              function () {
                // If user clicks "No"
                //frappe.msgprint('You clicked No!');
                // Cancel the action here or do nothing
              }
            );
          } else {
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
                  fieldtype: "Duration",
                  label: __("Expected Time"),
                  fieldname: "expected_time",
                  in_list_view: 1,
                  reqd: 1,
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
          }
        } else {
          frappe.msgprint(__("No response from server. Please try again."));
        }
      },
    });
  };

  // Function to render number cards
function render_cards(wrapper, card_names) {
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

      $(wrapper).find(".widget.number-widget-box").css({
        width: "250px", 
      });

      $(wrapper).find(".widget-group-body.grid-col-3").css({
        display: "flex", 
        "flex-wrap": "nowrap", 
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

// Event listener for the Your Projects tab
your_projectsTab.addEventListener("click", () => {
  // Remove 'active' class from All Projects tab and set to Your Projects
  all_projectsTab.classList.remove("active");
  your_projectsTab.classList.add("active");

  // Set visual feedback for selection
  your_projectsTab.setAttribute("aria-selected", "true");
  all_projectsTab.setAttribute("aria-selected", "false");

  // Show content for the Your Projects tab
  show_tab("Your Projects", projectData);
});

// Event listener for the All Projects tab
all_projectsTab.addEventListener("click", () => {
  // Remove 'active' class from Your Projects tab and set to All Projects
  your_projectsTab.classList.remove("active");
  all_projectsTab.classList.add("active");

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
  // Logic to hide the specific column when "Your Projects" tab is active
  
  let style = document.createElement("style");
    style.innerHTML = `
        /* Hide the "Name" column cells and header */
        .dt-cell__content--col-14, 
        .dt-cell__content--header-14 { 
            display: none; 
            width: 0; 
        }
    `;
    document.head.appendChild(style);

  // Render the cards for Your Projects
  card_names = ["Your Total Projects", "Total Hrs Worked Today", "Total Hrs Worked This Week", "Total Hrs Worked This Month"];
  render_cards(cardWrapper, card_names); // Call the render_cards function here

  // Render the DataTable for Your Projects
  renderProjectDataTable(datatableWrapper, projectData); // Render the actual DataTable
} else if (tab === "All Projects") {
  let style = document.createElement("style");
  style.innerHTML = `
    /* Hide the "Name" column cells and header */
    .dt-cell__content--col-14, .dt-cell__content--header-14 { display: table-cell; }
  `;
  document.head.appendChild(style);

  // Define the cards to display
  card_names = ["Total Projects", "Total Hrs Worked Today", "Total Hrs Worked This Week", "Total Hrs Worked This Month"];
  
  // Render the cards immediately to improve perceived speed
  render_cards(cardWrapper, card_names);

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

}


// Function to render DataTable
function renderProjectDataTable(datatableWrapper, projectData) {
  // Define columns for the report view
  let button_formatter1 = (value, row) => {
    
      return `<button type="button" style="height: 23px; width: 60px; display: flex; align-items: center; justify-content: center; background-color: rgb(255, 165, 0);" class="btn btn-primary btn-sm btn-modal-primary" onclick="assignProject('${row[9].content}')">Assign</button>`;
    
  };
  let button_formatter = (value, row) => {
    if (row[8].html == "") {
      return `<button type="button" style="height: 23px; width: 60px; display: flex; align-items: center; justify-content: center; background-color: rgb(0, 100, 0);" class="btn btn-primary btn-sm btn-modal-primary" onclick="startProject('${row[1].content}', '${row[3].content}', '${row[9].content}','${row[13]?.content}')">Start</button>`;
    } else {
      return `<button type="button" style="height: 23px; width: 60px; display: flex; align-items: center; justify-content: center; background-color: rgb(139, 0, 0);" class="btn btn-primary btn-sm btn-modal-primary" onclick="stopProject('${row[8].content}','${row[11].content}', '${row[9].content}','${row[12]?.content || ''}','${row[13]?.content}')">Stop</button>`;
    }
  };

  let columns = [
    { label: "<b>Project Name</b>", id: "project_name", fieldtype: "Data", width: 180, editable: false, visible: false },
    { label: "<b>Project</b>", id: "project_desc", fieldtype: "Data", width: 340, editable: false, format: linkFormatter1 },
    { label: "<b>Customer Name</b>", id: "customer", fieldtype: "Link", width: 120, editable: false },
    { label: "<b>Customer</b>", id: "customer_desc", fieldtype: "Link", width: 340, editable: false, format: linkFormatter },
    { label: "<b>Hours Status</b>", id: "planned_hours", fieldtype: "Data", width: 230, editable: false,format: hoursFormatter },
    { label: "<b></b>", id: "spent_hours_draft", fieldtype: "Float", width: 70, editable: false },
    { label: "<b></b>", id: "spent_hours_submitted", fieldtype: "Float", width: 70, editable: false },
    { label: "<b>Timesheet Record</b>", id: "timesheet_record", fieldtype: "Link", width: 180, editable: false, format: linkFormatter2 },
    { label: "<b>Name</b>", id: "name", fieldtype: "Link", width: 140, editable: false },
    { label: "<b>Action</b>", focusable: false, format: button_formatter, width: 100 },
    { label: "<b>percent_billable</b>", id: "percent_billable", fieldtype: "Data", width: 0, editable: false },
    { label: "<b>Task</b>", id: "task", fieldtype: "Link", width: 0, editable: false },
    { label: "<b>task_in_timesheet_record</b>", id: "task_in_timesheet_record", fieldtype: "Data", width: 0, editable: false },
    {
      label: '<svg class="icon icon-sm"><use href="#icon-assign"></use></svg> <b>Assign To</b>', 
      focusable: false, 
      format: button_formatter1, 
      width: 120 
    }
  ];
  function hoursFormatter(value, row) {
    const plannedHours = row[5]?.content || 0; // Planned hours
    const spentDraft = row[6]?.content || 0;  // Spent hours (Draft)
    const spentSubmitted = row[7]?.content || 0; // Spent hours (Submitted)
  
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
    return `<a href="#" onclick="handleProjectClick('${row[9].content}');">${row[2].content}</a>`;
  }
  function linkFormatter(value, row) {
    return `<a href="#" onclick="handleCustomerClick('${row[3].content}');">${row[4].content}</a>`;
  }
  function linkFormatter2(value, row) {
    return row[8]?.content ? `<a href="#" onclick="handleTimesheetClick('${row[8].content}');">${row[8].content}</a>` : "";
  }
  // Add a combined style element to hide the specified columns and headers
let style = document.createElement("style");
style.innerHTML = `
/* Hide the "Name" column cells and header */
.dt-cell__content--col-9, .dt-cell__content--header-9 { display: none; }

/* Hide the "Customer Name" column cells and header */
.dt-cell__content--col-3, .dt-cell__content--header-3 { display: none; }

/* Hide the "Project Name" column cells and header */
.dt-cell__content--col-1, .dt-cell__content--header-1 { display: none; }

/* Hide the "percent_billable" column cells and header */
.dt-cell__content--col-11, .dt-cell__content--header-11 { display: none; }

/* Hide the "task" column cells and header */
.dt-cell__content--col-12, .dt-cell__content--header-12 { display: none; }

/* Hide the "task_in_timesheet_record" column cells and header */
.dt-cell__content--col-13, .dt-cell__content--header-13 { display: none; }

/* Hide additional columns */
.dt-cell__content--col-6, .dt-cell__content--header-6 { display: none; }
.dt-cell__content--col-7, .dt-cell__content--header-7 { display: none; }

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

};
