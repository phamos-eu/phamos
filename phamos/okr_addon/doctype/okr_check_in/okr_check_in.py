# Copyright (c) 2025, Phamos and contributors
# For license information, please see license.txt

import frappe
from frappe.utils import nowdate
from frappe.model.document import Document

class OKRCheckIn(Document):
    def validate(self):
        self.validate_check_in_data()
    
    def before_save(self):
        self.update_okr_progress()
    
    def validate_check_in_data(self):
        """Validate check-in data"""
        if self.progress_update and (self.progress_update < 0 or self.progress_update > 100):
            frappe.throw("Progress update must be between 0 and 100")
        
        if self.confidence_update and (self.confidence_update < 0 or self.confidence_update > 100):
            frappe.throw("Confidence update must be between 0 and 100")
    
    def update_okr_progress(self):
        """Update the linked OKR with check-in data"""
        if not self.okr:
            return
        
        try:
            obj = frappe.get_doc("OKR", self.okr)
            
            # Update progress if provided
            if self.progress_update is not None:
                obj.progress = self.progress_update
            
            # Update confidence if provided
            if self.confidence_update is not None:
                obj.confidence_level = self.confidence_update
            
            # Update last check-in date
            obj.last_check_in = self.check_in_date or nowdate()
            
            # Update risk status based on overall status
            if self.overall_status == "Off Track":
                obj.risk_status = "Red"
            elif self.overall_status == "At Risk":
                obj.risk_status = "Yellow"
            elif self.overall_status == "On Track":
                obj.risk_status = "Green"
            
            obj.save(ignore_permissions=True)
            
        except Exception as e:
            frappe.log_error(f"Error updating OKR progress: {str(e)}")
    
    def get_previous_check_in(self):
        """Get the previous check-in for this OKR"""
        if not self.okr:
            return None
        
        return frappe.get_all(
            "OKR Check In",
            filters={
                "okr": self.okr,
                "name": ["!=", self.name]
            },
            order_by="check_in_date desc",
            limit=1
        )
    
    def get_progress_trend(self):
        """Get progress trend from previous check-ins"""
        previous_check_ins = frappe.get_all(
            "OKR Check In",
            filters={
                "okr": self.okr,
                "name": ["!=", self.name]
            },
            fields=["progress_update", "check_in_date"],
            order_by="check_in_date desc",
            limit=5
        )
        
        if len(previous_check_ins) < 2:
            return "Insufficient data"
        
        # Calculate trend
        recent_progress = previous_check_ins[0].progress_update or 0
        older_progress = previous_check_ins[-1].progress_update or 0
        
        if recent_progress > older_progress:
            return "Improving"
        elif recent_progress < older_progress:
            return "Declining"
        else:
            return "Stable"
            