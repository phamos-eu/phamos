"""
Patch to migrate Measurable child table records to use KRA (Key Result Area) doctype.

KRA is a standard doctype from the HR module (HRMS app).

This patch runs in pre_model_sync to:
1. Verify KRA doctype exists (standard doctype from HR module)
2. Extract unique metric_name values from all Measurable records
3. Create KRA records for each unique metric_name
4. Update all Measurable records to link to the corresponding KRA record

After this patch, the field type change in measurable.json (Data -> Link) will be applied
during model sync, and the data will already be migrated to KRA names.
"""

import frappe


def execute():
	# Step 1: Verify KRA doctype exists (standard doctype from HR module)
	if not frappe.db.exists("DocType", "KRA"):
		frappe.log_error("KRA Migration: DocType Missing", "KRA doctype does not exist. Please ensure HRMS app is installed.")
		return
	
	# Reload KRA doctype to ensure it's up to date
	try:
		frappe.reload_doc("HR", "doctype", "KRA")
	except Exception as e:
		frappe.log_error("KRA Migration: Reload Error", f"Error reloading KRA doctype: {str(e)}")
		# Continue anyway, KRA might already exist
	
	# Step 2: Get all unique metric_name values from Measurable child table
	measurables = frappe.db.sql("""
		SELECT DISTINCT metric_name
		FROM `tabMeasurable`
		WHERE metric_name IS NOT NULL AND metric_name != ''
		AND metric_name NOT LIKE '%-%'  -- Exclude already migrated KRA names (they contain hyphens)
	""", as_dict=True)
	
	if not measurables:
		frappe.log_error("KRA Migration: No Records", "No Measurable records found to migrate")
		return
	
	frappe.log_error("KRA Migration: Starting", f"Found {len(measurables)} unique metric names to migrate")
	
	# Step 3: Create KRA records for each unique metric_name
	kra_mapping = {}  # Maps old metric_name to new KRA name
	
	for measurable in measurables:
		metric_name = measurable.metric_name.strip()
		
		if not metric_name:
			continue
		
		# Skip if it's already a KRA name (contains hyphen, which is Frappe's naming pattern)
		if '-' in metric_name and frappe.db.exists("KRA", metric_name):
			kra_mapping[metric_name] = metric_name
			continue
		
		# Check if KRA already exists by title
		existing_kra = frappe.db.get_value("KRA", {"title": metric_name}, "name")
		
		if existing_kra:
			kra_mapping[metric_name] = existing_kra
			frappe.log_error("KRA Migration: Existing KRA", f"KRA already exists: {metric_name} -> {existing_kra}")
		else:
			# Create new KRA record
			try:
				kra_doc = frappe.get_doc({
					"doctype": "KRA",
					"title": metric_name,
					"description": f"Migrated from Measurable metric_name: {metric_name}"
				})
				kra_doc.insert(ignore_permissions=True)
				kra_mapping[metric_name] = kra_doc.name
				frappe.log_error("KRA Migration: Created", f"Created KRA: {metric_name} -> {kra_doc.name}")
			except frappe.DuplicateEntryError:
				# If duplicate, get the existing one
				existing_kra = frappe.db.get_value("KRA", {"title": metric_name}, "name")
				if existing_kra:
					kra_mapping[metric_name] = existing_kra
					frappe.log_error("KRA Migration: Duplicate", f"Duplicate KRA found: {metric_name} -> {existing_kra}")
			except Exception as e:
				frappe.log_error("KRA Migration: Create Error", f"Error creating KRA for {metric_name}: {str(e)}")
				continue
	
	# Step 4: Update all Measurable records to use KRA link
	# Get all Measurable records that need updating
	all_measurables = frappe.db.sql("""
		SELECT name, parent, parenttype, metric_name
		FROM `tabMeasurable`
		WHERE metric_name IS NOT NULL 
		AND metric_name != ''
		AND metric_name NOT LIKE '%-%'  -- Exclude already migrated records
	""", as_dict=True)
	
	updated_count = 0
	failed_count = 0
	
	for measurable in all_measurables:
		metric_name = measurable.metric_name.strip()
		kra_name = kra_mapping.get(metric_name)
		
		if not kra_name:
			frappe.log_error("KRA Migration: Missing Mapping", f"No KRA mapping found for metric_name: {metric_name}")
			failed_count += 1
			continue
		
		try:
			# Update the metric_name field to store KRA name
			# This will work when the field type changes to Link
			frappe.db.set_value("Measurable", measurable.name, "metric_name", kra_name)
			updated_count += 1
		except Exception as e:
			frappe.log_error("KRA Migration: Update Error", f"Error updating Measurable {measurable.name}: {str(e)}")
			failed_count += 1
	
	frappe.log_error("KRA Migration: Complete", f"Migration completed: {updated_count} updated, {failed_count} failed, {len(kra_mapping)} KRAs created")
	
	frappe.db.commit()

