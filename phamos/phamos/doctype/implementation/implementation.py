# Copyright (c) 2025, phamos.eu and contributors
# For license information, please see license.txt

import frappe
from frappe.model.document import Document
from frappe.query_builder import DocType, get_query_builder
from frappe.utils import today


class Implementation(Document):
	def before_save(self):
		self.add_delivered_hrs()

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
						

@frappe.whitelist()
def get_financial_history(name, customer):
	get_so_hrs = frappe.db.get_value('Sales Order', {'custom_implementation':name,"status":["in",["To Deliver and Bill","To Bill"]]},'sum(total_qty) as sales_order_qty', as_dict=1)

	get_so_names = frappe.db.get_all("Sales Order",
		filters={"customer":customer, 'status':['in',["To Bill", "To Deliver and Bill"]]},
		fields=["name"])

	get_so_list = [item.name for item in get_so_names]
	
	if get_so_hrs['sales_order_qty'] == None:
		get_so_hrs['sales_order_qty'] = 0
	else:
		pass

	
	if len(get_so_list) == 1:
		get_dn_hrs = frappe.db.sql("""SELECT sum(dni.qty) as dn_qty from `tabDelivery Note` dn join `tabDelivery Note Item` dni on dn.name = dni.parent where dni.against_sales_order = '{0}' and dn.custom_implementation = '{1}' and status != 'Cancelled' """.format(get_so_list[0], name), as_list=1)
		if get_dn_hrs[0][0] != None:
			get_so_hrs['dn_qty'] = get_dn_hrs[0][0]
		else:
			get_so_hrs['dn_qty'] = 0
	elif len(get_so_list) > 1:
		get_dn_hrs = frappe.db.sql("""SELECT sum(dni.qty) as dn_qty from `tabDelivery Note` dn join `tabDelivery Note Item` dni on dn.name = dni.parent where dni.against_sales_order in {0} and dn.custom_implementation = '{1}' and status != 'Cancelled' """.format(tuple(get_so_list), name), as_list=1)
		
		if get_dn_hrs[0][0] != None:
			get_so_hrs['dn_qty'] = get_dn_hrs[0][0]
		else:
			get_so_hrs['dn_qty'] = 0
	else:
		get_so_hrs['dn_qty'] = 0

	
	get_so_hrs['remaining_hrs'] = int(get_so_hrs['sales_order_qty']) - int(get_so_hrs['dn_qty'])
	

	timesheet_hrs = frappe.db.sql("""SELECT sum(td.hours) as timesheet_hrs from `tabTimesheet` t join `tabTimesheet Detail` td on t.name = td.parent where td.is_billable = 1 and t.docstatus = 0 and td.custom_implementation = '{0}'  """.format(name), as_list=1, debug=1)

	if len(timesheet_hrs) != 0:
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



@frappe.whitelist()
def graphical_representation(customer, name):
	pass