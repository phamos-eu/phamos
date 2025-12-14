# Copyright (c) 2025, Phamos and contributors
# For license information, please see license.txt

import frappe
from frappe.model.document import Document

class OKRBlocker(Document):
    def validate(self):
        self.validate_blocker_data()
    
    def validate_blocker_data(self):
        """Validate blocker data"""
        if not self.blocker_description:
            frappe.throw("Blocker description is required")
        
        if self.priority == "Critical" and not self.resolution_plan:
            frappe.msgprint("Consider adding a resolution plan for critical blockers")
    
    def on_update(self):
        """Update parent OKR when blocker status changes"""
        if hasattr(self, 'parent') and self.parent:
            try:
                parent_obj = frappe.get_doc("OKR", self.parent)
                parent_obj.save()  # This will trigger progress recalculation
            except Exception as e:
                frappe.log_error(f"Error updating parent OKR: {str(e)}") 