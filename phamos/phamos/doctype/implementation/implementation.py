# Copyright (c) 2025, phamos.eu and contributors
# For license information, please see license.txt

import frappe
from frappe.model.document import Document
from frappe.query_builder import DocType, get_query_builder
from frappe.utils import today


class Implementation(Document):
	def before_save(self):
		if self.resource_planning_prediction:
			self.resource_planning_prediction.sort(
				key=lambda x: x.month_and_year or "",
			)
			# Re-index after sorting
			for idx, row in enumerate(self.resource_planning_prediction, start=1):
				row.idx = idx
		
		if self.resource_planning:
			self.resource_planning.sort(
				key=lambda x: x.month_and_year or "", reverse=True
			)
			# Re-index after sorting
			for idx, row in enumerate(self.resource_planning, start=1):
				row.idx = idx
		
		self.add_delivered_hrs()
		self.add_resource_planning()
		self.add_status_history()


	def add_delivered_hrs(self):
		if self.sales_order_status_information:
			for row in self.sales_order_status_information:
				total_hours = 0
				delivery_notes = frappe.get_all("Delivery Note Item",filters={"against_sales_order": row.sales_order},fields=["parent", "qty"])
				if len(delivery_notes) == 0:
					row.delivered_total_hrs = 0
					row.remaining_hrs = row.total_hrs - row.delivered_total_hrs 
				else:
					for dn in delivery_notes:
						total_hours += dn.get("qty", 0)
						row.delivered_total_hrs = total_hours
						row.remaining_hrs = row.total_hrs - row.delivered_total_hrs

	def add_resource_planning(self):
		if self.name:
			get_projects = frappe.db.get_all('Project', {'custom_implementation':self.name}, 'name')

			get_project_list = [item.name for item in get_projects]

			if len(get_project_list) == 1:
				total_time_spent = """SELECT DATE_FORMAT(start_date, '%Y-%m') AS month, SUM(tsd.hours) AS total_working_hours FROM  `tabTimesheet` ts JOIN `tabTimesheet Detail` tsd ON ts.name = tsd.parent WHERE ts.docstatus != 2 and tsd.project = '{0}' GROUP BY month ORDER BY month""".format(get_project_list[0])

				total_time = frappe.db.sql(total_time_spent, as_dict=True)

				total_billable_time = """SELECT DATE_FORMAT(start_date, '%Y-%m') AS month, SUM(tsd.billing_hours) AS billable_time FROM  `tabTimesheet` ts JOIN `tabTimesheet Detail` tsd ON ts.name = tsd.parent WHERE ts.docstatus != 2 and tsd.project = '{0}' and tsd.is_billable = 1 GROUP BY month ORDER BY month""".format(get_project_list[0])
				
				billable_time = frappe.db.sql(total_billable_time, as_dict =1)
			elif len(get_project_list) > 1:
				total_time_spent = """SELECT DATE_FORMAT(start_date, '%Y-%m') AS month, SUM(tsd.hours) AS total_working_hours FROM  `tabTimesheet` ts JOIN `tabTimesheet Detail` tsd ON ts.name = tsd.parent WHERE ts.docstatus != 2 and tsd.project in {0} GROUP BY month ORDER BY month""".format(tuple(get_project_list))

				total_time = frappe.db.sql(total_time_spent, as_dict=True)

				total_billable_time = """SELECT DATE_FORMAT(start_date, '%Y-%m') AS month, SUM(tsd.billing_hours) AS billable_time FROM  `tabTimesheet` ts JOIN `tabTimesheet Detail` tsd ON ts.name = tsd.parent WHERE ts.docstatus != 2 and tsd.project in {0} and tsd.is_billable = 1 GROUP BY month ORDER BY month""".format(tuple(get_project_list))
				
				billable_time = frappe.db.sql(total_billable_time, as_dict =1)
			else:
				total_time = [{'month':None, 'total_working_hours':0}]
				billable_time = [{'month':None, 'billable_time':0}]


			if self.resource_planning:
				(self.resource_planning).clear()
				for row in total_time:
					for row1 in billable_time:
						if row['month'] == row1['month']:
							non_billable = float(row.get('total_working_hours')) - float(row1.get('billable_time'))
							if non_billable >0:
								ratio = float(row1.get('billable_time'))/float(non_billable)
							else:
								ratio = 0

							self.append('resource_planning',{
								'month_and_year':row.get('month'),
								'total_time':row.get('total_working_hours'),
								'billable_time_spent':row1.get('billable_time'),
								'non_billable_time_spent':float(row.get('total_working_hours')) - float(row1.get('billable_time')),
								'ratio_of_billable_to_non_billable_time_spent':ratio
								})
			else:
				(self.resource_planning).clear()
				for row in total_time:
					for row1 in billable_time:
						if row['month'] == row1['month']:
							non_billable = float(row.get('total_working_hours')) - float(row1.get('billable_time'))
							if non_billable >0:
								ratio = float(row1.get('billable_time'))/float(non_billable)
							else:
								ratio = 0
							
							self.append('resource_planning',{
								'month_and_year':row.get('month'),
								'total_time':row.get('total_working_hours'),
								'non_billable_time_spent':float(row.get('total_working_hours')) - float(row1.get('billable_time')),
								'billable_time_spent':row1.get('billable_time'),
								'ratio_of_billable_to_non_billable_time_spent':ratio
								})
	

	def add_status_history(self):
		date = today()
		found_today = False

		if self.status_updates:
			for d in self.status_updates:
				if d.date == date:
					d.status_statement = self.status_statement
					d.status = self.status
					d.maturity_level = self.maturity_level
					d.forecast = self.forecast
					d.trend = self.trend
					found_today = True
					break 

		if not found_today:
			self.append("status_updates", {
				"date": date,
				"status_statement": self.status_statement,
				"status": self.status,
				"maturity_level": self.maturity_level,
				"forecast": self.forecast,
				"trend" : self.trend
			})



						

