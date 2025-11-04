# Copyright (c) 2025, Phamos and contributors
# For license information, please see license.txt

import frappe
from frappe.model.document import Document

class OKRDependency(Document):
    def validate(self):
        self.validate_dependency_data()
    
    def validate_dependency_data(self):
        """Validate dependency data"""
        if not self.dependency_description:
            frappe.throw("Dependency description is required")
        
        if self.impact_level == "Critical" and not self.expected_completion:
            frappe.msgprint("Consider setting expected completion date for critical dependencies")
    
    def on_update(self):
        """Update parent OKR when dependency status changes"""
        if hasattr(self, 'parent') and self.parent:
            try:
                parent_obj = frappe.get_doc("OKR", self.parent)
                parent_obj.save()  # This will trigger progress recalculation
            except Exception as e:
                frappe.log_error(f"Error updating parent OKR: {str(e)}") 