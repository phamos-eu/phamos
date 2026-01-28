# Copyright (c) 2025, Phamos and contributors
# For license information, please see license.txt

import frappe
from frappe.utils import nowdate, add_days, getdate
from frappe.model.document import Document

class OKR(Document):
    def validate(self):
        self.validate_measurables()
        # self.validate_okr_structure()
    
    def before_save(self):
        self.update_measurable_targets()
        # Calculate and update progress based on measurables
        self.progress = self.calculate_progress()
        # Calculate OKR score (0.0-1.0)
        self.okr_score = self.calculate_okr_score()
        # Set next check-in date
        self.set_next_check_in()
    
    def after_save(self):
        self.update_parent_okr_progress()
    
    def calculate_progress(self):
        """Calculate overall progress from measurables"""
        if not self.measurables:
            return 0
        
        total_percent = 0
        valid_measurables = 0
        
        for measurable in self.measurables:
            if measurable.percent_complete is not None:
                total_percent += measurable.percent_complete
                valid_measurables += 1
        
        if valid_measurables == 0:
            return 0
        
        return total_percent / valid_measurables
    
    def calculate_okr_score(self):
        """Calculate OKR score (0.0-1.0) based on KR achievement"""
        if not self.measurables:
            return 0.0
        
        total_score = 0
        valid_krs = 0
        
        for kr in self.measurables:
            if (kr.committed_target and kr.baseline_value and 
                kr.current_value is not None):
                
                # Calculate progress from baseline to committed target
                baseline_to_target = kr.committed_target - kr.baseline_value
                if baseline_to_target == 0:
                    score = 1.0 if kr.current_value >= kr.committed_target else 0.0
                else:
                    progress = (kr.current_value - kr.baseline_value) / baseline_to_target
                    score = min(max(progress, 0.0), 1.0)  # Clamp between 0.0 and 1.0
                
                total_score += score
                valid_krs += 1
        
        if valid_krs == 0:
            return 0.0
        
        return total_score / valid_krs
    
    def validate_measurables(self):
        """Validate measurable data"""
        for measurable in self.measurables:
            if measurable.baseline_value == measurable.committed_target:
                frappe.throw(f"Baseline value cannot be equal to committed target for KR: {measurable.metric_name}")
            
            if measurable.stretch_target and measurable.stretch_target <= measurable.committed_target:
                frappe.throw(f"Stretch target must be higher than committed target for KR: {measurable.metric_name}")
    
    def get_parent_info(self):
        """Get parent information (KR or OKR)"""
        if self.parent_kra:
            try:
                return {
                    "type": "KR",
                    "name": self.parent_kra,
                    "doctype": "KR",
                    "doc": frappe.get_doc("KR", self.parent_kra)
                }
            except frappe.DoesNotExistError:
                return None
        elif self.parent_okr:
            try:
                return {
                    "type": "OKR",
                    "name": self.parent_okr,
                    "doctype": "OKR",
                    "doc": frappe.get_doc("OKR", self.parent_okr)
                }
            except frappe.DoesNotExistError:
                return None
        return None
    
    def _get_status_category(self, okr):
        """Get status category for an OKR based on progress and target date"""
        progress = okr.get('progress', 0) or 0
        target_date = okr.get('target_date')
        
        if not target_date:
            if progress >= 100:
                return 'completed'
            elif progress >= 70:
                return 'on_track'
            else:
                return 'at_risk'
        
        from frappe.utils import getdate, nowdate
        days_remaining = (getdate(target_date) - getdate(nowdate())).days
        
        if progress >= 100:
            return 'completed'
        elif days_remaining < 0:
            return 'overdue'
        elif days_remaining <= 7:
            if progress < 80:
                return 'at_risk'
            else:
                return 'on_track'
        elif progress < 60:
            return 'at_risk'
        else:
            return 'on_track'
    
    def validate_okr_structure(self):
        """Validate OKR structure and hierarchy"""
        if self.okr_type == "Company" and self.parent_okr:
            frappe.throw("Company OKRs cannot have parent OKRs")
        
        if self.okr_type != "Company" and not self.parent_okr:
            frappe.msgprint("Consider linking this OKR to a Company OKR for better alignment")
    
    def update_measurable_targets(self):
        """Update measurable percent complete for all measurables"""
        for measurable in self.measurables:
            if measurable.current_value is not None:
                if measurable.committed_target is not None and measurable.baseline_value is not None:
                    baseline_to_target = measurable.committed_target - measurable.baseline_value
                    if baseline_to_target != 0:
                        progress = (measurable.current_value - measurable.baseline_value) / baseline_to_target
                        measurable.percent_complete = min(max(progress * 100, 0), 100)
                    else:
                        # If baseline equals target, check if current value meets or exceeds target
                        measurable.percent_complete = 100 if measurable.current_value >= measurable.committed_target else 0
                else:
                    measurable.percent_complete = 0
            else:
                measurable.percent_complete = 0
    
    def set_next_check_in(self):
        """Set next check-in date based on frequency"""
        if not self.check_in_frequency:
            return
        
        if not self.last_check_in:
            self.last_check_in = nowdate()
        
        frequency_days = {
            "Weekly": 7,
            "Bi-weekly": 14,
            "Monthly": 30
        }
        
        days_to_add = frequency_days.get(self.check_in_frequency, 7)
        self.next_check_in = add_days(self.last_check_in, days_to_add)
    
    def update_parent_okr_progress(self):
        """Update parent progress if this is a child (OKR parent only, KR is read-only)"""
        # Only update if parent is OKR (KR is a standard doctype, we can't update it)
        if self.parent_okr:
            try:
                parent = frappe.get_doc("OKR", self.parent_okr)
                parent.progress = parent.calculate_progress()
                parent.okr_score = parent.calculate_okr_score()
                parent.save()
            except Exception as e:
                frappe.log_error(f"Error updating parent OKR progress: {str(e)}")
    
    def get_measurable_summary(self):
        """Get comprehensive summary of measurables with market-standard metrics"""
        if not self.measurables:
            return {
                "total": 0,
                "completed": 0,
                "in_progress": 0,
                "not_started": 0,
                "at_risk": 0,
                "on_track": 0,
                "ahead_of_schedule": 0,
                "average_progress": 0,
                "average_confidence": 0,
                "leading_indicators": 0,
                "lagging_indicators": 0,
                "overdue_count": 0,
                "due_soon_count": 0,
                "progress_distribution": {
                    "excellent": 0,  # 90-100%
                    "good": 0,       # 70-89%
                    "fair": 0,       # 50-69%
                    "poor": 0,       # 30-49%
                    "critical": 0    # 0-29%
                },
                "confidence_distribution": {
                    "high": 0,       # 80-100%
                    "medium": 0,     # 60-79%
                    "low": 0         # 0-59%
                }
            }
        
        from frappe.utils import getdate, add_days, nowdate
        
        total = len(self.measurables)
        completed = 0
        in_progress = 0
        not_started = 0
        at_risk = 0
        on_track = 0
        ahead_of_schedule = 0
        total_progress = 0
        total_confidence = 0
        leading_indicators = 0
        lagging_indicators = 0
        overdue_count = 0
        due_soon_count = 0
        
        # Distribution counters
        progress_dist = {"excellent": 0, "good": 0, "fair": 0, "poor": 0, "critical": 0}
        confidence_dist = {"high": 0, "medium": 0, "low": 0}
        
        today = getdate(nowdate())
        
        for measurable in self.measurables:
            # Basic status counting
            if measurable.percent_complete is None:
                not_started += 1
            elif measurable.percent_complete >= 100:
                completed += 1
            elif measurable.percent_complete > 0:
                in_progress += 1
            else:
                not_started += 1
            
            # Progress tracking
            if measurable.percent_complete is not None:
                total_progress += measurable.percent_complete
                
                # Progress distribution
                if measurable.percent_complete >= 90:
                    progress_dist["excellent"] += 1
                elif measurable.percent_complete >= 70:
                    progress_dist["good"] += 1
                elif measurable.percent_complete >= 50:
                    progress_dist["fair"] += 1
                elif measurable.percent_complete >= 30:
                    progress_dist["poor"] += 1
                else:
                    progress_dist["critical"] += 1
                
                # Risk assessment based on progress vs time
                if measurable.time_bound:
                    days_remaining = (getdate(measurable.time_bound) - today).days
                    progress_ratio = measurable.percent_complete / 100
                    if days_remaining < 0:  # Overdue
                        overdue_count += 1
                        at_risk += 1
                    elif days_remaining <= 7:  # Due soon
                        due_soon_count += 1
                        if progress_ratio < 0.8:
                            at_risk += 1
                        elif progress_ratio >= 1.0:
                            ahead_of_schedule += 1
                        else:
                            on_track += 1
                    else:  # Normal timeline
                        if progress_ratio < 0.6:
                            at_risk += 1
                        elif progress_ratio >= 1.0:
                            ahead_of_schedule += 1
                        else:
                            on_track += 1
            
            # Confidence tracking
            if measurable.confidence_level is not None:
                total_confidence += measurable.confidence_level
                
                # Confidence distribution
                if measurable.confidence_level >= 80:
                    confidence_dist["high"] += 1
                elif measurable.confidence_level >= 60:
                    confidence_dist["medium"] += 1
                else:
                    confidence_dist["low"] += 1
            
            # KR Type counting
            if measurable.kr_type == "Leading":
                leading_indicators += 1
            elif measurable.kr_type == "Lagging":
                lagging_indicators += 1
        
        return {
            "total": total,
            "completed": completed,
            "in_progress": in_progress,
            "not_started": not_started,
            "at_risk": at_risk,
            "on_track": on_track,
            "ahead_of_schedule": ahead_of_schedule,
            "average_progress": round(total_progress / total, 1) if total > 0 else 0,
            "average_confidence": round(total_confidence / total, 1) if total > 0 else 0,
            "leading_indicators": leading_indicators,
            "lagging_indicators": lagging_indicators,
            "overdue_count": overdue_count,
            "due_soon_count": due_soon_count,
            "progress_distribution": progress_dist,
            "confidence_distribution": confidence_dist,
            "completion_rate": round((completed / total) * 100, 1) if total > 0 else 0,
            "risk_score": round((at_risk / total) * 100, 1) if total > 0 else 0,
            "overall_health": self._calculate_overall_health(progress_dist, confidence_dist, overdue_count, total)
        }
    
    def _calculate_overall_health(self, progress_dist, confidence_dist, overdue_count, total):
        """Calculate overall health score (0-100)"""
        if total == 0:
            # If no measurables, calculate health based on okr progress and confidence
            if hasattr(self, 'progress') and hasattr(self, 'confidence_level'):
                progress_score = self.progress or 0
                confidence_score = self.confidence_level or 50
                return round((progress_score + confidence_score) / 2, 1)
            return 0
        
        # Weight factors
        progress_weight = 0.4
        confidence_weight = 0.3
        timeline_weight = 0.3
        
        # Progress score (0-100)
        progress_score = (
            progress_dist["excellent"] * 100 +
            progress_dist["good"] * 80 +
            progress_dist["fair"] * 60 +
            progress_dist["poor"] * 40 +
            progress_dist["critical"] * 20
        ) / total
        
        # Confidence score (0-100) - handle case where no confidence data
        confidence_score = 0
        if sum(confidence_dist.values()) > 0:
            confidence_score = (
                confidence_dist["high"] * 100 +
                confidence_dist["medium"] * 70 +
                confidence_dist["low"] * 40
            ) / sum(confidence_dist.values())
        else:
            confidence_score = 50  # Default to neutral if no confidence data
        
        # Timeline score (0-100) - penalize overdue items
        timeline_score = max(0, 100 - (overdue_count / total) * 50)
        
        # Calculate weighted average
        overall_health = (
            progress_score * progress_weight +
            confidence_score * confidence_weight +
            timeline_score * timeline_weight
        )
        
        return round(overall_health, 1)
    

    
    def get_risk_summary(self):
        """Get summary of risks and blockers"""
        if not self.blockers:
            return {
                "total_blockers": 0,
                "critical_blockers": 0,
                "resolved_blockers": 0
            }
        
        total_blockers = len(self.blockers)
        critical_blockers = len([b for b in self.blockers if b.priority == "Critical"])
        resolved_blockers = len([b for b in self.blockers if b.status == "Resolved"])
        
        return {
            "total_blockers": total_blockers,
            "critical_blockers": critical_blockers,
            "resolved_blockers": resolved_blockers
        }
    
    def get_okr_grade(self):
        """Get OKR grade based on score"""
        score = self.okr_score or 0.0
        
        if score >= 0.7:
            return "A"
        elif score >= 0.4:
            return "B"
        elif score >= 0.1:
            return "C"
        else:
            return "D"
    
    @staticmethod
    @frappe.whitelist()
    def get_measurable_summary_static(okr_name):
        """Static method to get measurable summary for frontend"""
        doc = frappe.get_doc("OKR", okr_name)
        return doc.get_measurable_summary()
    
