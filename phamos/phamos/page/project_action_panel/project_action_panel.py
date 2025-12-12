import frappe
import frappe
import pytz
from frappe.utils import get_datetime
from frappe import _
from frappe.model.document import Document
from frappe.utils import cstr, now_datetime, time_diff_in_seconds, get_datetime,time_diff,today
from frappe.utils.data import add_to_date,format_duration, time_diff_in_seconds
import datetime
from datetime import datetime, timedelta
from collections import defaultdict
from frappe.utils import strip_html
from frappe.query_builder import Field, Case, Order, DocType, functions as fn
from frappe.query_builder.functions import Concat, Max, Sum, Round, Coalesce, IfNull
from frappe.utils import getdate, nowdate, get_first_day, get_last_day, add_days, add_months


@frappe.whitelist()
def create_timesheet_record(project_name,  customer, from_time, expected_time, goal,task=None):
    try:
        employee_name = frappe.db.get_value("Employee", {"user_id": frappe.session.user}, "name")
        activity_type = frappe.db.get_value("Employee", {"user_id": frappe.session.user}, "activity_type")
        customer = frappe.db.get_value("Customer", {"customer_name": customer}, "name")
        project = frappe.db.get_value("Project", {"project_name": project_name}, "name")
        
        if employee_name:
            after_1_minute = add_to_date(from_time, seconds=10, as_string=True)
            
            timesheet_record = frappe.new_doc('Timesheet Record')
            timesheet_record.project = project
            timesheet_record.task=task
            timesheet_record.customer = customer
            timesheet_record.from_time = after_1_minute
            timesheet_record.expected_time = expected_time
            timesheet_record.goal = goal
            timesheet_record.employee = employee_name
            timesheet_record.activity_type = activity_type
            timesheet_record.append("item", {
                "from_time": from_time
            })

            timesheet_record.save()
            frappe.db.commit()
            
            # Return the saved timesheet record
            return timesheet_record
        else:
            frappe.throw("Employee not found for the current user.")
    except Exception as e:
        # Handle errors here, you can log the error for further investigation
        frappe.log_error(frappe.get_traceback(), "Timesheet Record Creation Error")
        
        # Return None or an error message to indicate the failure
        return None
    
@frappe.whitelist()
def update_to_time(name):
    try:
        doc = frappe.get_doc("Timesheet Record", name)

        for row in doc.item:
            if not row.to_time:
                row.to_time = now_datetime()
                new_row = doc.append("item", {})
                new_row.from_time = now_datetime()
                break 

        doc.save()
        frappe.db.commit()

        return {
            "status": "success",
            "message": "to_time updated",
            "timesheet": name
        }

    except Exception as e:
        frappe.log_error(frappe.get_traceback(), "Timesheet Record Update Error")
        return {
            "status": "error",
            "message": "Error updating Timesheet Record"
        }

@frappe.whitelist()
def close_open_row_and_add_break(name):
    try:
        doc = frappe.get_doc("Timesheet Record", name)
        current_time = now_datetime()
        new_row = None
        previous_from_time = None
        previous_to_time = None

        if len(doc.item) >= 1:
            previous_from_time = doc.item[-1].from_time


        for idx, row in enumerate(doc.item):
            if not row.to_time:
                row.to_time = current_time
                previous_to_time = row.to_time
                new_row = doc.append("item", {})
                new_row.from_time = current_time
                break

        if not new_row:
            return {
                "status": "error",
                "message": "No open row found to close."
            }

        doc.save()
        frappe.db.commit()

        return {
            "status": "success",
            "message": "Break row created",
            "new_row_name": new_row.name,
            "previous_from_time": previous_from_time,
            "previous_to_time": previous_to_time,
        }

    except Exception as e:
        frappe.log_error(frappe.get_traceback(), "Timesheet Record Break Creation Error")
        return {
            "status": "error",
            "message": f"Error creating break row: {str(e)}"
        }

@frappe.whitelist()
def get_assigned_projects(doctype, txt, searchfield, start, page_len, filters):
    user = frappe.session.user
    
    projects = frappe.db.sql("""
        SELECT DISTINCT p.name, p.project_name
        FROM `tabProject` p
        JOIN `tabToDo` t ON t.reference_name = p.name
        WHERE t.owner = %s
        AND t.reference_type = 'Project'
        AND (p.name LIKE %s OR p.project_name LIKE %s)
        ORDER BY p.project_name ASC
        LIMIT %s OFFSET %s
    """, (user, f"%{txt}%", f"%{txt}%", page_len, start))
    
    return projects

    
