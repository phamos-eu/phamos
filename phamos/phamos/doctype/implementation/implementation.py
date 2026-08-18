# Copyright (c) 2025, phamos.eu and contributors
# For license information, please see license.txt

import frappe
from datetime import date
from datetime import datetime
import re
from frappe.model.document import Document
from frappe.query_builder import Case, DocType
from frappe.query_builder.functions import Coalesce, Count, Sum
from frappe.utils import flt, today


class Implementation(Document):
	def validate(self):
		if self.is_new():
			return
		db_status = frappe.db.get_value("Implementation", self.name, "status")
		if db_status == "Escalated" and self.status != "Escalated":
			has_resolved = frappe.db.exists(
				"Escalation", {"implementation": self.name, "status": "Resolved"}
			)
			has_submitted = frappe.db.exists(
				"Escalation", {"implementation": self.name, "docstatus": 1}
			)
			if not has_resolved and not has_submitted:
				frappe.throw(
					"Cannot change status from Escalated. "
					"Please resolve or submit the linked Escalation first."
				)

	def before_save(self):
		self.sync_modules_from_implementation_chapters()
		self.sync_sales_order_status_information()
		self.add_financial_snapshot()

		if self.resource_planning_prediction:
			# Get existing row names from database to identify truly new rows
			existing_names = set()
			if not self.is_new():
				existing_names = set(
					frappe.get_all(
						"Prediction",
						filters={"parent": self.name},
						pluck="name"
					)
				)
			
			# Separate new rows from existing rows
			new_rows = []
			existing_rows = []
			for row in self.resource_planning_prediction:
				# Row is new if its name is not in the database
				if not row.name or row.name not in existing_names:
					new_rows.append(row)
				else:
					existing_rows.append(row)
			
			# Sort only new rows by date descending (newest first)
			new_rows.sort(key=lambda x: x.date or "", reverse=True)
			
			# Prepend new rows to existing rows (new rows at top, existing rows keep their order)
			self.resource_planning_prediction = new_rows + existing_rows
			
			# Re-index all rows
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
		self.add_implementation_stats()
		self.add_rank_html()
		self.add_status_history()

	def sync_sales_order_status_information(self):
		if not self.name or not self.customer:
			self.sales_order_status_information = []
			return

		rows = get_sales_order_status_information(name=self.name, customer=self.customer)
		self.sales_order_status_information = []
		for row in rows:
			self.append("sales_order_status_information", row)

	def _parse_month_key(self, value):
		if not value:
			return None

		if isinstance(value, date):
			return date(value.year, value.month, 1)

		if not isinstance(value, str):
			return None

		value = value.strip()
		if not value:
			return None

		match = re.match(r"^(\d{4})-(\d{1,2})(?:-\d{1,2})?$", value)
		if match:
			year = int(match.group(1))
			month = int(match.group(2))
			if 1 <= month <= 12:
				return date(year, month, 1)

		for fmt in ("%Y/%m", "%b %Y", "%B %Y", "%m-%Y", "%Y-%m-%d"):
			try:
				parsed = datetime.strptime(value, fmt)
				return date(parsed.year, parsed.month, 1)
			except ValueError:
				continue

		try:
			year_str, month_str = value.split("-", 1)
			year = int(year_str)
			month = int(month_str)
			if month < 1 or month > 12:
				return None
			return date(year, month, 1)
		except Exception:
			return None

	def _month_shift(self, base_month_start, delta):
		year = base_month_start.year + ((base_month_start.month - 1 + delta) // 12)
		month = ((base_month_start.month - 1 + delta) % 12) + 1
		return date(year, month, 1)

	def add_implementation_stats(self):
		month_totals = {}
		life_total = 0.0
		for row in self.resource_planning or []:
			life_total += flt(row.total_time)
			month_start = self._parse_month_key(row.month_and_year)
			if not month_start:
				continue
			month_totals[month_start] = month_totals.get(month_start, 0.0) + flt(row.total_time)

		self.total_time_implementation_life = life_total

		today_date = date.today()
		current_month_start = date(today_date.year, today_date.month, 1)

		def rolling_total(month_count):
			start_month = self._month_shift(current_month_start, -(month_count - 1))
			return sum(
				value
				for month_start, value in month_totals.items()
				if start_month <= month_start <= current_month_start
			)

		self.total_time_last_12_months = rolling_total(12)
		self.total_time_last_6_months = rolling_total(6)
		self.total_time_last_3_months = rolling_total(3)

		# For next 3 upcoming months: if a month has multiple predictions,
		# use that month's average; then add month values together.
		predictions_by_month = {}
		for row in self.resource_planning_prediction or []:
			month_start = self._parse_month_key(row.month_and_year)
			if not month_start:
				continue
			if month_start <= current_month_start:
				continue
			predictions_by_month.setdefault(month_start, []).append(flt(row.prediction))

		upcoming_months = sorted(
			month_start
			for month_start in predictions_by_month
		)[:3]

		if upcoming_months:
			total_prediction = 0.0
			for month in upcoming_months:
				month_values = predictions_by_month.get(month, [])
				if not month_values:
					continue
				if len(month_values) >= 2:
					total_prediction += sum(month_values) / len(month_values)
				else:
					total_prediction += month_values[0]
			self.predicted_time_next_3_months = total_prediction
		else:
			self.predicted_time_next_3_months = 0

	def _get_rank_fraction(self, metric_field, current_value):
		current_value = flt(current_value)
		if current_value <= 0:
			return "-"

		other_rows = frappe.get_all(
			"Implementation",
			filters={
				"name": ["!=", self.name],
				metric_field: [">", 0],
			},
			fields=[metric_field],
			limit_page_length=0,
		)

		other_values = [flt(row.get(metric_field)) for row in other_rows if flt(row.get(metric_field)) > 0]
		higher_count = sum(1 for value in other_values if value > current_value)
		total_active = len(other_values) + 1
		rank = higher_count + 1
		return f"{rank}/{total_active}"

	def add_rank_html(self):
		rank_last_12 = self._get_rank_fraction("total_time_last_12_months", self.total_time_last_12_months)
		rank_last_6 = self._get_rank_fraction("total_time_last_6_months", self.total_time_last_6_months)
		rank_last_3 = self._get_rank_fraction("total_time_last_3_months", self.total_time_last_3_months)
		rank_next_3 = self._get_rank_fraction("predicted_time_next_3_months", self.predicted_time_next_3_months)

		self.rank_html = (
			"<div class='implementation-rank-card'>"
			"<div class='implementation-rank-title'>Implementation Ranking</div>"
			f"<div class='implementation-rank-row'><span class='implementation-rank-label'>Last 12 months</span><span class='implementation-rank-value'>{rank_last_12}</span></div>"
			f"<div class='implementation-rank-row'><span class='implementation-rank-label'>Last 6 months</span><span class='implementation-rank-value'>{rank_last_6}</span></div>"
			f"<div class='implementation-rank-row'><span class='implementation-rank-label'>Last 3 months</span><span class='implementation-rank-value'>{rank_last_3}</span></div>"
			f"<div class='implementation-rank-row'><span class='implementation-rank-label'>Next 3 months</span><span class='implementation-rank-value'>{rank_next_3}</span></div>"
			"</div>"
		)

	def add_financial_snapshot(self):
		if not self.customer or not self.name:
			return

		financial_history = get_financial_history(self.name, self.customer) or {}
		self.sales_order_total_hrs = int(flt(financial_history.get("sales_order_qty")))
		self.total_hrs_timesheet = flt(financial_history.get("timesheet_hrs"))
		self.remaining_hrs = flt(financial_history.get("remaining_hrs"))


	def after_save(self):
		self._sync_linked_escalations()

	def _sync_linked_escalations(self):
		escalations = frappe.get_all(
			"Escalation",
			filters={"implementation": self.name, "docstatus": ["!=", 2]},
			fields=["name", "open_date"],
		)
		for esc in escalations:
			if not esc.open_date:
				continue
			snapshot = _get_escalation_snapshot(self.name, str(esc.open_date))
			if snapshot:
				frappe.db.set_value(
					"Escalation",
					esc.name,
					{
						"maturity_level": snapshot.get("maturity_level"),
						"implementation_status": snapshot.get("forecast"),
					},
					update_modified=False,
				)

	def add_delivered_hrs(self):
		delivered_total_hrs = 0
		if self.sales_order_status_information:
			for row in self.sales_order_status_information:
				total_hours = 0

				delivery_notes = frappe.db.sql("""
					SELECT dni.qty
					FROM `tabDelivery Note Item` dni
					JOIN `tabDelivery Note` dn ON dn.name = dni.parent
					WHERE
						dni.against_sales_order = %s
						AND dn.docstatus = 1
						AND dn.status NOT IN ('Cancelled', 'Closed')
				""", row.sales_order, as_dict=True)

				if not delivery_notes:
					row.delivered_total_hrs = 0
				else:
					for dn in delivery_notes:
						total_hours += dn.get("qty", 0)
					row.delivered_total_hrs = total_hours

				delivered_total_hrs += flt(row.delivered_total_hrs)
				row.remaining_hrs = flt(row.total_hrs) - flt(row.delivered_total_hrs)

		self.delivered_total_hrs = delivered_total_hrs

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

	def sync_modules_from_implementation_chapters(self):
		if not self.name:
			return

		existing_by_chapter = {
			(row.implementation_chapter or "").strip(): row
			for row in self.modules or []
			if (row.implementation_chapter or "").strip()
		}

		chapters = frappe.get_all(
			"Implementation Chapter",
			filters={"implementation": self.name},
			fields=["name", "chapter_title", "planned_start", "target_date"],
			order_by="creation asc",
			limit_page_length=1000,
		)

		for chapter in chapters:
			chapter_name = (chapter.get("name") or "").strip()
			if not chapter_name:
				continue

			existing_row = existing_by_chapter.get(chapter_name)
			if existing_row:
				if chapter.get("planned_start") and not existing_row.planned_start:
					existing_row.planned_start = chapter.get("planned_start")
				if chapter.get("target_date") and not existing_row.target_date:
					existing_row.target_date = chapter.get("target_date")
				continue

			self.append(
				"modules",
				{
					"implementation_chapter": chapter_name,
					"planned_start": chapter.get("planned_start"),
					"target_date": chapter.get("target_date"),
				},
			)



						

@frappe.whitelist()
def get_financial_history(name, customer = None):
	if not customer:
		return {}

	Project = DocType("Project")
	SalesOrder = DocType("Sales Order")
	DeliveryNote = DocType("Delivery Note")
	DeliveryNoteItem = DocType("Delivery Note Item")
	Timesheet = DocType("Timesheet")
	TimesheetDetail = DocType("Timesheet Detail")
	open_so_statuses = ("To Deliver and Bill", "To Deliver", "To Bill")

	sales_order_qty = (
		frappe.qb.from_(SalesOrder)
		.select(Coalesce(Sum(SalesOrder.total_qty), 0))
		.where(
			(SalesOrder.custom_implementation == name)
			& SalesOrder.status.isin(open_so_statuses)
		)
	)

	open_so_count = (
		frappe.qb.from_(SalesOrder)
		.select(Count(SalesOrder.name))
		.where(
			(SalesOrder.custom_implementation == name)
			& SalesOrder.status.isin(open_so_statuses)
		)
	)

	dn_qty = (
		frappe.qb.from_(DeliveryNote)
		.inner_join(DeliveryNoteItem)
		.on(DeliveryNoteItem.parent == DeliveryNote.name)
		.inner_join(SalesOrder)
		.on(SalesOrder.name == DeliveryNoteItem.against_sales_order)
		.select(Coalesce(Sum(DeliveryNoteItem.qty), 0))
		.where(
			(SalesOrder.custom_implementation == name)
			& SalesOrder.status.isin(open_so_statuses)
			& (DeliveryNote.docstatus == 1)
			& DeliveryNote.status.notin(("Cancelled", "Closed"))
		)
	)

	timesheet_hrs = (
		frappe.qb.from_(Timesheet)
		.inner_join(TimesheetDetail)
		.on(TimesheetDetail.parent == Timesheet.name)
		.inner_join(Project)
		.on(Project.name == TimesheetDetail.project)
		.select(Coalesce(Sum(TimesheetDetail.hours), 0))
		.where(
			(Project.custom_implementation == name)
			& (TimesheetDetail.custom_implementation == name)
			& (TimesheetDetail.is_billable == 1)
			& (Timesheet.docstatus == 0)
			& Timesheet.custom_delivery_note.isnull()
		)
	)

	# Keep all financial fields on the same filters and calculate them in one
	# database round trip. In particular, delivered hours must match the child
	# table calculation in add_delivered_hrs().
	totals = (
		frappe.qb.from_(Project)
		.select(
			sales_order_qty.as_("sales_order_qty"),
			dn_qty.as_("dn_qty"),
			timesheet_hrs.as_("timesheet_hrs"),
			open_so_count.as_("open_so_count"),
		)
		.where(Project.custom_implementation == name)
		.limit(1)
	)

	financial_history = (
		frappe.qb.from_(totals)
		.select(
			totals.sales_order_qty,
			totals.dn_qty,
			totals.timesheet_hrs,
			(totals.sales_order_qty - totals.dn_qty - totals.timesheet_hrs).as_("remaining_hrs"),
			Case().when(totals.open_so_count > 0, 1).else_(0).as_("open_so"),
		)
	).run(as_dict=True)

	return financial_history[0] if financial_history else {
		"sales_order_qty": 0,
		"dn_qty": 0,
		"timesheet_hrs": 0,
		"remaining_hrs": 0,
		"open_so": 0,
	}


def _delivered_hours_against_sales_order(sales_order_name):
	rows = frappe.db.sql(
		"""
		SELECT dni.qty
		FROM `tabDelivery Note Item` dni
		INNER JOIN `tabDelivery Note` dn ON dn.name = dni.parent
		WHERE dni.against_sales_order = %s
			AND dn.docstatus = 1
			AND IFNULL(dn.status, '') NOT IN ('Cancelled', 'Closed')
		""",
		sales_order_name,
		as_dict=True,
	)
	return flt(sum(flt(r.get("qty")) for r in rows)) if rows else 0


def get_sales_order_status_information(name, customer=None):
	if not name:
		return []

	if not customer:
		customer = frappe.db.get_value("Implementation", name, "customer")

	if not customer:
		return []

	open_so = {
		"customer": customer,
		"custom_implementation": name,
		"status": ["in", ["To Deliver", "To Bill", "To Deliver and Bill"]],
		"docstatus": 1,
	}

	rows = []
	for so in frappe.get_all(
		"Sales Order",
		filters=open_so,
		fields=["name", "status", "total_qty", "customer_name"],
		order_by="transaction_date desc",
	):
		total_hrs = flt(so.total_qty)
		delivered_total_hrs = _delivered_hours_against_sales_order(so.name)
		remaining_hrs = flt(total_hrs - delivered_total_hrs, 2)
		rows.append(
			{
				"sales_order": so.name,
				"so_title": so.customer_name or "",
				"total_hrs": total_hrs,
				"status": so.status or "",
				"delivered_total_hrs": delivered_total_hrs,
				"remaining_hrs": remaining_hrs,
			}
		)

	return rows


@frappe.whitelist()
def get_financial_snapshot(name, customer=None):
	return {
		"financial_history": get_financial_history(name=name, customer=customer),
		"sales_order_status_information": get_sales_order_status_information(name=name, customer=customer),
	}


@frappe.whitelist()
def sync_modules_with_implementation_chapters(name):
	if not name:
		return {"added_count": 0, "updated_count": 0}

	existing_chapters = {
		(chapter or "").strip()
		for chapter in frappe.get_all(
			"Implementation Item",
			filters={"parent": name, "parenttype": "Implementation", "parentfield": "modules"},
			pluck="implementation_chapter",
		)
		if (chapter or "").strip()
	}

	chapters = frappe.get_all(
		"Implementation Chapter",
		filters={"implementation": name},
		fields=["name", "chapter_title", "planned_start", "target_date"],
		order_by="creation asc",
		limit_page_length=1000,
	)

	last_row = frappe.get_all(
		"Implementation Item",
		filters={"parent": name, "parenttype": "Implementation", "parentfield": "modules"},
		fields=["idx"],
		order_by="idx desc",
		limit_page_length=1,
	)

	next_idx = int(last_row[0].idx) if last_row and last_row[0].get("idx") else 0
	added_count = 0
	updated_count = 0

	for chapter in chapters:
		chapter_name = (chapter.get("name") or "").strip()
		if not chapter_name:
			continue

		chapter_planned_start = chapter.get("planned_start")
		chapter_target_date = chapter.get("target_date")

		if chapter_name in existing_chapters:
			existing_item = frappe.db.get_value(
				"Implementation Item",
				{
					"parent": name,
					"parenttype": "Implementation",
					"parentfield": "modules",
					"implementation_chapter": chapter_name,
				},
				["name", "planned_start", "target_date"],
				as_dict=True,
			)
			updates = {}
			if existing_item and existing_item.get("planned_start") != chapter_planned_start:
				updates["planned_start"] = chapter_planned_start
			if existing_item and existing_item.get("target_date") != chapter_target_date:
				updates["target_date"] = chapter_target_date

			if existing_item and updates:
				frappe.db.set_value(
					"Implementation Item",
					existing_item.get("name"),
					updates,
					update_modified=False,
				)
				updated_count += 1
			continue

		if frappe.db.exists(
			"Implementation Item",
			{
				"parent": name,
				"parenttype": "Implementation",
				"parentfield": "modules",
				"implementation_chapter": chapter_name,
			},
		):
			existing_chapters.add(chapter_name)
			continue

		next_idx += 1
		frappe.get_doc(
			{
				"doctype": "Implementation Item",
				"parent": name,
				"parenttype": "Implementation",
				"parentfield": "modules",
				"idx": next_idx,
				"implementation_chapter": chapter_name,
				"planned_start": chapter_planned_start,
				"target_date": chapter_target_date,
			}
		).insert(ignore_permissions=True)

		existing_chapters.add(chapter_name)
		added_count += 1

	return {"added_count": added_count, "updated_count": updated_count}


@frappe.whitelist()
def recompute_implementation_stats(name):
	"""Rebuild resource planning from Timesheets and recompute stats fields for one record."""
	doc = frappe.get_doc("Implementation", name)
	doc.add_resource_planning()

	frappe.db.delete(
		"Resource planning",
		{"parent": name, "parenttype": "Implementation", "parentfield": "resource_planning"},
	)
	for idx, row in enumerate(doc.resource_planning or [], start=1):
		row.idx = idx
		row.name = None
		frappe.get_doc(row.as_dict()).insert(ignore_permissions=True)

	doc.add_implementation_stats()
	doc.add_rank_html()
	frappe.db.set_value(
		"Implementation",
		name,
		{
			"total_time_implementation_life": flt(doc.total_time_implementation_life),
			"total_time_last_12_months": flt(doc.total_time_last_12_months),
			"total_time_last_6_months": flt(doc.total_time_last_6_months),
			"total_time_last_3_months": flt(doc.total_time_last_3_months),
			"predicted_time_next_3_months": flt(doc.predicted_time_next_3_months),
		},
		update_modified=False,
	)
	return {
		"name": name,
		"total_time_implementation_life": flt(doc.total_time_implementation_life),
		"total_time_last_12_months": flt(doc.total_time_last_12_months),
		"total_time_last_6_months": flt(doc.total_time_last_6_months),
		"total_time_last_3_months": flt(doc.total_time_last_3_months),
		"predicted_time_next_3_months": flt(doc.predicted_time_next_3_months),
		"rank_html": doc.rank_html,
	}


@frappe.whitelist()
def get_implementation_rank_overview(name):
	doc = frappe.get_doc("Implementation", name)
	doc.add_implementation_stats()
	doc.add_rank_html()
	return {
		"rank_html": doc.rank_html,
		"rank_last_12": doc._get_rank_fraction("total_time_last_12_months", doc.total_time_last_12_months),
		"rank_last_6": doc._get_rank_fraction("total_time_last_6_months", doc.total_time_last_6_months),
		"rank_last_3": doc._get_rank_fraction("total_time_last_3_months", doc.total_time_last_3_months),
		"rank_next_3": doc._get_rank_fraction("predicted_time_next_3_months", doc.predicted_time_next_3_months),
	}


@frappe.whitelist()
def recompute_all_implementation_stats(limit=None):
	"""Backfill stats for all Implementation records (optional limit)."""
	limit = int(limit) if limit else None
	names = frappe.get_all("Implementation", pluck="name", limit=limit)
	return [recompute_implementation_stats(name) for name in names]


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

    # 🔹 Group child table records
    for row in implementation.auto_email_report_record:
        key = (row.templates, row.frequency)
        if key not in grouped_reports:
            grouped_reports[key] = {
                "templates": row.templates,
                "frequency": row.frequency,
                "recipients": set()
            }

        if row.recipients:
            for r in row.recipients.replace(" ", "").split(","):
                grouped_reports[key]["recipients"].add(r.lower())

    # 🔹 Create / Update Auto Email Report
    for (template, frequency), data in grouped_reports.items():
        email_to = "\n".join(sorted(data["recipients"]))

        # 🔍 Check existing record (WITHOUT email_to)
        existing_name = frappe.db.get_value(
            "Auto Email Report",
            {
                "user": user,
                "report": template,
                "frequency": frequency
            },
            "name"
        )

        # ✅ Case 1: Record exists → update email if changed
        if existing_name:
            existing_doc = frappe.get_doc("Auto Email Report", existing_name)

            if existing_doc.email_to.strip() != email_to.strip():
                existing_doc.email_to = email_to
                existing_doc.save(ignore_permissions=True)

                frappe.msgprint(
                    f"✏️ Email updated successfully for <b>{template}</b> ({frequency}).",
                    alert=True
                )
            else:
                frappe.msgprint(
                    f"⚠️ Auto Email Report already exists for <b>{template}</b> ({frequency}).",
                    alert=True
                )

            continue # Skip to next iteration

        # ✅ Case 2: No record exists → create new
        auto_email = frappe.new_doc("Auto Email Report")
        auto_email.user = user
        auto_email.report = template
        auto_email.email_to = email_to
        auto_email.frequency = frequency
        auto_email.sender = sender
        auto_email.format = format_type

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
        frappe.publish_realtime(
			event="show_alert",
			message=f"✅ New Auto Email Report created for {template} ({frequency})",
			user=frappe.session.user
		)

    frappe.db.commit()

@frappe.whitelist()
def get_auto_email_reports(user_email: str):
    """Return count of Auto Email Reports where user matches Implementation.user_with_permission."""
    if not user_email:
        return 0
    return frappe.db.count(
        "Auto Email Report",
        filters={"user": user_email, "enabled": 1},
    )

@frappe.whitelist()
def get_gitlab_projects_count(implementation: str):
    """Return count of GitLab Projects linked with this Implementation."""
    if not implementation:
        return 0

    return frappe.db.count(
        "GitLab Project",
        filters={
            "implementation": implementation
        },
    )

@frappe.whitelist()
def get_gitlab_issues_count(implementation: str):
    """Return count of GitLab Issues linked via GitLab Projects of this Implementation."""
    if not implementation:
        return 0

    return frappe.db.count(
        "GitLab Issue",
        filters={
            "gitlab_project": ["in", frappe.get_all(
                "GitLab Project",
                filters={"implementation": implementation},
                pluck="name"
            )]
        }
    )
@frappe.whitelist()
def get_gitlab_milestones_count(implementation: str):
    """Return count of GitLab Milestones linked via GitLab Projects of this Implementation."""
    if not implementation:
        return 0

    return frappe.db.count(
        "GitLab Milestones",
        filters={
            "gitlab_project": ["in", frappe.get_all(
                "GitLab Project",
                filters={"implementation": 	implementation},
                pluck="name"
            )]
        }
    )
def _get_escalation_snapshot(implementation, open_date):
	"""Return the Status Updates row strictly before open_date (non-Escalated).
	Falls back to the row on or before open_date (today's entry) if none found."""
	result = frappe.db.sql(
		"""
		SELECT maturity_level, forecast
		FROM `tabStatus Information`
		WHERE parent = %s
		AND parentfield = 'status_updates'
		AND `date` < %s
		AND COALESCE(status, '') != 'Escalated'
		ORDER BY `date` DESC
		LIMIT 1
		""",
		(implementation, open_date),
		as_dict=True,
	)
	if result:
		return result[0]

	# Fallback: today's row (no previous entry exists yet)
	fallback = frappe.db.sql(
		"""
		SELECT maturity_level, forecast
		FROM `tabStatus Information`
		WHERE parent = %s
		AND parentfield = 'status_updates'
		AND `date` <= %s
		ORDER BY `date` DESC
		LIMIT 1
		""",
		(implementation, str(open_date)),
		as_dict=True,
	)
	return fallback[0] if fallback else {}


@frappe.whitelist()
def escalate_implementation(implementation_name, reason):
	open_date = today()

	# Snapshot before save — today's row still holds the pre-escalation status
	snapshot = _get_escalation_snapshot(implementation_name, open_date)

	doc = frappe.get_doc("Implementation", implementation_name)
	doc.status = "Escalated"
	doc.status_statement = reason
	doc.save(ignore_permissions=True)

	escalation = frappe.new_doc("Escalation")
	escalation.implementation = implementation_name
	escalation.open_date = open_date
	escalation.status = "Unresolved"
	escalation.opening_statement = reason
	if snapshot:
		escalation.maturity_level = snapshot.get("maturity_level")
		escalation.implementation_status = snapshot.get("status")
	escalation.insert(ignore_permissions=True)
	return escalation.name


@frappe.whitelist()
def generate_weekly_customer_report(implementation_name, from_date=None, to_date=None):
    from phamos.gitlab_integration.generate_weekly_report import generate_and_send_weekly_report
    return generate_and_send_weekly_report(implementation_name, from_date=from_date, to_date=to_date)


@frappe.whitelist()
def get_auto_email_reports_for_users(user_list):
    if isinstance(user_list, str):
        user_list = [user_list]

    reports = frappe.get_all(
        "Auto Email Report",
        filters={"user": ["in", user_list]},
        fields=["email_to", "report", "frequency"]
    )

    result = []

    for r in reports:
        # split by comma, semicolon or new line
        emails = [e.strip() for e in r.email_to.replace("\n",",").replace(";",",").split(",") if e.strip()]
        for email in emails:
            if email not in [x.get("recipient") for x in result]:
                result.append({
                    "recipient": email,
                    "template": r.report,
                    "frequency": r.frequency
                })
    return result