# Server-side functions for frontend calls
@frappe.whitelist()
def get_measurable_summary_for_frontend(okr_name):
    """Get measurable summary for frontend display"""
    doc = frappe.get_doc("OKR", okr_name)
    return doc.get_measurable_summary()

@frappe.whitelist()
def get_child_okrs(okr_name):
    """Get child OKRs for an OKR (OKRs that have this OKR as their parent_okr)"""
    child_okrs = []
    
    if not okr_name:
        return child_okrs
    
    # Get OKRs that have this OKR as parent (parent_okr = this OKR's name)
    child_okrs = frappe.get_all(
        "OKR",
        filters={"parent_okr": okr_name},
        fields=["name", "title", "progress", "okr_score", "responsible_person", 
               "target_date", "risk_status", "confidence_level", "okr_type"],
        order_by="creation desc"
    )
    
    # Add status category and format data
    for child in child_okrs:
        child['status_category'] = _get_status_category_for_okr(child)
        child['progress_display'] = f"{child.get('progress', 0):.1f}%"
        child['score_display'] = f"{child.get('okr_score', 0):.2f}"
    
    return child_okrs

def _get_status_category_for_okr(okr):
    """Get status category for an OKR based on progress and target date"""
    progress = okr.get('progress', 0) or 0
    target_date = okr.get('target_date')
    
    if not target_date:
        if progress >= 100:
            return 'completed'
        elif progress >= 70:
            return 'on_track'
        else:
            return 'at_risk'
    
    from frappe.utils import getdate, nowdate
    days_remaining = (getdate(target_date) - getdate(nowdate())).days
    
    if progress >= 100:
        return 'completed'
    elif days_remaining < 0:
        return 'overdue'
    elif days_remaining <= 7:
        if progress < 80:
            return 'at_risk'
        else:
            return 'on_track'
    elif progress < 60:
        return 'at_risk'
    else:
        return 'on_track'

@frappe.whitelist()
def get_okr_type_options():
    """Fetch okr_type options from OKR Setting's child table."""
    setting = frappe.get_single("OKR Setting")
    return [row.okr_type for row in setting.okr_types]