@frappe.whitelist()
def is_task_running(name):
    # Get all child rows in correct order
    rows = frappe.db.sql("""
        SELECT name, to_time
        FROM `tabTimesheet Record Item`
        WHERE parent = %s
        ORDER BY creation ASC
    """, name, as_dict=True)

    if not rows:
        return {"is_running": False}

    # Find last open (missing to_time)
    for idx, row in enumerate(rows, start=1):
        if not row.to_time:
            # Odd index (1, 3, 5...) → task running ⏸️
            # Even index (2, 4, 6...) → task paused ▶️
            is_running = (idx % 2 != 0)
            return {"is_running": is_running}

    # If no missing to_time → considered paused
    return {"is_running": False}


@frappe.whitelist()
def create_and_submit_timesheet( project_name=None, 
    percent_billable=None, 
    result=None, 
    activity_type=None, 
    from_time=None, 
    expected_time=None, 
    goal=None, 
    to_time=None):
    try:
        ts = frappe.new_doc("Timesheet Record")
        ts.project = project_name
        ts.activity_type = activity_type
        ts.percent_billable = percent_billable
        ts.goal = goal
        ts.expected_time = expected_time
        ts.result = result

        # Parent field set
        ts.from_time = from_time
        ts.to_time = to_time

        # Add child row
        ts.append("item", {
            "from_time": from_time,
            "to_time": ts.to_time
        })

        # ✅ Calculate duration for each row and sum it up
        total_duration = 0
        for row in ts.item:
            if row.from_time and row.to_time:
                duration_seconds = time_diff_in_seconds(row.to_time, row.from_time)
                row.duration = duration_seconds
                total_duration += duration_seconds

        # ✅ Set total duration in parent actual_time
        ts.actual_time = total_duration

        # ✅ Mark as complete before submit
        ts.status = "Complete"

        ts.insert(ignore_permissions=True)
        ts.save()
        ts.submit()

        return {
            "status": "success",
            "message": f"Timesheet Record {ts.name} created and submitted successfully",
            "name": ts.name
        }

    except Exception as e:
        frappe.log_error(frappe.get_traceback(), "Create Timesheet Record Error")
        return {
            "status": "error",
            "message": str(e)
        }

@frappe.whitelist()
def update_to_time(name):
    try:
        doc = frappe.get_doc("Timesheet Record", name)

        for row in doc.item:
            if not row.to_time:
                row.to_time = now_datetime()
                new_row = doc.append("item", {})
                new_row.from_time = now_datetime()
                break 

        doc.save()
        frappe.db.commit()

        return {
            "status": "success",
            "message": "to_time updated",
            "timesheet": name
        }

    except Exception as e:
        frappe.log_error(frappe.get_traceback(), "Timesheet Record Update Error")
        return {
            "status": "error",
            "message": "Error updating Timesheet Record"
        }

@frappe.whitelist()
def close_open_row_and_add_break(name):
    try:
        doc = frappe.get_doc("Timesheet Record", name)
        current_time = now_datetime()
        new_row = None
        previous_from_time = None
        previous_to_time = None

        if len(doc.item) >= 1:
            previous_from_time = doc.item[-1].from_time


        for idx, row in enumerate(doc.item):
            if not row.to_time:
                row.to_time = current_time
                previous_to_time = row.to_time
                new_row = doc.append("item", {})
                new_row.from_time = current_time
                break

        if not new_row:
            return {
                "status": "error",
                "message": "No open row found to close."
            }

        doc.save()
        frappe.db.commit()

        return {
            "status": "success",
            "message": "Break row created",
            "new_row_name": new_row.name,
            "previous_from_time": previous_from_time,
            "previous_to_time": previous_to_time,
        }

    except Exception as e:
        frappe.log_error(frappe.get_traceback(), "Timesheet Record Break Creation Error")
        return {
            "status": "error",
            "message": f"Error creating break row: {str(e)}"
        }

@frappe.whitelist()
def get_assigned_projects(doctype, txt, searchfield, start, page_len, filters):
    user = frappe.session.user
    
    projects = frappe.db.sql("""
        SELECT DISTINCT p.name, p.project_name
        FROM `tabProject` p
        JOIN `tabToDo` t ON t.reference_name = p.name
        WHERE t.owner = %s
        AND t.reference_type = 'Project'
        AND (p.name LIKE %s OR p.project_name LIKE %s)
        ORDER BY p.project_name ASC
        LIMIT %s OFFSET %s
    """, (user, f"%{txt}%", f"%{txt}%", page_len, start))
    
    return projects

    
