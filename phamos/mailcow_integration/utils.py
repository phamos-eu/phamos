
import frappe
import random
import string
import base64
import requests
import pytz
from frappe.utils.password import get_decrypted_password


def _headers():
	api_key = get_decrypted_password("Mailcow Settings", "Mailcow Settings", "api_key")
	return {"X-API-Key": api_key, "Content-Type": "application/json"}

def generate_password(length: int = 16) -> str:
	alphabet = string.ascii_letters + string.digits + "!@#%^*()-_=+"
	return "".join(random.SystemRandom().choice(alphabet) for _ in range(length))

def _generate_password(length):
	characters = string.ascii_letters + string.digits + string.punctuation
	password = ''.join(random.choice(characters) for i in range(length))
	return password

def _date_ics(d):  # d can be date or string "YYYY-MM-DD"
	if isinstance(d, str):
		d = frappe.utils.getdate(d)
	return d.strftime("%Y%m%d")

def get_mailbox(username_email):
	base = frappe.db.get_single_value("Mailcow Settings", "base_url").rstrip("/")
	url = f"{base}/api/v1/get/mailbox/{username_email}"

	response = requests.request('GET', url, headers=_headers(), data = {})
	return response

def convert_to_base64(auth_str):
	bytes_data = auth_str.encode('utf-8')
	encoded_bytes = base64.b64encode(bytes_data)
	base64_string = encoded_bytes.decode('utf-8')
	return f'Basic {base64_string}'

def get_site_timezone(default: str = "UTC") -> str:
	tz = None
	try:
		tz = frappe.db.get_single_value("System Settings", "time_zone")
	except Exception:
		pass
	if not tz:
		try:
			tz = frappe.get_conf().get("time_zone")
		except Exception:
			tz = None
	if not tz:
		return default
	# validate
	try:
		pytz.timezone(tz)
		return tz
	except Exception:
		return default