/*frappe.pages['project-action-panel'].on_page_load = function(wrapper) {
    // Ensure wrapper is defined
    if (!wrapper) {
        console.error("Wrapper is not defined.");
        return;
    }

    // Set the title of the page
    if (wrapper.page) {
        wrapper.page.set_title('<span style="font-size: 14px;">Project Action Panel</span>');
    }

    // Fetch project data from the server
    frappe.call({
        method: "phamos.phamos.page.project_action_panel.project_action_panel.fetch_projects",
        callback: function(r) {
            if (r.message) {
                // Render DataTable with the fetched data
                renderDataTable(wrapper, r.message);
            } else {
                // Handle error or empty data
                console.log("No project data found");
            }
        }
    });

    // Function to render DataTable
    function renderDataTable(wrapper, projectData) {
        // Ensure wrapper is defined
        if (!wrapper) {
            console.error("Wrapper is not defined.");
            return;
        }

        // Define columns for the report view
        let button_formatter = (value) => `<button style="display: block; margin: 0 auto;" onclick="alert('This is ${value}')">Action!</button>`
        let columns = [
            { label: "Project Name", id: "Project", fieldtype: "Data", width: 300 },
            { label: "Notes", id: "Notes", fieldtype: "Data", width: 300 },
            { label: "Customer", id: "Customer", fieldtype: "Link", width: 200 },
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
            renderCell: function(row, column, data, index) {
                // Check if the current column is the Actions column
                if (column.id === 'Actions') {
                    // Use a custom formatter function to create the button
                    return buttonFormatter(data);
                } else {
                    // For other columns, just return the data
                    return data;
                }
            }
        });

        // Move the table to the center and add margin on top
        $(wrapper.querySelector('#datatable-wrapper')).css({
            'margin-top': '50px',
            'text-align': 'center',
            'margin-left': '50px',
        });
    }

    
};*/

/*frappe.pages['project-action-panel'].on_page_load = function(wrapper) {
    var page = frappe.ui.make_app_page({
        parent: wrapper,
        title: 'project-action-panel',
        single_column: true
    });

    //set up our empty datatable
    let el = document.querySelector('.layout-main-section')
    let button_formatter = (value) => `<button style="display: block; margin: 0 auto;" onclick="alert('This is ${value}')">Action!</button>`
    let columns = ['Project Name', 'Notes', 'Customer', 
        {name: "Action Button", focusable: false, format: button_formatter }]
    let datatable = new frappe.DataTable(el, { columns: columns, data: [], layout: "fluid" });

    //use regular ajax api methods to fetch document data, then refresh
    frappe.db.get_list("Project", 
        {fields: ['project_name','notes' , 'customer']}
    ).then((r) => { 
        let data = r.map(Object.values)
        datatable.refresh(data, columns) 
    })
}*/

frappe.pages['project-action-panel'].on_page_load = function(wrapper) {
    // Ensure wrapper is defined
    if (!wrapper) {
        console.error("Wrapper is not defined.");
        return;
    }

    // Set the title of the page
    if (wrapper.page) {
        wrapper.page.set_title('<span style="font-size: 14px;">Project Action Panel</span>');
    }

    // Fetch project data from the server
    frappe.call({
        method: "phamos.phamos.page.project_action_panel.project_action_panel.fetch_projects",
        callback: function(r) {
            if (r.message) {
                // Render DataTable with the fetched data
                renderDataTable(wrapper, r.message);
            } else {
                // Handle error or empty data
                console.log("No project data found");
            }
        }
    });

    // Function to render DataTable
    function renderDataTable(wrapper, projectData) {
        // Ensure wrapper is defined
        if (!wrapper) {
            console.error("Wrapper is not defined.");
            return;
        }

        // Define columns for the report view
        //let button_formatter = (value) => `<button style="display: block; margin: 0 auto;" onclick="alert('This is ${value}')">Action!</button>`
        let button_formatter = (value) => `<button style="width: 80px; height: 23px; background-color: #007bff; color: white; display: block; margin: 0 auto;" onclick="alert('This is ${value}')">Start</button>`;

        let columns = [
            { label: "Project Name", id: "Project", fieldtype: "Data", width: 300 },
            { label: "Notes", id: "Notes", fieldtype: "Data", width: 300 },
            { label: "Customer", id: "Customer", fieldtype: "Link", width: 200 },
            {name: "Start", focusable: false, format: button_formatter }];

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