# Copyright (c) 2026, phamos.eu and contributors
# For license information, please see license.txt


from __future__ import annotations

import time
from typing import Any, Iterator

import frappe
import requests
from frappe.utils.password import get_decrypted_password


class BookstackAPIError(Exception):
	def __init__(self, status_code: int, message: str, payload: Any = None):
		super().__init__(f"[{status_code}] {message}")
		self.status_code = status_code
		self.payload = payload


class BookstackClient:

	DEFAULT_TIMEOUT = 30
	DEFAULT_PAGE_SIZE = 100

	def __init__(self, instance: str):
		self.instance = instance
		self._cfg = frappe.get_cached_doc("Bookstack Configuration", instance)
		if not self._cfg.enabled:
			frappe.throw(f"Bookstack Configuration '{instance}' is disabled.")

		self.base_url = (self._cfg.instance_url or "").rstrip("/")
		if not self.base_url:
			frappe.throw(f"Bookstack Configuration '{instance}' is missing instance_url.")

		token_id = self._cfg.token_id
		token_secret = get_decrypted_password(
			"Bookstack Configuration", instance, "token_secret", raise_exception=False
		)
		if not (token_id and token_secret):
			frappe.throw(f"Bookstack Configuration '{instance}' is missing API credentials.")

		self._session = requests.Session()
		self._session.headers.update({
			"Authorization": f"Token {token_id}:{token_secret}",
			"Accept": "application/json",
		})


	def _url(self, path: str) -> str:
		path = path.lstrip("/")
		if not path.startswith("api/"):
			path = f"api/{path}"
		return f"{self.base_url}/{path}"

	def request(self, method: str, path: str, **kwargs) -> Any:
		kwargs.setdefault("timeout", self.DEFAULT_TIMEOUT)
		resp = self._session.request(method, self._url(path), **kwargs)
		if resp.status_code == 204:
			return None
		if not resp.ok:
			try:
				payload = resp.json()
				msg = payload.get("error", {}).get("message") or payload.get("message") or resp.text
			except ValueError:
				payload = resp.text
				msg = resp.text
			raise BookstackAPIError(resp.status_code, msg, payload)
		if not resp.content:
			return None
		try:
			return resp.json()
		except ValueError:
			return resp.content

	def get(self, path: str, params: dict | None = None) -> Any:
		return self.request("GET", path, params=params)

	def post(self, path: str, json: dict | None = None, **kwargs) -> Any:
		return self.request("POST", path, json=json, **kwargs)

	def put(self, path: str, json: dict | None = None, **kwargs) -> Any:
		return self.request("PUT", path, json=json, **kwargs)

	def delete(self, path: str) -> Any:
		return self.request("DELETE", path)


	def paginate(self, path: str, params: dict | None = None, page_size: int | None = None) -> Iterator[dict]:

		params = dict(params or {})
		params.setdefault("count", page_size or self.DEFAULT_PAGE_SIZE)
		offset = 0
		while True:
			params["offset"] = offset
			body = self.get(path, params=params)
			data = (body or {}).get("data") or []
			if not data:
				return
			for item in data:
				yield item
			if len(data) < params["count"]:
				return
			offset += len(data)
			time.sleep(0.05)
