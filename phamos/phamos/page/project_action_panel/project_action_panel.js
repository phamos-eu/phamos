let project_ = ""
frappe.pages['project-action-panel'].on_page_load = function(wrapper) {
    // Ensure wrapper is defined
    if (!wrapper) {
        return;
    }

    // Set the title of the page
    if (wrapper.page) {
        wrapper.page.set_title('<span style="font-size: 14px;">Project Action Panel</span>');
    }

    // Fetch project data from the server on page load
    frappe.call({
        method: "phamos.phamos.page.project_action_panel.project_action_panel.fetch_projects",
        callback: function(r) {
            if (r.message) {
                // Render DataTable with the fetched data
                renderDataTable(wrapper, r.message);
            } else {
                // Handle error or empty data
            }
        }
    });
   
    // Function to create timesheet record
    function create_timesheet_record(project_name,customer,activity_type,percent_billable,from_time,expected_time,goal){
        frappe.call({
            method: "phamos.phamos.page.project_action_panel.project_action_panel.create_timesheet_record",
            args: {
                "project_name": project_name,
                "customer": customer,
                "activity_type":activity_type,
                "percent_billable":percent_billable,
                "from_time":from_time,
                "expected_time":expected_time,
                "goal":goal
            },
            freeze: true,
			freeze_message: __("Creating Timesheet Record......"),
			callback: function(r) {
				if(r.message) {
                    var doc = frappe.model.sync(r.message);
					frappe.msgprint('Timesheet Record: '+doc[0].name+' Created Successfully.');
					}
				}
        })
    }

    // Function to create timesheet record
    function update_and_submit_timesheet_record(timesheet_record,to_time,result){
        frappe.call({
            method: "phamos.phamos.page.project_action_panel.project_action_panel.update_and_submit_timesheet_record",
            args: {
                "name": timesheet_record,
                "to_time": to_time,
                "result":result,
            },
            freeze: true,
			freeze_message: __("Updating Timesheet Record......"),
			callback: function(r) {
				if(r.message) {
                    var doc = frappe.model.sync(r.message);
					frappe.msgprint('Timesheet Record: '+doc[0].name+' Updated Successfully.');
					}
				}
        })
    }

    window.stopProject = function(timesheet_record) {
        var dialog = new frappe.ui.Dialog({
            title: __("Mark Complete Timesheet record."),
            fields: [
                {
                    fieldtype: "Data",
                    label: __("Timesheet Record"),
                    fieldname: "timesheet_record",
                    in_list_view: 1,
                    read_only:1,
                    default: timesheet_record
                },
                {
                    label: 'Time',
                    fieldname: 'to_time',
                    fieldtype: 'Datetime',
                    default: frappe.datetime.now_datetime(), reqd: 1
                },
                {
                    fieldtype: 'Column Break'
                },
                {
                    label: 'What I did ',
                    fieldname: 'result',
                    fieldtype: 'Small Text', reqd: 1
                },
                
            ],
            primary_action_label: __("Update Timesheet Record."),
            primary_action(values) {
                update_and_submit_timesheet_record(values.timesheet_record,values.to_time,values.result)
                dialog.hide();
                window.location.reload();
            }
        });
    
        dialog.show();
    };

    window.startProject = function(project_name, customer) {
        frappe.call({
            method: "phamos.phamos.page.project_action_panel.project_action_panel.check_draft_timesheet_record",
            callback: function(r) {
                if (r.message) {
                    var timesheetRecordDrafts = r.message;
    
                    // Process the retrieved draft Timesheet Records
                    if (timesheetRecordDrafts && timesheetRecordDrafts.length > 0) {
                        // Show error message that draft Timesheet Records are found
                        frappe.msgprint(__("Draft Timesheet Records found. Please submit them before creating a new one."));
                    } else {
                        // No draft Timesheet Records found, show dialog to create new Timesheet Record
                        var dialog = new frappe.ui.Dialog({
                            title: __("Add Timesheet record."),
                            fields: [
                                {
                                    fieldtype: "Data",
                                    options: "Project",
                                    label: __("Project Name"),
                                    fieldname: "project_name",
                                    in_list_view: 1,
                                    read_only:1,
                                    default: project_name
                                },
                                {
                                    fieldtype: "Data",
                                    options: "Customer",
                                    label: __("Customer"),
                                    fieldname: "customer",
                                    in_list_view: 1,
                                    read_only:1,
                                    default: customer
                                },
                                {
                                    fieldtype: "Link",
                                    options: "Activity Type",
                                    label: __("Activity Type"),
                                    fieldname: "activity_type",
                                    in_list_view: 1,
                                    reqd: 1
                                },
                                {
                                    fieldtype: "Select",
                                    options: [0,25,50,75,100],
                                    label: __("Percent Billable"),
                                    fieldname: "percent_billable",
                                    in_list_view: 1,
                                    reqd: 1
                                },
                                {
                                    fieldtype: 'Column Break'
                                },
                                {
                                    fieldtype: "Datetime",
                                    label: __("From Time"),
                                    fieldname: "from_time",
                                    in_list_view: 1,
                                    reqd: 1
                                },
                                {
                                    fieldtype: "Duration",
                                    label: __("Expected Time"),
                                    fieldname: "expected_time",
                                    in_list_view: 1,
                                    reqd: 1
                                },
                                {
                                    fieldtype: "Small Text",
                                    label: __("Goal"),
                                    fieldname: "goal",
                                    in_list_view: 1,
                                    reqd: 1
                                },
                            ],
                            primary_action_label: __("Create Timesheet Record."),
                            primary_action(values) {
                                create_timesheet_record(values.project_name,values.customer,values.activity_type,values.percent_billable,values.from_time,values.expected_time,values.goal)
                                dialog.hide();
                                window.location.reload();
                            }
                        });
    
                        dialog.show();
                    }
                } else {
                    // No response from server
                    frappe.msgprint(__("No response from server. Please try again."));
                }
            }
        });
    };
    
     
    // Function to render DataTable
    function renderDataTable(wrapper, projectData) {
        // Ensure wrapper is defined
        if (!wrapper) {
            return;
        }
        
        // Define columns for the report view
        // Define the function
        

       
        // Define the button formatter function with the click event calling the startProject function
        //let button_formatter = (value, row) => {
                // Now that both project and employee values are available, you can render the button
           // return `<button type="button" style="height: 23px; width: 60px; display: block; background-color: rgb(144, 238, 144);" class="btn btn-primary btn-sm btn-modal-primary" onclick="startProject('${row[1].content}', '${row[3].content}')">Start</button>`;  
        //};
        let button_formatter = (value, row) => {
                // Now that both project and employee values are available, you can render the button
            if (row[4].html == ""){
                return `<button type="button" style="height: 23px; width: 60px; display: flex; align-items: center; justify-content: center; background-color: rgb(0, 100, 0);" class="btn btn-primary btn-sm btn-modal-primary" onclick="startProject('${row[1].content}', '${row[3].content}')">Start</button>`;
                //return `<button type="button" style="height: 23px; width: 60px; display: block;" class="btn btn-primary btn-sm btn-modal-primary" onclick="startProject('${row[1].content}', '${row[3].content}')">Start</button>`;
            }
            else {
                //return `<button type="button" style="height: 23px; width: 60px; display: block; background-color: rgb(255, 144, 144);" class="btn btn-primary btn-sm btn-modal-primary" onclick="stopProject('${row[4].content}')">Stop</button>`;
                return `<button type="button" style="height: 23px; width: 60px; display: flex; align-items: center; justify-content: center; background-color: rgb(139, 0, 0);" class="btn btn-primary btn-sm btn-modal-primary" onclick="stopProject('${row[4].content}')">Stop</button>`;

            }
        };
        
        let columns = [
            { label: "<b>Project Name</b>", id: "project_name", fieldtype: "Data", width: 200 },
            { label: "<b>Notes</b>", id: "notes", fieldtype: "Data", width: 200 },
            { label: "<b>Customer</b>", id: "customer", fieldtype: "Link", width: 200 },
            { label: "<b>Timesheet Record</b>", id: "timesheet_record", fieldtype: "Link", width: 150 },
            { label: "<b>Action</b>", focusable: false, format: button_formatter , width: 150}
        ];
        // Add a header to the report view
        wrapper.innerHTML = `<h1>Project Action Panel</h1><div id="datatable-wrapper"></div>`;
        
        // Initialize DataTable with the data and column configuration
        let datatable = new frappe.DataTable(wrapper.querySelector('#datatable-wrapper'), {
            columns: columns.map(col => ({ content: col.label, ...col })), // Include the column headers
            data: projectData,
            inlineFilters: true,
            language: frappe.boot.lang,
            translations: frappe.utils.datatable.get_translations(),
            layout: "fixed",
            cellHeight: 33,
            direction: frappe.utils.is_rtl() ? "rtl" : "ltr",
            header: true, // Ensure that column headers are shown
        
        });
        // Move the table to the center and add margin on top
        $(wrapper.querySelector('#datatable-wrapper')).css({
            'margin-top': '50px',
            'text-align': 'center',
            'margin-left': '50px',
        });
         
    }
};