@frappe.whitelist()
def is_task_running(name):
    try:
        doc = frappe.get_doc("Timesheet Record", name)
        for row in reversed(doc.item):
            if not row.to_time:
                return {"is_running": True}
        return {"is_running": False}
    except:
        return {"is_running": False}


@frappe.whitelist()
def get_employee_leaves():
    today = getdate(nowdate())

    # ✅ Current year start
    year_start = get_first_day(today.replace(month=1, day=1))

    # ✅ Next year  end
    next_year = today.year + 1
    year_end = get_last_day(getdate(f"{next_year}-12-31"))

    # Final range (current + next year)
    start = year_start
    end = year_end

    leaves = frappe.get_all(
        "Leave Application",
        filters={
            "status": "Approved",
            "from_date": ("<=", end),
            "to_date": (">=", start),
        },
        fields=[
            "employee_name",
            "from_date",
            "to_date",
            "leave_type",
            "half_day",
            "half_day_date",
            "available_from_time",
            "available_to_time"
        ]
    )

    events = []
    for l in leaves:
        description = f"{l.employee_name} ({l.leave_type})"

        if l.half_day and l.from_date != l.to_date:
            # LEFT SIDE: from_date → (half_day_date - 1)
            if l.from_date < l.half_day_date:
                events.append({
                    "title": description,
                    "start": l.from_date,
                    "end": l.half_day_date,  # exclude half_day_date
                    "color": "#6b9eeb"  # blue
                })

            # HALF-DAY: only half_day_date
            hd_desc = description
            if l.available_from_time and l.available_to_time:
                hd_desc += f" [{l.available_from_time} - {l.available_to_time}]"

            events.append({
                "title": hd_desc,
                "start": l.half_day_date,
                "end": add_days(l.half_day_date, 1),
                "color": "#ff69b4"  # pink
            })

            # RIGHT SIDE: (half_day_date + 1) → to_date
            if l.half_day_date < l.to_date:
                events.append({
                    "title": description,
                    "start": add_days(l.half_day_date, 1),
                    "end": add_days(l.to_date, 1),
                    "color": "#6b9eeb"  # blue
                })

        else:
            # normal case (full day or single day half-day)
            color = "#6b9eeb"  # blue by default
            if l.half_day:
                color = "#ff69b4"
                if l.available_from_time and l.available_to_time:
                    description += f" [{l.available_from_time} - {l.available_to_time}]"

            events.append({
                "title": description,
                "start": l.from_date if not l.half_day else l.half_day_date or l.from_date,
                "end": add_days(l.to_date, 1),
                "color": color
            })

    return events


@frappe.whitelist()
def get_timesheet_records_by_date(selected_date=None):
    user = frappe.session.user

    user_tz = frappe.db.get_value("User", user, "time_zone") \
        or frappe.utils.get_system_settings("time_zone") \
        or "Asia/Karachi"

    germany_tz = "Europe/Berlin"
    user_zone = pytz.timezone(user_tz)
    germany_zone = pytz.timezone(germany_tz)

    # 🔹 if not selected date then get today date
    if not selected_date:
        selected_date = frappe.utils.now_datetime().date()
    else:
        selected_date = datetime.strptime(selected_date, "%Y-%m-%d").date()

    # Records fetch
    records = frappe.db.sql("""
        SELECT 
            td.name, td.from_time, td.to_time, td.hours, td.task, td.project, t.creation
        FROM `tabTimesheet Detail` td
        INNER JOIN `tabTimesheet` t ON td.parent = t.name
        WHERE t.employee = (
            SELECT employee FROM `tabEmployee` WHERE user_id = %s LIMIT 1
        )
    """, (user,), as_dict=True)

    date_records = []
    for rec in records:
        from_dt = germany_zone.localize(get_datetime(rec["from_time"]))
        to_dt   = germany_zone.localize(get_datetime(rec["to_time"]))

        rec["from_time_user"] = from_dt.astimezone(user_zone).strftime("%H:%M")
        rec["to_time_user"]   = to_dt.astimezone(user_zone).strftime("%H:%M")

        rec["from_time_germany"] = from_dt.strftime("%H:%M")
        rec["to_time_germany"]   = to_dt.strftime("%H:%M")

        # ✅ Filter records for selected date
        if (from_dt.astimezone(user_zone).date() == selected_date
            or from_dt.date() == selected_date):
            date_records.append(rec)

    # Slots (07:00–22:00) in user timezone
    slots = []
    for h in range(7, 22):
        dt_user = user_zone.localize(get_datetime(f"{selected_date} {h:02d}:00:00"))
        dt_germ = dt_user.astimezone(germany_zone)

        slots.append({
            "user": dt_user.strftime("%H:%M"),
            "germany": dt_germ.strftime("%H:%M")
        })

    return {
        "user_timezone": user_tz,
        "records": date_records,
        "slots": slots
    }



