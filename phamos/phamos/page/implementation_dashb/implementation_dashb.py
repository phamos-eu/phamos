import frappe
from frappe.utils import formatdate

@frappe.whitelist()
def get_chart_data(from_date=None, to_date=None, team=None, implementation=None):
    from_month = from_date[:7] if from_date else None
    to_month = to_date[:7] if to_date else None

    def is_within_range(month_year):
        return (not from_month or month_year >= from_month) and (not to_month or month_year <= to_month)

    planning = []
    prediction = []

    if implementation:
        full_doc = frappe.get_doc("Implementation", implementation)
        planning = full_doc.resource_planning or []
        prediction = full_doc.resource_planning_prediction or []
    else:
        filters = {}
        if team:
            filters["team"] = team

        all_impls = frappe.get_all("Implementation", filters=filters, fields=["name"])
        for impl in all_impls:
            full_doc = frappe.get_doc("Implementation", impl.name)
            
            for row in (full_doc.resource_planning or []):
                row_dict = row.as_dict()
                row_dict["implementation_name"] = impl.name
                planning.append(row_dict)

            for row in (full_doc.resource_planning_prediction or []):
                row_dict = row.as_dict()
                row_dict["implementation_name"] = impl.name
                prediction.append(row_dict)

    # 🔹 HR-Addon Timesheet hours
    addon_data = frappe.db.sql("""
        SELECT DATE_FORMAT(tl.from_time, '%Y-%m') as month_and_year,
            SUM(tl.hours) as total_hours
        FROM `tabTimesheet` t
        JOIN `tabTimesheet Detail` tl ON tl.parent = t.name
        WHERE t.project_name = 'HR-Addon'
        AND t.docstatus = 1
        GROUP BY DATE_FORMAT(tl.from_time, '%Y-%m')
        ORDER BY month_and_year
    """, as_dict=True)


    # Filter by date
    planning_filtered = [row for row in planning if row.month_and_year and is_within_range(row.month_and_year)]
    prediction_filtered = [row for row in prediction if row.month_and_year and is_within_range(row.month_and_year)]
    addon_filtered = [row for row in addon_data if row.month_and_year and is_within_range(row.month_and_year)]

    return {
        "planning": planning_filtered,
        "prediction": prediction_filtered,
        "addon": addon_filtered  # 🔸 Extra addon data
    }



