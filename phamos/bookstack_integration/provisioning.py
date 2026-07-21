# Copyright (c) 2026, phamos.eu and contributors
# For license information, please see license.txt


from __future__ import annotations

import csv
import io

import frappe

from phamos.bookstack_integration.api_client import BookstackAPIError, BookstackClient


def _role_id(client: BookstackClient, instance: str, display_name: str) -> int | None:
	# Prefer the locally mirrored role
	role_id = frappe.db.get_value(
		"Bookstack Role",
		{"instance": instance, "display_name": display_name},
		"bookstack_id",
	)
	if role_id:
		return int(role_id)

	# Fallback: query API directly
	for r in client.paginate("roles"):
		if r.get("display_name") == display_name:
			return r["id"]
	return None


def _find_remote_user_by_email(client: BookstackClient, email: str) -> dict | None:
	body = client.get("users", params={"filter[email]": email, "count": 1})
	data = (body or {}).get("data") or []
	return data[0] if data else None


def _resolve_employee_defaults(email: str) -> dict:
	"""Look up an ERPNext Employee by email and return language + avatar URL."""
	user = frappe.db.get_value("User", {"email": email}, ["name", "language", "user_image"], as_dict=True)
	if not user:
		return {}
	defaults = {}
	if user.get("language"):
		defaults["language"] = user["language"]
	return defaults


@frappe.whitelist()
def create_user(instance: str, name: str, email: str, role: str | None = None,
                language: str | None = None, send_invite: int | bool = 1) -> dict:

	client = BookstackClient(instance)
	cfg = frappe.get_cached_doc("Bookstack Configuration", instance)

	existing = _find_remote_user_by_email(client, email)
	if existing:
		return {"status": "exists", "user": existing}

	role_display = role or cfg.default_role_name
	role_id = _role_id(client, instance, role_display) if role_display else None


	employee_defaults = _resolve_employee_defaults(email)
	payload = {
		"name": name,
		"email": email,
		"language": language or employee_defaults.get("language") or cfg.language or "en",
		"send_invite": bool(int(send_invite)),
	}
	if role_id:
		payload["roles"] = [role_id]

	user = client.post("users", json=payload)
	return {"status": "created", "user": user}


@frappe.whitelist()
def bulk_create_users(instance: str, users_csv: str, send_invite: int | bool = 1) -> dict:

	results = {"created": [], "existing": [], "errors": []}
	reader = csv.reader(io.StringIO(users_csv))
	for row in reader:
		row = [c.strip() for c in row if c is not None]
		if not row or row[0].startswith("#"):
			continue
		if len(row) < 2:
			results["errors"].append({"row": row, "error": "expected at least name,email"})
			continue
		name = row[0]
		email = row[1]
		role = row[2] if len(row) > 2 and row[2] else None
		language = row[3] if len(row) > 3 and row[3] else None
		try:
			outcome = create_user(instance, name, email, role=role, language=language, send_invite=send_invite)
			bucket = "existing" if outcome["status"] == "exists" else "created"
			results[bucket].append({"email": email, "id": (outcome["user"] or {}).get("id")})
		except BookstackAPIError as exc:
			results["errors"].append({"email": email, "error": str(exc), "payload": exc.payload})
		except Exception as exc:  # noqa: BLE001
			results["errors"].append({"email": email, "error": str(exc)})

	return results