@frappe.whitelist()
def get_team_holidays():
    today = getdate(nowdate())

    # ✅ Current year ka start
    from_date = get_first_day(today.replace(month=1, day=1))

    # ✅ Next year ka end
    next_year = today.year + 1
    to_date = get_last_day(getdate(f"{next_year}-12-31"))

    grouped = defaultdict(list)

    employees = frappe.get_all("Employee", fields=["name", "employee_name", "holiday_list"])
    
    for emp in employees:
        if not emp.holiday_list:
            continue

        holidays = frappe.get_all(
            "Holiday",
            filters={
                "parent": emp.holiday_list,
                "holiday_date": ["between", [from_date, to_date]]
            },
            fields=["holiday_date", "description"]
        )

        for h in holidays:
            clean_desc = strip_html(h.description or "Holiday")
            grouped[(h.holiday_date, clean_desc)].append(emp.employee_name)

    events = []
    for (holiday_date, desc), emps in grouped.items():
        events.append({
            "title": f"{desc}: <br> {', '.join(emps)}",
            "start": holiday_date,
            "allDay": True,
            "color": "#28a745",
            "description": desc
        })

    return events


@frappe.whitelist()
def create_and_submit_timesheet( project_name=None, 
    percent_billable=None, 
    result=None, 
    activity_type=None, 
    from_time=None, 
    expected_time=None, 
    goal=None, 
    to_time=None):
    try:
        # ✅ Validate before creating record
        if from_time and to_time and get_datetime(to_time) < get_datetime(from_time):
            frappe.throw(_("To Time cannot be earlier than From Time. Record not saved."))

        ts = frappe.new_doc("Timesheet Record")
        ts.project = project_name
        ts.activity_type = activity_type
        ts.percent_billable = percent_billable
        ts.goal = goal
        ts.expected_time = expected_time
        ts.result = result

        # Parent field set
        ts.from_time = from_time
        ts.to_time = to_time

        # Add child row
        ts.append("item", {
            "from_time": from_time,
            "to_time": to_time
        })

        # ✅ Calculate total duration
        total_duration = 0
        for row in ts.item:
            if row.from_time and row.to_time:
                if get_datetime(row.to_time) < get_datetime(row.from_time):
                    frappe.throw(_("Row #{0}: To Time cannot be earlier than From Time. Record not saved.").format(row.idx))
                row.duration = time_diff_in_seconds(row.to_time, row.from_time)
                total_duration += row.duration

        ts.actual_time = total_duration
        ts.status = "Complete"

        ts.insert(ignore_permissions=True)
        ts.submit()

        return {
            "status": "success",
            "message": f"Timesheet Record {ts.name} created and submitted successfully",
            "name": ts.name
        }

    except Exception as e:
        frappe.log_error(frappe.get_traceback(), "Create Timesheet Record Error")
        return {
            "status": "error",
            "message": str(e)
        }

@frappe.whitelist()
def update_and_submit_timesheet_record(name, to_time, percent_billable, activity_type, result, task=None):
    try:
        # Retrieve the Timesheet Record document
        doc = frappe.get_doc("Timesheet Record", name)

        # Close last open row if exists
        if doc.item:
            for row in reversed(doc.item):
                if row.from_time and not row.to_time:
                    # ✅ Validate before assigning
                    if get_datetime(to_time) < get_datetime(row.from_time):
                        frappe.throw(_("To Time cannot be earlier than From Time. Update aborted."))
                    row.to_time = to_time
                    break

        # Calculate durations & validate
        for row in doc.item:
            if row.from_time and row.to_time:
                if get_datetime(row.to_time) < get_datetime(row.from_time):
                    frappe.throw(_("Row #{0}: To Time cannot be earlier than From Time. Update aborted.").format(row.idx))
                row.duration = time_diff_in_seconds(row.to_time, row.from_time)

        # Update parent fields
        if doc.item:
            first_row = doc.item[0]
            doc.from_time = first_row.from_time
            doc.to_time = first_row.to_time
            doc.actual_time = first_row.duration or 0

        doc.task = task
        doc.activity_type = activity_type
        doc.result = result
        doc.percent_billable = percent_billable

        # ✅ Final validation before any save or submit
        if doc.from_time and doc.to_time and get_datetime(doc.to_time) < get_datetime(doc.from_time):
            frappe.throw(_("To Time cannot be earlier than From Time. Update aborted."))

        doc.save()
        doc.submit()

        # --- Create alternative records (3rd, 5th, etc.) ---
        for i in range(2, len(doc.item), 2):  # start from 3rd row (index 2)
            alt_row = doc.item[i]

            # ✅ Skip invalid alternate rows
            if alt_row.from_time and alt_row.to_time and get_datetime(alt_row.to_time) < get_datetime(alt_row.from_time):
                continue

            new_doc = frappe.new_doc("Timesheet Record")

            # Copy parent fields from original
            for field in ["project", "customer", "task", "goal", "expected_time", "activity_type", "result", "percent_billable"]:
                new_doc.set(field, doc.get(field))

            # Parent times from selected row
            new_doc.from_time = alt_row.from_time
            new_doc.to_time = alt_row.to_time
            new_doc.actual_time = alt_row.duration or 0

            # Copy all item rows
            for original_row in doc.item:
                new_doc.append("item", {
                    "from_time": original_row.from_time,
                    "to_time": original_row.to_time,
                    "duration": original_row.duration or 0
                })

            new_doc.insert(ignore_permissions=True)
            new_doc.submit()

        return {"timesheet_name": doc.name}

    except Exception as e:
        frappe.log_error(frappe.get_traceback(), "Timesheet Record Update and Submit Error")
        return f"Error: {str(e)}"

