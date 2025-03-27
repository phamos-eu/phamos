# Copyright (c) 2025, phamos.eu and contributors
# For license information, please see license.txt

import frappe
from frappe.model.document import Document
from frappe.query_builder import DocType, get_query_builder
from frappe.utils import today


class Implementation(Document):
	def before_save(self):
		self.add_delivered_hrs()
		self.add_resource_planning()

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

				total_billable_time = """SELECT DATE_FORMAT(start_date, '%Y-%m') AS month, SUM(tsd.hours) AS billable_time FROM  `tabTimesheet` ts JOIN `tabTimesheet Detail` tsd ON ts.name = tsd.parent WHERE ts.docstatus != 2 and tsd.project = '{0}' and tsd.is_billable = 1 GROUP BY month ORDER BY month""".format(get_project_list[0])
				
				billable_time = frappe.db.sql(total_billable_time, as_dict =1)
			elif len(get_project_list) > 1:
				total_time_spent = """SELECT DATE_FORMAT(start_date, '%Y-%m') AS month, SUM(tsd.hours) AS total_working_hours FROM  `tabTimesheet` ts JOIN `tabTimesheet Detail` tsd ON ts.name = tsd.parent WHERE ts.docstatus != 2 and tsd.project in {0} GROUP BY month ORDER BY month""".format(tuple(get_project_list))

				total_time = frappe.db.sql(total_time_spent, as_dict=True)

				total_billable_time = """SELECT DATE_FORMAT(start_date, '%Y-%m') AS month, SUM(tsd.hours) AS billable_time FROM  `tabTimesheet` ts JOIN `tabTimesheet Detail` tsd ON ts.name = tsd.parent WHERE ts.docstatus != 2 and tsd.project in {0} and tsd.is_billable = 1 GROUP BY month ORDER BY month""".format(tuple(get_project_list))
				
				billable_time = frappe.db.sql(total_billable_time, as_dict =1)
			else:
				total_time = [{'month':None, 'total_working_hours':0}]
				billable_time = [{'month':None, 'billable_time':0}]


			if self.resource_planning:
				(self.resource_planning).clear()
				for row in total_time:
					for row1 in billable_time:
						if row['month'] == row1['month']:
							non_billable = int(row.get('total_working_hours')) - int(row1.get('billable_time'))
							if non_billable >0:
								ratio = int(row1.get('billable_time'))/int(non_billable)
							else:
								ratio = 0

							self.append('resource_planning',{
								'month_and_year':row.get('month'),
								'total_time':row.get('total_working_hours'),
								'billable_time_spent':row1.get('billable_time'),
								'non_billable_time_spent':int(row.get('total_working_hours')) - int(row1.get('billable_time')),
								'ratio_of_billable_to_non_billable_time_spent':ratio
								})
			else:
				(self.resource_planning).clear()
				for row in total_time:
					for row1 in billable_time:
						if row['month'] == row1['month']:
							non_billable = int(row.get('total_working_hours')) - int(row1.get('billable_time'))
							if non_billable >0:
								ratio = int(row1.get('billable_time'))/int(non_billable)
							else:
								ratio = 0
							
							self.append('resource_planning',{
								'month_and_year':row.get('month'),
								'total_time':row.get('total_working_hours'),
								'non_billable_time_spent':int(row.get('total_working_hours')) - int(row1.get('billable_time')),
								'billable_time_spent':row1.get('billable_time'),
								'ratio_of_billable_to_non_billable_time_spent':ratio
								})
						

