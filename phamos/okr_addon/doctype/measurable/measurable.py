# Copyright (c) 2025, Phamos and contributors
# For license information, please see license.txt

import frappe
from frappe.model.document import Document

class Measurable(Document):
    def validate(self):
        self.validate_measurable_data()
        self.auto_calculate_percent_complete()
    
    def validate_measurable_data(self):
        """Validate measurable data"""
        if not self.metric_name:
            frappe.throw("Key Result name is required")
        
        if not self.baseline_value and self.baseline_value != 0:
            frappe.throw("Baseline value is required")
        
        if not self.committed_target and self.committed_target != 0:
            frappe.throw("Committed target is required")
        
        # Validate that stretch target is higher than committed target
        if self.stretch_target and self.committed_target:
            if self.stretch_target <= self.committed_target:
                frappe.throw("Stretch target must be higher than committed target")
        
        # Validate current value is within reasonable bounds
        if self.current_value is not None and self.baseline_value is not None:
            if self.current_value < 0:
                frappe.throw("Current value cannot be negative")
            
            # Ensure current_value is properly converted to float
            try:
                self.current_value = float(self.current_value)
            except (ValueError, TypeError):
                frappe.throw("Current value must be a valid number")
    
    def auto_calculate_percent_complete(self):
        """Automatically calculate percent complete when current value is updated"""
        if (self.current_value is not None and 
            self.baseline_value is not None and 
            self.committed_target is not None):
            
            # Calculate progress from baseline to committed target
            baseline_to_target = self.committed_target - self.baseline_value
            
            if baseline_to_target == 0:
                # If baseline equals target, check if current value meets or exceeds target
                self.percent_complete = 100 if self.current_value >= self.committed_target else 0
            else:
                # Calculate percentage progress
                progress = (self.current_value - self.baseline_value) / baseline_to_target
                self.percent_complete = min(max(progress * 100, 0), 100)
    
    def on_update(self):
        """Update parent OKR when measurable changes"""
        if hasattr(self, 'parent') and self.parent:
            try:
                parent_obj = frappe.get_doc("OKR", self.parent)
                parent_obj.save()  # This will trigger progress recalculation
            except Exception as e:
                frappe.log_error(f"Error updating parent OKR: {str(e)}")
    
    def calculate_progress(self):
        """Calculate progress from baseline to committed target"""
        if not self.baseline_value or not self.committed_target or self.current_value is None:
            return 0
        
        baseline_to_target = self.committed_target - self.baseline_value
        if baseline_to_target == 0:
            return 100 if self.current_value >= self.committed_target else 0
        
        progress = (self.current_value - self.baseline_value) / baseline_to_target
        return min(max(progress * 100, 0), 100) 