@frappe.whitelist(allow_guest=True)
def get_employee_and_project(project_name):
    employee = frappe.db.get_value("Employee", {"user_id": frappe.session.user}, "name")
    project = frappe.db.get_value("Project", {"project_name": project_name}, "name")
    timesheet_record = frappe.db.get_value("Timesheet Record", {"project": project,"employee":employee,"docstatus":0}, "name")
    return employee,project,timesheet_record

@frappe.whitelist()
def check_draft_timesheet_record():
    try:
        # Current logged-in employee
        employee_name = frappe.db.get_value(
            "Employee", {"user_id": frappe.session.user}, "name"
        )

        # Draft Timesheet Records + child table rows
        draft_records = frappe.db.sql("""
            SELECT 
                tsr.name AS timesheet_record_draft,
                tsri.from_time,
                tsri.to_time
            FROM `tabTimesheet Record` tsr
            LEFT JOIN `tabTimesheet Record Item` tsri
                ON tsr.name = tsri.parent
            WHERE tsr.employee = %(employee)s 
              AND tsr.docstatus = 0
        """, {"employee": employee_name}, as_dict=True)

        if not draft_records:
            return []

        # Check for running timer rows (from_time filled, to_time empty)
        for row in draft_records:
            if row.from_time and not row.to_time:
                frappe.throw("Please pause current record before starting a new one.")

        # Return only draft record names
        return [{"timesheet_record_draft": r["timesheet_record_draft"]} for r in draft_records]

    except Exception as e:
        frappe.log_error(f"Error in check_draft_timesheet_record: {e}")
        return None

    
