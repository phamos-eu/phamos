import frappe
from frappe import _
from datetime import datetime, timedelta
import json
from frappe.utils import getdate, nowdate, add_days

def get_context(context):
    context.no_cache = 1
    context.title = _("OKR Dashboard")

@frappe.whitelist()
def get_dashboard_data(filters = None, page = 1, items_per_page = 50):
    """Get comprehensive dashboard data with advanced filtering and pagination"""
    try:
        # Parse filters
        if filters:
            filters = json.loads(filters)
        else:
            filters = {}
        
        # Convert page and items_per_page to integers
        page = int(page) if page else 1
        items_per_page = int(items_per_page) if items_per_page else 50
        
        # Get all OKRs for hierarchy building (no pagination for data)
        okrs, total_count = get_filtered_okrs(filters, 1, 1000)  # Get all OKRs
        
        # Apply pagination to the returned data for UI
        start_idx = (page - 1) * items_per_page
        end_idx = start_idx + items_per_page
        paginated_okrs = okrs[start_idx:end_idx]
        
        # Calculate comprehensive statistics using all OKRs
        stats = calculate_comprehensive_stats(okrs)
        
        # Get hierarchical data using all OKRs
        hierarchy_data = get_hierarchy_data(okrs)
        
        # Get performance metrics using all OKRs
        performance_metrics = get_performance_metrics(okrs)
        
        # Get timeline data
        timeline_data = get_timeline_data(filters)
        
        # Get risk analysis using all OKRs
        risk_analysis = get_risk_analysis(okrs)
        
        # Get team/individual performance using all OKRs
        team_performance = get_team_performance(okrs)
        
        response_data = {
            "objectives": okrs,  # Return all OKRs for hierarchy (keeping key as 'objectives' for frontend compatibility)
            "stats": stats,
            "hierarchy_data": hierarchy_data,
            "performance_metrics": performance_metrics,
            "timeline_data": timeline_data,
            "risk_analysis": risk_analysis,
            "team_performance": team_performance,
            "filters": filters,
            "total_items": total_count,
            "current_page": page,
            "items_per_page": items_per_page,
            "total_pages": (total_count + items_per_page - 1) // items_per_page
        }
        
        return response_data
    except Exception as e:
        frappe.log_error(f"Error in get_dashboard_data: {str(e)}")
        return {"error": str(e)}

