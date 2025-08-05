import frappe
from frappe.utils import now_datetime
from .gitlab_utils import schedule_gitlab_sync

def setup_gitlab_sync_scheduler():
    """Setup automatic GitLab sync scheduler"""
    try:
        # Create scheduler event for incremental sync
        if not frappe.db.exists("Scheduled Job Type", "gitlab_incremental_sync"):
            frappe.get_doc({
                "doctype": "Scheduled Job Type",
                "method": "phamos.gitlab_integration.scheduler.run_incremental_sync",
                "frequency": "All",
                "cron_format": "0 */6 * * *",  # Every 6 hours
                "enabled": 1
            }).insert()
        
        # Create scheduler event for full sync
        if not frappe.db.exists("Scheduled Job Type", "gitlab_full_sync"):
            frappe.get_doc({
                "doctype": "Scheduled Job Type",
                "method": "phamos.gitlab_integration.scheduler.run_full_sync",
                "frequency": "All",
                "cron_format": "0 2 * * 0",  # Every Sunday at 2 AM
                "enabled": 1
            }).insert()
            
        frappe.log_error("GitLab sync schedulers configured successfully")
        
    except Exception as e:
        frappe.log_error(f"Error setting up GitLab sync schedulers: {str(e)}")

def run_incremental_sync():
    """Run incremental GitLab sync (called by scheduler)"""
    try:
        # Check if GitLab is configured
        settings = frappe.get_single("GitLab Settings")
        if not settings.access_token or not settings.gitlab_url:
            frappe.log_error("GitLab not configured, skipping incremental sync")
            return
        
        # Schedule incremental sync
        schedule_gitlab_sync("incremental")
        
    except Exception as e:
        frappe.log_error(f"Error in incremental sync scheduler: {str(e)}")

def run_full_sync():
    """Run full GitLab sync (called by scheduler)"""
    try:
        # Check if GitLab is configured
        settings = frappe.get_single("GitLab Settings")
        if not settings.access_token or not settings.gitlab_url:
            frappe.log_error("GitLab not configured, skipping full sync")
            return
        
        # Schedule full sync
        schedule_gitlab_sync("full")
        
    except Exception as e:
        frappe.log_error(f"Error in full sync scheduler: {str(e)}")