@frappe.whitelist()
def fetch_projects():
    # Get Employee linked to current user
    employee_name = frappe.db.get_value("Employee", {"user_id": frappe.session.user}, "name")
    if not employee_name:
        frappe.throw("Employee not found for the current user.")

    # Define DocTypes
    Project = DocType("Project")
    Timesheet = DocType("Timesheet")
    TimesheetDetail = DocType("Timesheet Detail")
    Customer = DocType("Customer")
    TimesheetRecord = DocType("Timesheet Record")
    ToDo = DocType("ToDo")

    # Subqueries for calculations
    spent_hours_draft = (
        frappe.qb.from_(Timesheet)
        .select(Coalesce(Sum(Timesheet.total_hours), 0))
        .where(
            (Timesheet.docstatus == 0)
            & (Timesheet.employee == employee_name)
            & (Timesheet.name.isin(
                frappe.qb.from_(TimesheetDetail)
                .select(TimesheetDetail.parent)
                .where(TimesheetDetail.project == Project.name)
            ))
        )
    )

    spent_hours_submitted = (
        frappe.qb.from_(Timesheet)
        .select(Coalesce(Sum(Timesheet.total_hours), 0))
        .where(
            (Timesheet.docstatus == 1)
            & (Timesheet.employee == employee_name)
            & (Timesheet.name.isin(
                frappe.qb.from_(TimesheetDetail)
                .select(TimesheetDetail.parent)
                .where(TimesheetDetail.project == Project.name)
            ))
        )
    )

    latest_timesheet_record = (
        frappe.qb.from_(TimesheetRecord)
        .select(Max(TimesheetRecord.name))
        .where(
            (TimesheetRecord.project == Project.name)
            & (TimesheetRecord.employee == employee_name)
            & (TimesheetRecord.docstatus == 0)
        )
    )

    latest_task = (
        frappe.qb.from_(TimesheetRecord)
        .select(TimesheetRecord.task)
        .where(TimesheetRecord.name == latest_timesheet_record)
    )

    last_timesheet_update = (
        frappe.qb.from_(TimesheetRecord)
        .select(Max(TimesheetRecord.creation))
        .where(
            (TimesheetRecord.project == Project.name)
            & (TimesheetRecord.employee == employee_name)
        )
    )

    # Handling Customer Description (Replacing CASE)
    customer_desc_query = IfNull(Customer.customer_name, Customer.name)

    # Main Query
    query = (
        frappe.qb.from_(Project)
        .left_join(Customer).on(Customer.name == Project.customer)
        .select(
            Project.percent_billable,
            Project.name.as_("name"),
            Project.planned_hours,
            Project.task_in_timesheet_record,
            Project.status,
            Project.notes,
            Project.project_name,
            Concat(Project.name, " - ", Project.project_name).as_("project_desc"),
            Round(spent_hours_draft, 3).as_("spent_hours_draft"),
            Round(spent_hours_submitted, 3).as_("spent_hours_submitted"),
            Customer.name.as_("customer"),
            customer_desc_query.as_("customer_desc"),
            latest_timesheet_record.as_("timesheet_record"),
            latest_task.as_("task"),
            last_timesheet_update.as_("last_timesheet_update"),
        )
        .where(
            frappe.qb.from_(ToDo)
            .select(Max(ToDo.reference_name))
            .where(
                (ToDo.status == "Open")
                & (ToDo.reference_name == Project.name)
                & (ToDo.allocated_to == frappe.session.user)
            ).isnotnull()
        )
        .orderby(Coalesce(last_timesheet_update, "1970, 1, 1"), order=Order.desc)
        
    )
    # Execute query
    projects = query.run(as_dict=True)
    return projects

@frappe.whitelist()
def fetch_all_projects():
    project = frappe.qb.DocType("Project")
    customer = frappe.qb.DocType("Customer")
    todo = frappe.qb.DocType("ToDo")

    customer_subquery = (
        frappe.qb.from_(customer)
        .select(
            (
                Case()
                .when(customer.name != customer.customer_name, Concat(customer.name, " - ", customer.customer_name))
                .else_(customer.customer_name)
            ).as_("customer_desc")
        )
        .where(customer.name == project.customer)
        )

    todo_subquery = (
        frappe.qb.from_(todo)
        .select(todo.reference_name)
        .where(
            (todo.status == "Open") &
            (todo.allocated_to == frappe.session.user)
        )
        )

    projects = (
        frappe.qb.from_(project)
        .select(
            project.name.as_("name"),
            project.status.as_("status"),
            project.project_name.as_("project_name"),
            Concat(project.name, " - ", project.project_name).as_("project_desc"),
            project.customer.as_("customer"),
            customer_subquery.as_("customer_desc")
        )
        .where(
            (project.status == "Open") &
            (project.name.notin(todo_subquery)) 
        )
        ).run(as_dict=True)
 
    # Return project data
    return projects

@frappe.whitelist()
def get_permitted_cards(dashboard_name):
	permitted_cards = []
	dashboard = frappe.get_doc("Dashboard", dashboard_name)
	for card in dashboard.cards:
		if frappe.has_permission("Number Card", doc=card.card):
			permitted_cards.append(card)
	return permitted_cards

@frappe.whitelist()
def get_project_count():
    count_projects = frappe.db.sql("""
        SELECT count(p.name) AS total_projects
        FROM `tabProject` p
        WHERE (SELECT max(reference_name) FROM `tabToDo` td WHERE td.status = "Open" and td.reference_name = p.name and td.allocated_to = %(user)s) IS NOT NULL
    """, {"user": frappe.session.user}, as_dict=True)

    return {
        "value": count_projects[0].get('total_projects') if count_projects else 0 , # assuming you want to return the count of projects meeting certain conditions,
        "fieldtype": "Int",
        #"count_projects": count_projects[0].get('total_projects') if count_projects else 0  # assuming you want to return the count of projects meeting certain conditions
    }

@frappe.whitelist()
def get_project_count_all():
    count_projects = frappe.db.sql("""
        SELECT count(p.name) AS total_projects
        FROM `tabProject` p
    """, {}, as_dict=True)

    return {
        "value": count_projects[0].get('total_projects') if count_projects else 0 , # assuming you want to return the count of projects meeting certain conditions,
        "fieldtype": "Int",
        #"count_projects": count_projects[0].get('total_projects') if count_projects else 0  # assuming you want to return the count of projects meeting certain conditions
    }

