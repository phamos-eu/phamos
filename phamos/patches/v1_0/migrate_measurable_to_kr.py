"""
Patch to migrate Measurable child table records to use KR (Key Result) doctype.

KR is a doctype from the OKR Addon module.

This patch runs in pre_model_sync to:
1. Verify KR doctype exists (doctype from OKR Addon module)
2. Extract unique metric_name values from all Measurable records
3. Create KR records for each unique metric_name
4. Update all Measurable records to link to the corresponding KR record

After this patch, the field type change in measurable.json (Data -> Link) will be applied
during model sync, and the data will already be migrated to KR names.
"""

import frappe


def execute():
	# Step 1: Verify KR doctype exists (doctype from OKR Addon module)
	if not frappe.db.exists("DocType", "KR"):
		frappe.log_error("KR Migration: DocType Missing", "KR doctype does not exist. Please ensure OKR Addon module is installed.")
		return

	# Reload KR doctype to ensure it's up to date
	try:
		frappe.reload_doc("OKR Addon", "doctype", "KR")
	except Exception as e:
		frappe.log_error("KR Migration: Reload Error", f"Error reloading KR doctype: {str(e)}")
		# Continue anyway, KR might already exist
	# Step 2: Get all unique metric_name values from Measurable child table
	measurables = frappe.db.sql("""
		SELECT DISTINCT metric_name
		FROM `tabMeasurable`
		WHERE metric_name IS NOT NULL AND metric_name != ''
		AND metric_name NOT LIKE '%-%'  -- Exclude already migrated KR names (they contain hyphens)
	""", as_dict=True)

	if not measurables:
		frappe.log_error("KR Migration: No Records", "No Measurable records found to migrate")
		return

	frappe.log_error("KR Migration: Starting", f"Found {len(measurables)} unique metric names to migrate")

	# Step 3: Create KR records for each unique metric_name
	kra_mapping = {}  # Maps old metric_name to new KR name

	for measurable in measurables:
		metric_name = measurable.metric_name.strip()

		if not metric_name:
			continue

		# Skip if it's already a KR name (contains hyphen, which is Frappe's naming pattern)
		if '-' in metric_name and frappe.db.exists("KR", metric_name):
			kra_mapping[metric_name] = metric_name
			continue

		# Generate a short title for KR (max 140 chars for name field, but keep title shorter for safety)
		# Truncate to 100 chars to ensure the auto-generated name doesn't exceed limits
		short_title = metric_name[:100] if len(metric_name) <= 100 else metric_name[:97] + "..."

		# Check if KR already exists by title (check both full and truncated)
		existing_kra = frappe.db.get_value("KR", {"title": metric_name}, "name")
		if not existing_kra:
			existing_kra = frappe.db.get_value("KR", {"title": short_title}, "name")
		if existing_kra:
			kra_mapping[metric_name] = existing_kra
			# Truncate long metric_name in log message
			metric_short = metric_name[:50] if len(metric_name) > 50 else metric_name
			kra_short = existing_kra[:50] if len(existing_kra) > 50 else existing_kra
			frappe.log_error("KR Migration: Existing", f"KR exists: {metric_short} -> {kra_short}")
		else:
			# Create new KR record
			try:
				kra_doc = frappe.get_doc({
					"doctype": "KR",
					"title": short_title,  # Short title for the KR record (max 100 chars)
					"description": f"Original metric_name: {metric_name}"  # Full metric_name in description
				})
				kra_doc.insert(ignore_permissions=True)
				kra_mapping[metric_name] = kra_doc.name
				# Truncate long values in log message
				metric_short = metric_name[:40] if len(metric_name) > 40 else metric_name
				kra_short = kra_doc.name[:40] if len(kra_doc.name) > 40 else kra_doc.name
				title_short = short_title[:30] if len(short_title) > 30 else short_title
				frappe.log_error("KR Migration: Created", f"Created: {metric_short} -> {kra_short} (title: {title_short})")
			except frappe.DuplicateEntryError:
				# If duplicate, get the existing one
				existing_kra = frappe.db.get_value("KR", {"title": short_title}, "name")
				if existing_kra:
					kra_mapping[metric_name] = existing_kra
					metric_short = metric_name[:50] if len(metric_name) > 50 else metric_name
					kra_short = existing_kra[:50] if len(existing_kra) > 50 else existing_kra
					frappe.log_error("KR Migration: Duplicate", f"Duplicate: {metric_short} -> {kra_short}")
			except Exception as e:
				# Truncate all values to prevent nested error log issues
				metric_short = metric_name[:40] if len(metric_name) > 40 else metric_name
				error_msg = str(e)[:60] if len(str(e)) > 60 else str(e)
				# Remove any nested error log references that might cause issues
				if "Error Log" in error_msg:
					error_msg = "Previous error occurred (see details in description)"
				frappe.log_error("KR Migration: Error", f"Error for {metric_short}: {error_msg}")
				continue
	# Step 4: Update all Measurable records to use KR link
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
			metric_short = metric_name[:60] if len(metric_name) > 60 else metric_name
			frappe.log_error("KR Migration: No Mapping", f"No mapping for: {metric_short}")
			failed_count += 1
			continue
		try:
			# Update the metric_name field to store KR name
			# This will work when the field type changes to Link
			frappe.db.set_value("Measurable", measurable.name, "metric_name", kra_name)
			updated_count += 1
		except Exception as e:
			measurable_short = measurable.name[:40] if len(measurable.name) > 40 else measurable.name
			error_msg = str(e)[:60] if len(str(e)) > 60 else str(e)
			# Remove any nested error log references
			if "Error Log" in error_msg:
				error_msg = "Update failed (see details in description)"
			frappe.log_error("KR Migration: Update Failed", f"Error updating {measurable_short}: {error_msg}")
			failed_count += 1

	frappe.log_error("KR Migration: Complete", f"Migration completed: {updated_count} updated, {failed_count} failed, {len(kra_mapping)} KRs created")

	frappe.db.commit()
