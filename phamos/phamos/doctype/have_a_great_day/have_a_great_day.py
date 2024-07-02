# Copyright (c) 2024, phamos.eu and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import cstr, now_datetime, time_diff_in_seconds, get_datetime,time_diff,today
from frappe.utils.data import add_to_date,format_duration, time_diff_in_seconds
from datetime import datetime
from datetime import datetime, timedelta



class HaveaGreatDay(Document):
	pass
		

@frappe.whitelist()
def create_todays_feedback(lookingForward,todaysChallange):
		try:
			employee_name = frappe.db.get_value("Employee", {"user_id": frappe.session.user}, "name")
			settings = frappe.get_single("phamos Settings")
			is_employee_feedback = settings.is_employee_feedback
        	
			
			if employee_name and is_employee_feedback == 1:
				todays_feedback = frappe.new_doc("Have a Great Day")
				todays_feedback.user = frappe.session.user
				todays_feedback.what_are_you_most_looking_forward_today = lookingForward
				todays_feedback.what_challange_will_you_tackle_today = todaysChallange
				todays_feedback.save()
				todays_feedback.update()
				return todays_feedback
			elif not employee_name and is_employee_feedback == 1:
				frappe.throw("Employee not found for the current user.")
			elif is_employee_feedback == 0:
				todays_feedback = frappe.new_doc("Have a Great Day")
				todays_feedback.user = frappe.session.user
				todays_feedback.what_are_you_most_looking_forward_today = lookingForward
				todays_feedback.what_challange_will_you_tackle_today = todaysChallange
				todays_feedback.save()
				todays_feedback.update()
		except Exception as e:
			frappe.log_error(frappe.get_traceback(), "Record Creation Error")
			return None



@frappe.whitelist()
def get_timeframes():
    try:
        # Query to retrieve timeframes from "Dialog Display Timeframes" under "phamos Settings"
        timeframes = frappe.db.get_list("Dialog Display Timeframes",
                                        filters={"parent": "phamos Settings"},
                                        fields=["timeframe"],
										parent_doctype="phamos Settings")
        
        # Extract timeframes from the fetched records
        timeframes = [tf.get("timeframe") for tf in timeframes]
        
        # Join timeframes into a comma-separated string
        timeframes_str = ", ".join(timeframes)
       
        # Return the list of timeframes (you can return the string if needed)
        return timeframes_str
    except Exception as e:
        # Handle exceptions gracefully
        frappe.msgprint(f"Error retrieving timeframes: {str(e)}")