@frappe.whitelist()
def total_hours_worked_today():
    # --- Get employee ---
    employee_name = frappe.db.get_value("Employee", {"user_id": frappe.session.user}, "name")

    # --- User timezone ---
    user_tz = frappe.db.get_value("User", frappe.session.user, "time_zone") or "UTC"
    tz = pytz.timezone(user_tz)

    # --- Today in user timezone ---
    now = now_datetime().astimezone(tz)
    today_date = now.date()
    today_start = tz.localize(datetime.combine(today_date, datetime.min.time()))
    today_end = tz.localize(datetime.combine(today_date, datetime.max.time()))

    # --- Fetch timesheet records that could overlap today ---
    records = frappe.get_all(
        "Timesheet Record",
        filters={
            "employee": employee_name,
            "docstatus": ["!=", 2],
            "from_time": ["<=", today_end],
            "to_time": [">=", today_start]
        },
        fields=["from_time", "to_time", "actual_time", "percent_billable", "timesheet_record_color"]
    )

    total_actual_seconds = 0
    total_billable_seconds = 0
    green = amber = red = 0

    for rec in records:
        rec_start = get_datetime(rec.from_time).astimezone(tz)
        rec_end = get_datetime(rec.to_time).astimezone(tz)

        # Calculate overlap with today
        overlap_start = max(rec_start, today_start)
        overlap_end = min(rec_end, today_end)

        if overlap_start < overlap_end:
            duration_seconds = time_diff_in_seconds(overlap_end, overlap_start)
            total_actual_seconds += duration_seconds

            percent = float(rec.percent_billable or 0)
            total_billable_seconds += duration_seconds * percent / 100

        # Count color
        if rec.timesheet_record_color == "Green":
            green += 1
        elif rec.timesheet_record_color == "Amber":
            amber += 1
        elif rec.timesheet_record_color == "Red":
            red += 1

    total = green + amber + red
    green_pct = round((green / total) * 100, 2) if total else 0
    amber_pct = round((amber / total) * 100, 2) if total else 0
    red_pct = round((red / total) * 100, 2) if total else 0

    # Format durations
    actual_time_str = str(format_duration(total_actual_seconds))[:9] if total_actual_seconds else 0
    total_billable_time_str = str(format_duration(total_billable_seconds))[:10] if total_billable_seconds else 0

    return {
        "value": actual_time_str,
        "fieldtype": "Float",
        "billable": total_billable_time_str,
        "green": green_pct,
        "amber": amber_pct,
        "red": red_pct
    }


@frappe.whitelist()
def total_hours_worked_in_this_week():
    employee_name = frappe.db.get_value("Employee", {"user_id": frappe.session.user}, "name")
    today_date = datetime.today().date()
    start_of_week = today_date - timedelta(days=today_date.weekday())
    end_of_week = start_of_week + timedelta(days=6)

    TimesheetRecord = DocType("Timesheet Record")
    count_time = (
        frappe.qb.from_(TimesheetRecord)
        .select(
            fn.Sum(TimesheetRecord.actual_time).as_("total_actual_time"),
            fn.Sum(TimesheetRecord.actual_time * TimesheetRecord.percent_billable / 100).as_("total_billable_time")
        )
        .where(
            (TimesheetRecord.employee == employee_name)
            & (fn.Date(TimesheetRecord.creation).between(start_of_week, end_of_week))
            & (TimesheetRecord.docstatus != 2)
        )
        .run(as_dict=True)
    )

    # --- Color counts from timesheet_record_color field ---
    records = frappe.get_all(
        "Timesheet Record",
        filters={
            "employee": employee_name,
            "docstatus": ["!=", 2],
            "creation": ["between", [
                datetime.combine(start_of_week, datetime.min.time()),
                datetime.combine(end_of_week, datetime.max.time())
            ]]
        },
        fields=["timesheet_record_color"]
    )

    green = amber = red = 0
    for rec in records:
        if rec.timesheet_record_color == "Green":
            green += 1
        elif rec.timesheet_record_color == "Amber":
            amber += 1
        elif rec.timesheet_record_color == "Red":
            red += 1

    total = green + amber + red
    green_pct = round((green / total) * 100, 2) if total else 0
    amber_pct = round((amber / total) * 100, 2) if total else 0
    red_pct = round((red / total) * 100, 2) if total else 0

    if count_time and count_time[0].total_actual_time:
        total_actual_time_str = str(format_duration(count_time[0].total_actual_time))[:10]
        total_billable_time = count_time[0].total_billable_time or 0
        total_billable_time_str = str(format_duration(total_billable_time))[:10] if total_billable_time else 0
        return {
            "value": total_actual_time_str,
            "fieldtype": "Float",
            "billable": total_billable_time_str,
            "green": green_pct,
            "amber": amber_pct,
            "red": red_pct
        }
    return {"value": 0, "fieldtype": "Float", "billable": 0, "green": 0, "amber": 0, "red": 0}


