"""
Patch to migrate existing OKR records to use parent_type field.

This patch:
1. Reloads OKR doctype to clear cached link metadata
2. Sets parent_type = "OKR" for records with parent_okr
3. Sets parent_type = "" (blank) for records without any parent
4. Converts existing "None" values to blank
5. Ensures data consistency for the new toggle-based parent selection
6. Clears cache to remove stale link metadata
"""

import frappe


def execute():
	# Step 1: Clear cache first to remove any stale link metadata
	frappe.clear_cache()
	
	# Step 2: Reload OKR doctype to ensure parent_type field exists and links are updated
	frappe.reload_doc("OKR Addon", "doctype", "OKR")
	
	# Step 3: Clear cache again after reload to ensure fresh metadata
	frappe.clear_cache()
	
	# Step 4: Get all OKR records
	all_okrs = frappe.db.sql("""
		SELECT name, parent_okr, parent_kra, parent_type
		FROM `tabOKR`
	""", as_dict=True)
	
	if not all_okrs:
		frappe.log_error("No OKR records found to migrate", "OKR Parent Type Migration")
		return
	
	frappe.log_error(f"Found {len(all_okrs)} OKR records to migrate", "OKR Parent Type Migration")
	
	updated_count = 0
	okr_parent_count = 0
	kra_parent_count = 0
	none_count = 0
	
	for okr in all_okrs:
		parent_type = None
		
		# If parent_type already exists, check if it needs conversion
		existing_parent_type = okr.get('parent_type')
		if existing_parent_type == "None":
			# Convert "None" to blank
			parent_type = ""
			none_count += 1
		elif existing_parent_type in ["KRA", "OKR"]:
			# Keep existing valid value
			parent_type = existing_parent_type
			if parent_type == "OKR":
				okr_parent_count += 1
			else:
				kra_parent_count += 1
		else:
			# Determine parent_type based on existing fields
			if okr.get('parent_okr'):
				parent_type = "OKR"
				okr_parent_count += 1
			elif okr.get('parent_kra'):
				parent_type = "KRA"
				kra_parent_count += 1
			else:
				parent_type = ""  # Blank instead of "None"
				none_count += 1
		
		try:
			# Update parent_type field
			frappe.db.set_value("OKR", okr.name, "parent_type", parent_type)
			updated_count += 1
		except Exception as e:
			frappe.log_error(f"Error updating OKR {okr.name}: {str(e)}", "OKR Parent Type Migration")
	
	frappe.log_error(
		f"OKR parent_type migration completed: {updated_count} updated "
		f"(OKR parent: {okr_parent_count}, KRA parent: {kra_parent_count}, None: {none_count})",
		"OKR Parent Type Migration"
	)
	
	frappe.db.commit()

