import frappe

CUSTOMER_PORTAL_HOME = "timesheet"


def get_website_user_home_page(user):
	if _is_customer_portal_user(user):
		return CUSTOMER_PORTAL_HOME


def on_login(login_manager):
	if _is_customer_portal_user(login_manager.user):
		frappe.local.flags.home_page = CUSTOMER_PORTAL_HOME


def update_website_context(context):
	post_login = list(context.get("post_login") or [])

	portal_item = {"label": "Customer Portal", "url": "/timesheet"}
	already_present = any((item or {}).get("url") == portal_item["url"] for item in post_login)

	if not already_present:
		post_login.append(portal_item)

	return {"post_login": post_login}


def _is_customer_portal_user(user):
	if not user or user == "Guest":
		return False

	if frappe.db.get_value("User", user, "user_type") != "Website User":
		return False

	from phamos.api import get_customer_for_user

	return bool(get_customer_for_user(user))