@frappe.whitelist()
def total_hours_worked_in_this_month():
    employee_name = frappe.db.get_value("Employee", {"user_id": frappe.session.user}, "name")
    today_date = datetime.today().date()

    # Start & end of current month
    start_of_month = today_date.replace(day=1)
    if start_of_month.month == 12:
        next_month = start_of_month.replace(year=start_of_month.year + 1, month=1)
    else:
        next_month = start_of_month.replace(month=start_of_month.month + 1)
    end_of_month = next_month - timedelta(days=1)

    TimesheetRecord = DocType("Timesheet Record")
    count_time = (
        frappe.qb.from_(TimesheetRecord)
        .select(
            fn.Sum(TimesheetRecord.actual_time).as_("total_actual_time"),
            fn.Sum(TimesheetRecord.actual_time * TimesheetRecord.percent_billable / 100).as_("total_billable_time")
        )
        .where(
            (TimesheetRecord.employee == employee_name)
            & (fn.Date(TimesheetRecord.creation).between(start_of_month, end_of_month))
            & (TimesheetRecord.docstatus != 2)
        )
        .run(as_dict=True)
    )

    # --- Color counts from timesheet_record_color field ---
    records = frappe.get_all(
        "Timesheet Record",
        filters={
            "employee": employee_name,
            "docstatus": ["!=", 2],
            "creation": ["between", [
                datetime.combine(start_of_month, datetime.min.time()),
                datetime.combine(end_of_month, datetime.max.time())
            ]]
        },
        fields=["timesheet_record_color"]
    )

    green = amber = red = 0
    for rec in records:
        if rec.timesheet_record_color == "Green":
            green += 1
        elif rec.timesheet_record_color == "Amber":
            amber += 1
        elif rec.timesheet_record_color == "Red":
            red += 1

    total = green + amber + red
    green_pct = round((green / total) * 100, 2) if total else 0
    amber_pct = round((amber / total) * 100, 2) if total else 0
    red_pct = round((red / total) * 100, 2) if total else 0

    if count_time and count_time[0].total_actual_time:
        total_actual_time_str = str(format_duration(count_time[0].total_actual_time))[:10]
        total_billable_time = count_time[0].total_billable_time or 0
        total_billable_time_str = str(format_duration(total_billable_time))[:10] if total_billable_time else 0

        return {
            "value": total_actual_time_str,
            "fieldtype": "Float",
            "billable": total_billable_time_str,
            "green": green_pct,
            "amber": amber_pct,
            "red": red_pct
        }
    return {"value": 0, "fieldtype": "Float", "billable": 0, "green": 0, "amber": 0, "red": 0}


def format_duration(duration_in_seconds):
    total_minutes = int(duration_in_seconds) // 60
    hours, minutes = divmod(total_minutes, 60)

    result = []
    if hours:
        result.append(f"{hours} h")
    if minutes or not result:
        result.append(f"{minutes} m")

    return " ".join(result)


@frappe.whitelist()
def set_actual_time(from_time, to_time):
	if from_time and to_time:
		return time_diff_in_seconds(to_time, from_time)
     
@frappe.whitelist()
def self_assign_project(project_name):
    try:
        # Fetch the current employee name linked to the logged-in user
        employee_name = frappe.get_cached_value("Employee", {"user_id": frappe.session.user}, "employee_name")
        
        if not employee_name:
            frappe.throw(_("Employee not found for the current user."))

        # Create a new ToDo record
        todo_record = frappe.new_doc("ToDo")
        todo_record.update({
            "status": "Open",
            "allocated_to": frappe.session.user,
            "description": f"Assignment for Project {project_name}",
            "reference_type": "Project",
            "reference_name": project_name,
            "assigned_by": frappe.session.user,
            "assigned_by_full_name": employee_name
        })
        todo_record.insert()

        return _("Project assignment created successfully.")

    except Exception as e:
        frappe.log_error(frappe.get_traceback(), _("Project Assignment Error"))
        frappe.throw(_("An error occurred while assigning the project. Please check the error logs."))

