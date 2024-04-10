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
     
    // Function to render DataTable
    function renderDataTable(wrapper, projectData) {
        // Ensure wrapper is defined
        if (!wrapper) {
            return;
        }
        
        // Define columns for the report view
        // Define the function
        window.startProject = function(project_name, customer) {
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
                    },
                    {
                        fieldtype: "Select",
                        options: [0,25,50,75,100],
                        label: __("Percent Billable"),
                        fieldname: "percent_billable",
                        in_list_view: 1,
                    },
                    {
                        fieldtype: 'Column Break'
                    },
                    {
                        fieldtype: "Datetime",
                        label: __("From Time"),
                        fieldname: "from_time",
                        in_list_view: 1,
                    },
                    {
                        fieldtype: "Duration",
                        label: __("Expected Time"),
                        fieldname: "expected_time",
                        in_list_view: 1,
                    },
                    {
                        fieldtype: "Small Text",
                        label: __("Goal"),
                        fieldname: "goal",
                        in_list_view: 1,
                    },
                    
                ],
                primary_action_label: __("Create Timesheet Record."),
                primary_action(values) {
                    create_timesheet_record(values.project_name,values.customer,values.activity_type,values.percent_billable,values.from_time,values.expected_time,values.goal)
                    dialog.hide();
                }
            });
        
            dialog.show();
        };
        // Define the button formatter function with the click event calling the startProject function

        /*let button_formatter = (value, row) => {
                // Now that both project and employee values are available, you can render the button
           
            if (row[1].content =="Phamos 2"){
                return `<button type="button" style="height: 23px; width: 60px; display: block; background-color: rgb(144, 238, 144);" class="btn btn-primary btn-sm btn-modal-primary" onclick="startProject('${row[1].content}', '${row[3].content}')">Start</button>`;
                //return `<button type="button" style="height: 23px; width: 60px; display: block;" class="btn btn-primary btn-sm btn-modal-primary" onclick="startProject('${row[1].content}', '${row[3].content}')">Start</button>`;
            }
            else if(row[1].content =="Phamos"){
                return `<button type="button" style="height: 23px; width: 60px; display: block; background-color: rgb(255, 144, 144);" class="btn btn-primary btn-sm btn-modal-primary" onclick="startProject('${row[1].content}', '${row[3].content}')">Stop</button>`;
            }
        };*/
        let button_formatter = (value, row) => {
            let tc = "";
            // Call getValues and wait for its promise to resolve
            getValues(value, row).then(values => {
            // Access values.project, values.employee, values.timesheet_record here
                console.log(values.project);
                console.log(values.employee);
                console.log(values.timesheet_record);
                tc = values.timesheet_record
                if (values.timesheet_record){
                    console.log("i got values");
                }
            })
            .catch(error => {
                console.error("Error occurred:", error);
            // Handle error if necessary
            });
            if (tc){
                return `<button type="button" style="height: 23px; width: 60px; display: block;" class="btn btn-primary btn-sm btn-modal-primary" onclick="startProject('${row[1].content}', '${row[3].content}')">Start</button>`;  
            }
        };

        function getValues(value,row){
            let project_ = "";
            let employee_ = "";
            let timesheet_record = "";
        
            return frappe.db.get_value('Project', {"project_name": row[1].content}, 'name')
                .then(r => {
                    var doc_project = frappe.model.sync(r.message);
                    project_ = doc_project[0].name;
                    console.log(project_);
        
                    return frappe.db.get_value('Employee', {"user_id": frappe.session.user}, 'name');
                })
                .then(r => {
                    var doc_emp = frappe.model.sync(r.message);
                    employee_ = doc_emp[0].name;
                    console.log(employee_);
        
                    return frappe.db.get_value('Timesheet Record', {"project": project_, "employee": employee_, "docstatus": 0}, 'name');
                })
                .then(r => {
                    var doc_tc = frappe.model.sync(r.message);
                    timesheet_record = doc_tc[0].name;
                    console.log(timesheet_record);
                    return { project: project_, employee: employee_, timesheet_record: timesheet_record };
        
                    // Conditionally render the button based on the value of timesheet_record
                    
                });
        };
        
        let columns = [
            { label: "<b>Project Name</b>", id: "project_name", fieldtype: "Data", width: 300 },
            { label: "<b>Notes</b>", id: "notes", fieldtype: "Data", width: 300 },
            { label: "<b>Customer</b>", id: "customer", fieldtype: "Link", width: 200 },
            { label: "<b>Start</b>", focusable: false, format: button_formatter , width: 150}
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