@frappe.whitelist()
def get_financial_history(name, customer = None):
	if not customer:
		return {}
	get_projects = frappe.db.get_all('Project', {'custom_implementation':name}, 'name')
	
	get_project_list = [item.name for item in get_projects]
	
	if len(get_project_list) == 1:
		get_so_hrs = frappe.db.get_value('Sales Order', {'custom_implementation':name,"status":["in",["To Deliver and Bill", "To Deliver","To Bill"]]},'sum(total_qty) as sales_order_qty', as_dict=1)

		get_so_names = frappe.db.get_all("Sales Order",
			filters={"custom_implementation":name, 'status':['in',["To Bill", "To Deliver" ,"To Deliver and Bill"]]},
			fields=["name"])

		get_so_list = [item.name for item in get_so_names]
		
		if get_so_hrs['sales_order_qty'] == None:
			get_so_hrs['sales_order_qty'] = 0
		else:
			pass

		
		if len(get_so_list) == 1:
			get_dn_hrs = frappe.db.sql("""SELECT sum(dni.qty) as dn_qty from `tabDelivery Note` dn join `tabDelivery Note Item` dni on dn.name = dni.parent where dni.against_sales_order = '{0}' and dn.status in ('Completed','To Bill','Draft') """.format(get_so_list[0]), as_list=1)
			if get_dn_hrs[0][0] != None:
				get_so_hrs['dn_qty'] = get_dn_hrs[0][0]
			else:
				get_so_hrs['dn_qty'] = 0
		elif len(get_so_list) > 1:
			get_dn_hrs = frappe.db.sql("""SELECT sum(dni.qty) as dn_qty from `tabDelivery Note` dn join `tabDelivery Note Item` dni on dn.name = dni.parent where dni.against_sales_order in {0} and dn.status in ('Completed','To Bill','Draft') """.format(tuple(get_so_list), get_project_list[0]), as_list=1)
			
			if get_dn_hrs[0][0] != None:
				get_so_hrs['dn_qty'] = get_dn_hrs[0][0]
			else:
				get_so_hrs['dn_qty'] = 0
		else:
			get_so_hrs['dn_qty'] = 0

		
		get_so_hrs['remaining_hrs'] = float(get_so_hrs['sales_order_qty']) - float(get_so_hrs['dn_qty'])
		

		timesheet_hrs = frappe.db.sql("""SELECT sum(td.hours) as timesheet_hrs from `tabTimesheet` t join `tabTimesheet Detail` td on t.name = td.parent where td.is_billable = 1 and t.docstatus = 0 and td.project = '{0}' and td.custom_implementation = '{1}' and t.custom_delivery_note is null """.format(get_project_list[0], name), as_list=1, debug=1)

		if timesheet_hrs[0][0] != None:
			get_so_hrs['timesheet_hrs'] = timesheet_hrs[0][0]
			get_so_hrs['remaining_hrs'] = float(get_so_hrs['sales_order_qty']) - float(get_so_hrs['dn_qty']) - float(timesheet_hrs[0][0])
		else:
			get_so_hrs['timesheet_hrs'] = 0
			get_so_hrs['remaining_hrs'] = float(get_so_hrs['sales_order_qty']) - float(get_so_hrs['dn_qty'])

		get_open_sales_orders = frappe.db.get_value('Sales Order', {'status': ["in", ["To Deliver and Bill", "To Bill"]]}, 'count(name) as open_so')

		if get_open_sales_orders > 0:
			get_so_hrs['open_so'] = 1
		else:
			get_so_hrs['open_so'] = 0

		
		return get_so_hrs
	elif len(get_project_list) > 1:
		get_so_hrs = frappe.db.get_value('Sales Order', {'custom_implementation':name,"status":["in",["To Deliver and Bill","To Deliver", "To Bill"]]},'sum(total_qty) as sales_order_qty', as_dict=1)

		get_so_names = frappe.db.get_all("Sales Order",
			filters={"custom_implementation":name, 'status':['in',["To Bill","To Deliver","To Deliver and Bill"]]},
			fields=["name"])

		get_so_list = [item.name for item in get_so_names]
		
		if get_so_hrs['sales_order_qty'] == None:
			get_so_hrs['sales_order_qty'] = 0
		else:
			pass

		if len(get_so_list) == 1:
			get_dn_hrs = frappe.db.sql("""SELECT sum(dni.qty) as dn_qty from `tabDelivery Note` dn join `tabDelivery Note Item` dni on dn.name = dni.parent where dni.against_sales_order = '{0}' and dn.status in ('Draft' ,'Completed','To Bill') """.format(get_so_list[0], tuple(get_project_list)), as_list=1)
			if get_dn_hrs[0][0] != None:
				get_so_hrs['dn_qty'] = get_dn_hrs[0][0]
			else:
				get_so_hrs['dn_qty'] = 0
		elif len(get_so_list) > 1:
			get_dn_hrs = frappe.db.sql("""SELECT sum(dni.qty) as dn_qty from `tabDelivery Note` dn join `tabDelivery Note Item` dni on dn.name = dni.parent where dni.against_sales_order in {0} and dn.status in ('Completed','To Bill','Draft') """.format(tuple(get_so_list), tuple(get_project_list)), as_list=1)
			
			if get_dn_hrs[0][0] != None:
				get_so_hrs['dn_qty'] = get_dn_hrs[0][0]
			else:
				get_so_hrs['dn_qty'] = 0
		else:
			get_so_hrs['dn_qty'] = 0

		get_so_hrs['remaining_hrs'] = float(get_so_hrs['sales_order_qty']) - float(get_so_hrs['dn_qty'])
		

		timesheet_hrs = frappe.db.sql("""SELECT sum(td.hours) as timesheet_hrs from `tabTimesheet` t join `tabTimesheet Detail` td on t.name = td.parent where td.is_billable = 1 and t.docstatus = 0 and td.project in {0} and td.custom_implementation = '{1}' and t.custom_delivery_note is NULL """.format(tuple(get_project_list), name), as_list=1, debug=1)

		if timesheet_hrs[0][0] != None:
			get_so_hrs['timesheet_hrs'] = timesheet_hrs[0][0]
			get_so_hrs['remaining_hrs'] = float(get_so_hrs['sales_order_qty']) - float(get_so_hrs['dn_qty']) - float(timesheet_hrs[0][0])
		else:
			get_so_hrs['timesheet_hrs'] = 0
			get_so_hrs['remaining_hrs'] = float(get_so_hrs['sales_order_qty']) - float(get_so_hrs['dn_qty'])

		get_open_sales_orders = frappe.db.get_value('Sales Order', {'status': ["in", ["To Deliver and Bill", "To Bill"]]}, 'count(name) as open_so')

		if get_open_sales_orders > 0:
			get_so_hrs['open_so'] = 1
		else:
			get_so_hrs['open_so'] = 0


		return get_so_hrs
	else:
		get_so_hrs =  {'sales_order_qty': 0, 'dn_qty': 0, 'remaining_hrs': 0, 'timesheet_hrs': 0, 'open_so': 0}
		return get_so_hrs


