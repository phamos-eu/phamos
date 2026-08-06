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
	website_item = {"label": "Switch To Website", "url": "/"}
	already_present = any((item or {}).get("url") == portal_item["url"] for item in post_login)
	website_present = any((item or {}).get("url") == website_item["url"] for item in post_login)
	is_on_customer_portal = _is_on_customer_portal_path(context)

	if is_on_customer_portal:
		post_login = [item for item in post_login if (item or {}).get("url") != portal_item["url"]]
		already_present = False

	if not is_on_customer_portal and not already_present:
		post_login.append(portal_item)

	if is_on_customer_portal and not website_present:
		post_login.append(website_item)

	return {"post_login": post_login}


def _is_on_customer_portal_path(context):
	# Handle route variants such as: timesheet, /timesheet, /en/timesheet, /timesheet/...
	values = []
	ctx = context or {}
	for key in ("path", "route", "canonical_route"):
		if ctx.get(key):
			values.append(ctx.get(key))

	request = getattr(frappe.local, "request", None)
	if request:
		for key in ("path", "full_path"):
			value = getattr(request, key, "")
			if value:
				values.append(value)

	portal_route = CUSTOMER_PORTAL_HOME.strip("/")

	for raw in values:
		value = str(raw).split("?", 1)[0].split("#", 1)[0].strip("/")
		if not value:
			continue

		if value == portal_route or value.startswith(f"{portal_route}/"):
			return True

		parts = [part for part in value.split("/") if part]
		if portal_route in parts:
			idx = parts.index(portal_route)
			if idx == 0 or (idx == 1 and len(parts[0]) <= 5):
				return True

	return False


def _is_customer_portal_user(user):
	if not user or user == "Guest":
		return False

	if frappe.db.get_value("User", user, "user_type") != "Website User":
		return False

	from phamos.api import get_customer_for_user

	return bool(get_customer_for_user(user))
