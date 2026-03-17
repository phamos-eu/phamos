import frappe
from frappe.custom.doctype.custom_field.custom_field import create_custom_field
from frappe.custom.doctype.property_setter.property_setter import make_property_setter


def execute():
    frappe.reload_doc("Setup", "doctype", "project")
    create_custom_field("project",
	    dict(fieldname="phamos_section_break", label="phamos",
		fieldtype="Section Break", insert_before="naming_series"))

    create_custom_field("project",
		dict(fieldname="planned_hours", label="Planned Hours",
		fieldtype="Data",
		insert_after="phamos_section_break"))
    
    create_custom_field("project",
    	dict(fieldname="phamos_columns_break", label="",
		fieldtype="Column Break", insert_after="planned_hours"
    ))

    create_custom_field("project",
        dict(fieldname="percent_billable", label="Percent Billable",
		fieldtype="Select",
		options="\n0\n25\n50\n75\n100",insert_after="phamos_columns_break",default = 100
		))

    create_custom_field("project",
	    dict(fieldname="phamos_section_break_end", label="",
		fieldtype="Section Break", insert_after="percent_billable"))
    
    create_custom_field("project",
	    dict(fieldname="phamos_column_break_end", label="",
		fieldtype="Column Break", insert_after="percent_billable"))
    
    create_custom_field(
        "Project",
        dict(
            fieldname="task_in_timesheet_record",    
            label="Task in timesheet record",       
            fieldtype="Select",                     
            options="\nTask is hidden\nTask is optional\nTask is mandatory",   
            insert_after="phamos_column_break_end",   
            default="Task is hidden",
            description="Select the visibility requirement for the task in the timesheet record. Choose 'Task is hidden' to hide the task field, 'Task is optional' to allow the selection of a task, or 'Task is mandatory' to require a task selection."
        )
    )
    
	
    