@frappe.whitelist()
def get_financial_history(name, customer):
	get_projects = frappe.db.get_all('Project', {'custom_implementation':name}, 'name')
	
	get_project_list = [item.name for item in get_projects]
	
	if len(get_project_list) == 1:
		get_so_hrs = frappe.db.get_value('Sales Order', {'customer':customer,"status":["in",["To Deliver and Bill", "To Deliver"]]},'sum(total_qty) as sales_order_qty', as_dict=1)

		get_so_names = frappe.db.get_all("Sales Order",
			filters={"customer":customer, 'status':['in',["To Bill", "To Deliver and Bill"]]},
			fields=["name"])

		get_so_list = [item.name for item in get_so_names]
		
		if get_so_hrs['sales_order_qty'] == None:
			get_so_hrs['sales_order_qty'] = 0
		else:
			pass

		
		if len(get_so_list) == 1:
			get_dn_hrs = frappe.db.sql("""SELECT sum(dni.qty) as dn_qty from `tabDelivery Note` dn join `tabDelivery Note Item` dni on dn.name = dni.parent where dni.against_sales_order = '{0}' and status != 'Cancelled' """.format(get_so_list[0]), as_list=1)
			if get_dn_hrs[0][0] != None:
				get_so_hrs['dn_qty'] = get_dn_hrs[0][0]
			else:
				get_so_hrs['dn_qty'] = 0
		elif len(get_so_list) > 1:
			get_dn_hrs = frappe.db.sql("""SELECT sum(dni.qty) as dn_qty from `tabDelivery Note` dn join `tabDelivery Note Item` dni on dn.name = dni.parent where dni.against_sales_order in {0} and status != 'Cancelled' """.format(tuple(get_so_list), get_project_list[0]), as_list=1)
			
			if get_dn_hrs[0][0] != None:
				get_so_hrs['dn_qty'] = get_dn_hrs[0][0]
			else:
				get_so_hrs['dn_qty'] = 0
		else:
			get_so_hrs['dn_qty'] = 0

		
		get_so_hrs['remaining_hrs'] = int(get_so_hrs['sales_order_qty']) - int(get_so_hrs['dn_qty'])
		

		timesheet_hrs = frappe.db.sql("""SELECT sum(td.hours) as timesheet_hrs from `tabTimesheet` t join `tabTimesheet Detail` td on t.name = td.parent where td.is_billable = 1 and t.docstatus = 0 and td.project = '{0}'  """.format(get_project_list[0]), as_list=1, debug=1)

		if timesheet_hrs[0][0] != None:
			get_so_hrs['timesheet_hrs'] = timesheet_hrs[0][0]
			get_so_hrs['remaining_hrs'] = int(get_so_hrs['sales_order_qty']) - int(get_so_hrs['dn_qty']) - int(timesheet_hrs[0][0])
		else:
			get_so_hrs['timesheet_hrs'] = 0
			get_so_hrs['remaining_hrs'] = int(get_so_hrs['sales_order_qty']) - int(get_so_hrs['dn_qty'])

		get_open_sales_orders = frappe.db.get_value('Sales Order', {'status': ["in", ["To Deliver and Bill", "To Bill"]]}, 'count(name) as open_so')

		if get_open_sales_orders > 0:
			get_so_hrs['open_so'] = 1
		else:
			get_so_hrs['open_so'] = 0

		
		return get_so_hrs
	elif len(get_project_list) > 1:
		get_so_hrs = frappe.db.get_value('Sales Order', {'customer':customer,"status":["in",["To Deliver and Bill","To Deliver"]]},'sum(total_qty) as sales_order_qty', as_dict=1)

		get_so_names = frappe.db.get_all("Sales Order",
			filters={"customer":customer, 'status':['in',["To Bill", "To Deliver and Bill"]]},
			fields=["name"])

		get_so_list = [item.name for item in get_so_names]
		
		if get_so_hrs['sales_order_qty'] == None:
			get_so_hrs['sales_order_qty'] = 0
		else:
			pass

		if len(get_so_list) == 1:
			get_dn_hrs = frappe.db.sql("""SELECT sum(dni.qty) as dn_qty from `tabDelivery Note` dn join `tabDelivery Note Item` dni on dn.name = dni.parent where dni.against_sales_order = '{0}' and status != 'Cancelled' """.format(get_so_list[0], tuple(get_project_list)), as_list=1)
			if get_dn_hrs[0][0] != None:
				get_so_hrs['dn_qty'] = get_dn_hrs[0][0]
			else:
				get_so_hrs['dn_qty'] = 0
		elif len(get_so_list) > 1:
			get_dn_hrs = frappe.db.sql("""SELECT sum(dni.qty) as dn_qty from `tabDelivery Note` dn join `tabDelivery Note Item` dni on dn.name = dni.parent where dni.against_sales_order in {0} and status != 'Cancelled' """.format(tuple(get_so_list), tuple(get_project_list)), as_list=1)
			
			if get_dn_hrs[0][0] != None:
				get_so_hrs['dn_qty'] = get_dn_hrs[0][0]
			else:
				get_so_hrs['dn_qty'] = 0
		else:
			get_so_hrs['dn_qty'] = 0

		get_so_hrs['remaining_hrs'] = int(get_so_hrs['sales_order_qty']) - int(get_so_hrs['dn_qty'])
		

		timesheet_hrs = frappe.db.sql("""SELECT sum(td.hours) as timesheet_hrs from `tabTimesheet` t join `tabTimesheet Detail` td on t.name = td.parent where td.is_billable = 1 and t.docstatus = 0 and td.project in {0}  """.format(tuple(get_project_list)), as_list=1, debug=1)

		if timesheet_hrs[0][0] != None:
			get_so_hrs['timesheet_hrs'] = timesheet_hrs[0][0]
			get_so_hrs['remaining_hrs'] = int(get_so_hrs['sales_order_qty']) - int(get_so_hrs['dn_qty']) - int(timesheet_hrs[0][0])
		else:
			get_so_hrs['timesheet_hrs'] = 0
			get_so_hrs['remaining_hrs'] = int(get_so_hrs['sales_order_qty']) - int(get_so_hrs['dn_qty'])

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
def graphical_representation(customer, name):
	pass