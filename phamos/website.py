import frappe

CUSTOMER_PORTAL_HOME = "timesheet"


def get_website_user_home_page(user):
	if _is_customer_portal_user(user):
		return CUSTOMER_PORTAL_HOME


def on_login(login_manager):
	if _is_customer_portal_user(login_manager.user):
		frappe.local.flags.home_page = CUSTOMER_PORTAL_HOME


def _is_customer_portal_user(user):
	if not user or user == "Guest":
		return False

	if frappe.db.get_value("User", user, "user_type") != "Website User":
		return False

	from phamos.api import get_customer_for_user

	return bool(get_customer_for_user(user))