def get_filtered_okrs(filters, page=1, items_per_page=50):
    """Get OKRs with advanced filtering and pagination"""
    filter_conditions = {}
    
    # Date filtering
    if filters.get('date_range'):
        if filters['date_range'] == 'this_month':
            start_date = getdate().replace(day=1)
            end_date = (start_date + timedelta(days=32)).replace(day=1) - timedelta(days=1)
            filter_conditions['creation'] = ['between', [start_date, end_date]]
        elif filters['date_range'] == 'this_quarter':
            current_month = getdate().month
            quarter_start_month = ((current_month - 1) // 3) * 3 + 1
            start_date = getdate().replace(month=quarter_start_month, day=1)
            end_date = (start_date + timedelta(days=92)).replace(day=1) - timedelta(days=1)
            filter_conditions['creation'] = ['between', [start_date, end_date]]
        elif filters['date_range'] == 'custom' and filters.get('from_date') and filters.get('to_date'):
            filter_conditions['creation'] = ['between', [filters['from_date'], filters['to_date']]]
    
    # Status filtering
    if filters.get('status'):
        if filters['status'] == 'completed':
            filter_conditions['progress'] = 100
        elif filters['status'] == 'in_progress':
            filter_conditions['progress'] = ['>', 0]
        elif filters['status'] == 'not_started':
            filter_conditions['progress'] = 0
        elif filters['status'] == 'at_risk':
            # This will be handled in post-processing
            pass
    
    # OKR Type filtering
    if filters.get('okr_type'):
        filter_conditions['okr_type'] = filters['okr_type']
    
    # Responsible person filtering
    if filters.get('responsible_person'):
        filter_conditions['responsible_person'] = filters['responsible_person']
    
    # Get total count first
    total_count = frappe.db.count("OKR", filters=filter_conditions)
    
    # Calculate offset for pagination
    offset = (page - 1) * items_per_page
    
    # Get OKRs with pagination
    okrs = frappe.get_all(
        "OKR",
        filters=filter_conditions,
        fields=[
            "name", "title", "progress", "responsible_person", "target_date", 
            "last_check_in", "okr_type", "parent_objective", "parent_okr", "creation", "modified",
            "owner", "docstatus", "idx", "okr_score", "confidence_level"
        ],
        order_by="creation desc",
        limit_start=offset,
        limit_page_length=items_per_page
    )
    
    # Post-process for complex filters
    if filters.get('status') == 'at_risk':
        okrs = [obj for obj in okrs if is_at_risk(obj)]
    
    # Add computed fields
    for okr in okrs:
        okr['measurables_summary'] = get_measurables_summary(okr['name'])
        okr['health_score'] = calculate_health_score(okr)
        okr['days_remaining'] = calculate_days_remaining(okr)
        okr['status_category'] = get_status_category(okr)
        okr['child_objectives'] = get_child_objectives(okr['name'])
    
    return okrs, total_count

def calculate_comprehensive_stats(okrs):
    """Calculate comprehensive dashboard statistics"""
    total = len(okrs)
    if total == 0:
        return get_empty_stats()
    
    # Basic counts
    completed = sum(1 for obj in okrs if obj.progress == 100)
    in_progress = sum(1 for obj in okrs if 0 < obj.progress < 100)
    not_started = sum(1 for obj in okrs if obj.progress == 0)
    at_risk = sum(1 for obj in okrs if obj['status_category'] == 'at_risk')
    on_track = sum(1 for obj in okrs if obj['status_category'] == 'on_track')
    ahead_schedule = sum(1 for obj in okrs if obj['status_category'] == 'ahead_schedule')
    
    # Progress calculations
    overall_progress = sum(obj.progress or 0 for obj in okrs) / total
    avg_confidence = sum(obj.confidence_level or 0 for obj in okrs) / total
    avg_okr_score = sum(obj.okr_score or 0 for obj in okrs) / total
    avg_health_score = sum(obj['health_score'] or 0 for obj in okrs) / total
    
    # Type distribution
    company_okrs = sum(1 for obj in okrs if obj.okr_type == 'Company')
    team_okrs = sum(1 for obj in okrs if obj.okr_type == 'Team')
    individual_okrs = sum(1 for obj in okrs if obj.okr_type == 'Individual')
    
    # Timeline analysis
    overdue = sum(1 for obj in okrs if obj['days_remaining'] < 0)
    due_soon = sum(1 for obj in okrs if 0 <= obj['days_remaining'] <= 7)
    
    return {
        "total": total,
        "completed": completed,
        "in_progress": in_progress,
        "not_started": not_started,
        "at_risk": at_risk,
        "on_track": on_track,
        "ahead_schedule": ahead_schedule,
        "overall_progress": round(overall_progress, 1),
        "avg_confidence": round(avg_confidence, 1),
        "avg_okr_score": round(avg_okr_score, 2),
        "avg_health_score": round(avg_health_score, 1),
        "completion_rate": round((completed / total) * 100, 1),
        "risk_rate": round((at_risk / total) * 100, 1),
        "type_distribution": {
            "company": company_okrs,
            "team": team_okrs,
            "individual": individual_okrs
        },
        "timeline": {
            "overdue": overdue,
            "due_soon": due_soon,
            "on_time": total - overdue - due_soon
        }
    }

def get_hierarchy_data(okrs):
    """Get parent-child relationship data"""
    hierarchy = {
        "company_okrs": [],
        "team_okrs": [],
        "individual_okrs": [],
        "orphaned_okrs": []
    }
    
    for okr in okrs:
        if okr.okr_type == 'Company':
            okr['children'] = get_child_objectives(okr.name)
            hierarchy['company_okrs'].append(okr)
        elif okr.okr_type == 'Team':
            if okr.parent_okr:
                hierarchy['team_okrs'].append(okr)
            else:
                hierarchy['orphaned_okrs'].append(okr)
        elif okr.okr_type == 'Individual':
            if okr.parent_okr:
                hierarchy['individual_okrs'].append(okr)
            else:
                hierarchy['orphaned_okrs'].append(okr)
    
    return hierarchy

def get_performance_metrics(okrs):
    """Get detailed performance metrics"""
    if not okrs:
        return {}
    
    # Progress distribution
    progress_dist = {"excellent": 0, "good": 0, "fair": 0, "poor": 0, "critical": 0}
    confidence_dist = {"high": 0, "medium": 0, "low": 0}
    
    for obj in okrs:
        # Progress distribution
        if obj.progress >= 90:
            progress_dist["excellent"] += 1
        elif obj.progress >= 70:
            progress_dist["good"] += 1
        elif obj.progress >= 50:
            progress_dist["fair"] += 1
        elif obj.progress >= 30:
            progress_dist["poor"] += 1
        else:
            progress_dist["critical"] += 1
        
        # Confidence distribution
        confidence_level = obj.confidence_level or 0
        if confidence_level >= 80:
            confidence_dist["high"] += 1
        elif confidence_level >= 60:
            confidence_dist["medium"] += 1
        else:
            confidence_dist["low"] += 1
    
    total = len(okrs)
    
    return {
        "progress_distribution": {k: round((v/total)*100, 1) for k, v in progress_dist.items()},
        "confidence_distribution": {k: round((v/total)*100, 1) for k, v in confidence_dist.items()},
        "avg_health_score": round(sum(obj['health_score'] for obj in okrs) / total, 1)
    }

def get_timeline_data(filters):
    """Get timeline data for charts"""
    months = []
    progress_data = []
    confidence_data = []
    
    # Build filter conditions based on applied filters
    filter_conditions = {}
    
    # Date filtering
    if filters.get('date_range'):
        if filters['date_range'] == 'this_month':
            start_date = getdate().replace(day=1)
            end_date = (start_date + timedelta(days=32)).replace(day=1) - timedelta(days=1)
            filter_conditions['creation'] = ['between', [start_date, end_date]]
        elif filters['date_range'] == 'this_quarter':
            current_month = getdate().month
            quarter_start_month = ((current_month - 1) // 3) * 3 + 1
            start_date = getdate().replace(month=quarter_start_month, day=1)
            end_date = (start_date + timedelta(days=92)).replace(day=1) - timedelta(days=1)
            filter_conditions['creation'] = ['between', [start_date, end_date]]
        elif filters['date_range'] == 'custom' and filters.get('from_date') and filters.get('to_date'):
            filter_conditions['creation'] = ['between', [filters['from_date'], filters['to_date']]]
    
    # OKR Type filtering
    if filters.get('okr_type') and filters['okr_type'] != 'all':
        filter_conditions['okr_type'] = filters['okr_type']
    
    # Responsible person filtering
    if filters.get('responsible_person') and filters['responsible_person'] != 'all':
        filter_conditions['responsible_person'] = filters['responsible_person']
    
    for i in range(11, -1, -1):
        date = datetime.now() - timedelta(days=30*i)
        month_name = date.strftime("%b")
        months.append(month_name)
        
        # Calculate metrics for this month with filters
        start_date = date.replace(day=1)
        end_date = (start_date + timedelta(days=32)).replace(day=1) - timedelta(days=1)
        
        # Add month filter to existing filters
        month_filters = filter_conditions.copy()
        month_filters['creation'] = ['between', [start_date, end_date]]
        
        month_okrs = frappe.get_all(
            "OKR",
            filters=month_filters,
            fields=["progress", "confidence_level"]
        )
        
        avg_progress = 0
        avg_confidence = 0
        if month_okrs:
            avg_progress = sum(obj.progress or 0 for obj in month_okrs) / len(month_okrs)
            avg_confidence = sum(obj.confidence_level or 0 for obj in month_okrs) / len(month_okrs)
        
        progress_data.append(round(avg_progress, 1))
        confidence_data.append(round(avg_confidence, 1))

    return {
        "labels": months,
        "progress": progress_data,
        "confidence": confidence_data
    }

def get_risk_analysis(okrs):
    """Get risk analysis data"""
    if not okrs:
        return {}
    
    risk_factors = {
        "overdue": 0,
        "low_confidence": 0,
        "low_progress": 0,
        "no_measurables": 0,
        "no_check_ins": 0
    }
    
    for obj in okrs:
        # Overdue
        if obj['days_remaining'] < 0:
            risk_factors["overdue"] += 1
        
        # Risk factors
        if obj.confidence_level and obj.confidence_level < 50:
            risk_factors["low_confidence"] += 1
        
        # Low progress
        if obj.progress and obj.progress < 30:
            risk_factors["low_progress"] += 1
        
        # No measurables
        if obj['measurables_summary']['total'] == 0:
            risk_factors["no_measurables"] += 1
        
        # No recent check-ins
        if obj.last_check_in:
            days_since_checkin = (getdate() - getdate(obj.last_check_in)).days
            if days_since_checkin > 14:  # More than 2 weeks
                risk_factors["no_check_ins"] += 1
    
    total = len(okrs)
    return {
        "risk_factors": risk_factors,
        "risk_percentages": {k: round((v/total)*100, 1) for k, v in risk_factors.items()},
        "high_risk_count": sum(1 for obj in okrs if count_risk_factors(obj) >= 2)
    }

def get_team_performance(okrs):
    """Get team and individual performance data"""
    team_data = {}
    individual_data = {}
    
    for obj in okrs:
        if obj.responsible_person:
            person = obj.responsible_person
            if obj.okr_type == 'Team':
                if person not in team_data:
                    team_data[person] = {"okrs": [], "avg_progress": 0, "avg_confidence": 0}
                team_data[person]["okrs"].append(obj)
            elif obj.okr_type == 'Individual':
                if person not in individual_data:
                    individual_data[person] = {"okrs": [], "avg_progress": 0, "avg_confidence": 0}
                individual_data[person]["okrs"].append(obj)
    
    # Calculate averages
    for person, data in team_data.items():
        if data["okrs"]:
            data["avg_progress"] = round(sum(obj.progress or 0 for obj in data["okrs"]) / len(data["okrs"]), 1)
            data["avg_confidence"] = round(sum(obj.confidence_level or 0 for obj in data["okrs"]) / len(data["okrs"]), 1)
    
    for person, data in individual_data.items():
        if data["okrs"]:
            data["avg_progress"] = round(sum(obj.progress or 0 for obj in data["okrs"]) / len(data["okrs"]), 1)
            data["avg_confidence"] = round(sum(obj.confidence_level or 0 for obj in data["okrs"]) / len(data["okrs"]), 1)
    
    return {
        "team_performance": team_data,
        "individual_performance": individual_data
    }

# Helper functions
def get_measurables_summary(okr_name):
    """Get measurable summary for an OKR"""
    try:
        doc = frappe.get_doc("OKR", okr_name)
        return doc.get_measurable_summary()
    except:
        return {
            "total": 0,
            "completed": 0,
            "in_progress": 0,
            "not_started": 0,
            "at_risk": 0,
            "on_track": 0,
            "ahead_of_schedule": 0,
            "average_progress": 0,
            "average_confidence": 0
        }

def calculate_health_score(okr):
    """Calculate health score for an OKR"""
    try:
        doc = frappe.get_doc("OKR", okr.name)
        summary = doc.get_measurable_summary()
        health_score = summary.get('overall_health', 0)
        
        # If health score is 0 and we have OKR data, calculate a simple health score
        if health_score == 0 and okr.progress is not None:
            progress_score = okr.progress or 0
            confidence_score = okr.confidence_level or 50
            days_remaining = calculate_days_remaining(okr)
            
            # Simple health calculation based on progress, confidence, and timeline
            if days_remaining is not None:
                if days_remaining < 0:  # Overdue
                    timeline_penalty = min(30, abs(days_remaining) * 2)
                elif days_remaining <= 7:  # Due soon
                    timeline_penalty = 10
                else:
                    timeline_penalty = 0
            else:
                timeline_penalty = 0
            
            health_score = max(0, (progress_score + confidence_score) / 2 - timeline_penalty)
        
        return round(health_score, 1)
    except Exception as e:
        frappe.log_error(f"Error calculating health score for {okr.name}: {str(e)}")
        return 0

def calculate_days_remaining(okr):
    """Calculate days remaining for an OKR"""
    if not okr.target_date:
        return None
    
    today = getdate()
    target = getdate(okr.target_date)
    return (target - today).days

def get_status_category(okr):
    """Get status category for an OKR"""
    if okr.progress == 100:
        return 'completed'
    
    days_remaining = calculate_days_remaining(okr)
    if days_remaining is None:
        return 'no_deadline'
    
    progress_ratio = okr.progress / 100
    
    if days_remaining < 0:
        return 'overdue'
    elif days_remaining <= 7:
        if progress_ratio < 0.8:
            return 'at_risk'
        elif progress_ratio >= 1.0:
            return 'ahead_schedule'
        else:
            return 'on_track'
    else:
        if progress_ratio < 0.6:
            return 'at_risk'
        elif progress_ratio >= 1.0:
            return 'ahead_schedule'
        else:
            return 'on_track'

def is_at_risk(okr):
    """Check if OKR is at risk"""
    return get_status_category(okr) == 'at_risk'

def get_child_objectives(parent_name):
    """Get child OKRs for a parent"""
    children = frappe.get_all(
        "OKR",
        filters={"parent_okr": parent_name},
        fields=["name", "title", "progress", "okr_type", "responsible_person"],
        order_by="creation desc"
    )
    
    for child in children:
        child['measurables_summary'] = get_measurables_summary(child.name)
        child['status_category'] = get_status_category(child)
    
    return children

def count_risk_factors(okr):
    """Count risk factors for an OKR"""
    risk_count = 0
    
    if calculate_days_remaining(okr) and calculate_days_remaining(okr) < 0:
        risk_count += 1
    
    if okr.confidence_level and okr.confidence_level < 50:
        risk_count += 1
    
    if okr.progress and okr.progress < 30:
        risk_count += 1
    
    return risk_count

def get_empty_stats():
    """Return empty statistics structure"""
    return {
        "total": 0,
        "completed": 0,
        "in_progress": 0,
        "not_started": 0,
        "at_risk": 0,
        "on_track": 0,
        "ahead_schedule": 0,
        "overall_progress": 0,
        "avg_confidence": 0,
        "avg_okr_score": 0,
        "avg_health_score": 0,
        "completion_rate": 0,
        "risk_rate": 0,
        "type_distribution": {"company": 0, "team": 0, "individual": 0},
        "timeline": {"overdue": 0, "due_soon": 0, "on_time": 0}
    }

@frappe.whitelist()
def export_dashboard_data(filters=None, format="excel"):
    """Export dashboard data"""
    try:
        if filters:
            filters = json.loads(filters)
        else:
            filters = {}
        
        okrs = get_filtered_okrs(filters)
        
        if format == "excel":
            return export_to_excel(okrs)
        elif format == "csv":
            return export_to_csv(okrs)
        elif format == "pdf":
            return export_to_pdf(okrs)
        else:
            return {"error": "Unsupported format"}
    except Exception as e:
        frappe.log_error(f"Error exporting dashboard data: {str(e)}")
        return {"error": str(e)}

def export_to_excel(okrs):
    """Export data to Excel format"""
    # Implementation for Excel export
    return {"message": "Excel export functionality to be implemented"}

def export_to_csv(okrs):
    """Export data to CSV format"""
    # Implementation for CSV export
    return {"message": "CSV export functionality to be implemented"}

def export_to_pdf(okrs):
    """Export data to PDF format"""
    # Implementation for PDF export
    return {"message": "PDF export functionality to be implemented"} 

@frappe.whitelist()
def get_dashboard_template():
    """Get the OKR dashboard template in the proper Frappe way"""
    try:
        import os
        # Get the path to the template file relative to this file
        current_dir = os.path.dirname(os.path.abspath(__file__))
        template_path = os.path.join(current_dir, "template", "okr_template.html")
        
        # Read the template file directly
        with open(template_path, 'r', encoding='utf-8') as f:
            template_content = f.read()
        
        return template_content
    except Exception as e:
        frappe.log_error(f"Error loading OKR dashboard template: {e}")
        return None 