@frappe.whitelist()
def are_all_projects_closed(implementation_name):
    linked_projects = frappe.get_all('Project', filters={'custom_implementation': implementation_name}, fields=['status'])
    
    for proj in linked_projects:
        if proj.status not in ['Completed', 'Cancelled']:
            return False
    return True


@frappe.whitelist()
def graphical_representation(customer, name):
	pass

@frappe.whitelist()
def generate_auto_email_reports(docname):
    # Get Implementation document
    implementation = frappe.get_doc("Implementation", docname)

    user = implementation.user_with_permission
    sender = "Phamos no-reply"
    format_type = "HTML"

    # Dictionary to group by (template, frequency)
    grouped_reports = {}

    # Group recipients by template and frequency
    for row in implementation.auto_email_report_record:
        key = (row.templates, row.frequency)
        if key not in grouped_reports:
            grouped_reports[key] = {
                "templates": row.templates,
                "frequency": row.frequency,
                "recipients": set(),  # avoid duplicates
            }
        if row.recipients:
            # Split multiple recipients if present
            for r in row.recipients.replace(" ", "").split(","):
                grouped_reports[key]["recipients"].add(r)

    # Create one Auto Email Report per group
    for (template, frequency), data in grouped_reports.items():
        auto_email = frappe.new_doc("Auto Email Report")
        auto_email.user = user
        auto_email.report = template
        # Join recipients with newline instead of commas
        auto_email.email_to = "\n".join(sorted(data["recipients"]))
        auto_email.frequency = frequency
        auto_email.sender = sender
        auto_email.format = format_type

        # Add description based on frequency
        if frequency == "Daily":
            auto_email.description = (
                "<b><i>phamos wünscht einen wunderschönen guten Morgen!</i></b><br><br>"
                "Anbei erhalten Sie eine Übersicht der gestrigen Zeiteinträge, "
                "die auf Ihre Projekte gebucht wurden. Am Montagmorgen erhalten Sie zudem "
                "eine Zusammenfassung der vergangenen Woche.<br><br>"
                "Bei Fragen zu den Zeiteinträgen wenden Sie sich bitte an Ihren Projektleiter. Vielen Dank.<br><br>"
                "Wir wünschen Ihnen einen angenehmen Tag!<br>"
                "<b>Ihr team phamos</b>"
            )
        elif frequency == "Weekly":
            auto_email.description = (
                "<b><i>phamos wünscht einen wunderschönen guten Morgen!</i></b><br><br>"
                "Anbei die Übersicht aller Zeiterfassungen der vergangenen Woche.<br><br>"
                "Bei Fragen zu den Zeiteinträgen wenden Sie sich bitte an Ihren Projektleiter. Vielen Dank.<br><br>"
                "Wir wünschen eine gute Woche!<br>"
                "<b>Ihr team phamos</b>"
            )

        auto_email.insert(ignore_permissions=True)

    frappe.db.commit()
    return "Auto Email Reports created successfully"


