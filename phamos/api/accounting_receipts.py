# Copyright (c) 2026, phamos.eu and contributors
# For license information, please see license.txt

"""Accounting Cockpit receipt endpoints that are new in the receipt inbox work.

The older receipt endpoints still live in phamos.api.accounting_spa and move here step by step.
"""

import frappe
from frappe import _
from frappe.utils import cint, cstr, flt, get_datetime, getdate

from phamos.accounting.intake import IntakeError, create_receipts_from_file
from phamos.accounting.pdf_stamp import note_to_html, note_to_lines


@frappe.whitelist(methods=["POST"])
def create_receipts_from_upload():
	"""Called through /api/method/upload_file?method=... with one file (PDF or .eml).

	Returns {"results": [{"receipt", "title"} | {"duplicate_of", "title"}]}. A file whose
	content is already on a receipt is skipped unless allow_duplicate is set.
	"""
	frappe.has_permission("Accounting Receipt", "create", throw=True)
	content = frappe.local.uploaded_file
	filename = frappe.local.uploaded_filename
	if not content:
		frappe.throw(_("No file received."))
	try:
		results = create_receipts_from_file(
			filename, content, allow_duplicate=cint(frappe.form_dict.allow_duplicate)
		)
	except IntakeError as e:
		frappe.throw(str(e))
	return {"filename": filename, "results": results}


@frappe.whitelist(methods=["POST"])
def update_receipt_note(name, note=None):
	"""Save the note for the accounting office (printed on the PDF sent to DATEV)."""
	doc = frappe.get_doc("Accounting Receipt", name)
	doc.check_permission("write")
	doc.note = note_to_html(note)
	doc.save()
	return {"name": doc.name, "note_text": "\n".join(note_to_lines(doc.note))}


def _latest_extraction(name):
	"""(run name, extraction analysis) of the latest completed AI run with an extraction."""
	runs = frappe.get_all(
		"AI Agent Run",
		filters={"reference_doctype": "Accounting Receipt", "reference_name": name, "status": "Completed"},
		fields=["name", "analysis"],
		order_by="creation desc",
		limit=5,
	)
	for run in runs:
		analysis = frappe.parse_json(run.analysis or "{}") or {}
		if analysis.get("extraction"):
			return run.name, analysis["extraction"]
	return None, None


def _same(current, extracted, fieldtype):
	if fieldtype in ("Currency", "Float", "Percent"):
		return abs(flt(current) - flt(extracted)) < 0.005
	return cstr(current).strip() == cstr(extracted).strip()


@frappe.whitelist()
def get_extraction_diff(name):
	"""What the AI read vs. what the receipt holds now, for accepting values one by one.

	Rows: {fieldname, label, fieldtype, current, extracted, state}; state is "new" (field is
	empty), "different" (field has another value) or "missing_link" (the AI found a supplier
	that does not exist yet). Equal values are left out.
	"""
	doc = frappe.get_doc("Accounting Receipt", name)
	doc.check_permission("read")
	run, extraction = _latest_extraction(name)
	if not run:
		return {"run": None, "rows": [], "items": None}

	meta = frappe.get_meta("Accounting Receipt")
	rows = []
	values = extraction.get("values") or {}
	for fieldname, extracted in values.items():
		df = meta.get_field(fieldname)
		if not df or extracted in (None, ""):
			continue
		current = doc.get(fieldname)
		if current not in (None, "", 0) and _same(current, extracted, df.fieldtype):
			continue
		rows.append(
			{
				"fieldname": fieldname,
				"label": _(df.label),
				"fieldtype": df.fieldtype,
				"current": current,
				"extracted": extracted,
				"state": "new" if current in (None, "", 0) else "different",
			}
		)
	if extraction.get("supplier_name") and not values.get("supplier") and not doc.supplier:
		rows.append(
			{
				"fieldname": "supplier",
				"label": _("Supplier"),
				"fieldtype": "Link",
				"current": None,
				"extracted": extraction["supplier_name"],
				"state": "missing_link",
			}
		)
	items = extraction.get("items") or []
	items_differ = bool(items) and [r.get("item_name") for r in items] != [r.item_name for r in doc.items]
	return {
		"run": run,
		"rows": rows,
		"items": {"extracted": items, "current_count": len(doc.items)} if items_differ else None,
	}


@frappe.whitelist(methods=["POST"])
def apply_extraction(name, fields=None, include_items=0):
	"""Take over the AI's values for the chosen fields (and item lines). Saved as the
	current user, so the document history shows it as a human decision."""
	doc = frappe.get_doc("Accounting Receipt", name)
	doc.check_permission("write")
	run, extraction = _latest_extraction(name)
	if not run:
		frappe.throw(_("There is no AI reading for this receipt yet."))
	fields = frappe.parse_json(fields) if isinstance(fields, str) else (fields or [])
	values = extraction.get("values") or {}
	updated = []
	for fieldname in fields:
		if fieldname in values and doc.meta.get_field(fieldname):
			doc.set(fieldname, values[fieldname])
			updated.append(fieldname)
	if cint(include_items) and extraction.get("items"):
		doc.set("items", [])
		for row in extraction["items"]:
			doc.append("items", row)
		updated.append("items")
	if updated:
		doc.save()
	return {"updated": updated}


# --- Editing in the cockpit -------------------------------------------------------------

RECEIPT_EDITABLE_FIELDS = (
	"title",
	"posting_date",
	"due_date",
	"receipt_type",
	"supplier",
	"supplier_reference",
	"sum",
	"currency",
	"net_total",
	"total_taxes",
	"supplier_tax_id",
	"supplier_iban",
	"payment_reference",
	"project",
	"cost_center",
	"payment_date",
	"items",
)
ITEM_EDITABLE_FIELDS = ("item_name", "qty", "rate", "amount", "tax_rate", "expense_account", "cost_center", "project")


@frappe.whitelist(methods=["POST"])
def get_receipt_form_options():
	"""Choices for the cockpit editor's select fields."""
	frappe.has_permission("Accounting Receipt", "read", throw=True)
	meta = frappe.get_meta("Accounting Receipt")

	def options(fieldname):
		return [o for o in (meta.get_field(fieldname).options or "").split("\n") if o]

	company = frappe.defaults.get_user_default("company") or frappe.db.get_single_value("Global Defaults", "default_company")
	return {
		"receipt_types": options("receipt_type"),
		"company": company,
		"company_currency": company and frappe.get_cached_value("Company", company, "default_currency"),
		"can_create_supplier": 1 if frappe.has_permission("Supplier", "create") else 0,
	}


@frappe.whitelist(methods=["POST"])
def update_receipt(name, modified=None, **fields):
	"""Save edits from the cockpit. Unknown fields are refused; a stale `modified`
	raises Frappe's TimestampMismatchError so the editor can show the conflict."""
	from phamos.api.accounting_spa import get_receipt

	fields.pop("cmd", None)
	unknown = set(fields) - set(RECEIPT_EDITABLE_FIELDS)
	if unknown:
		frappe.throw(_("These fields cannot be changed here: {0}").format(", ".join(sorted(unknown))))

	doc = frappe.get_doc("Accounting Receipt", name)
	doc.check_permission("write")
	if doc.status == "Cancelled":
		frappe.throw(_("A cancelled receipt cannot be edited. Reopen it first."))

	if "title" in fields and not cstr(fields["title"]).strip():
		frappe.throw(_("Title is required"))
	for fieldname, value in fields.items():
		if fieldname == "items":
			_set_items(doc, frappe.parse_json(value) if isinstance(value, str) else value)
		else:
			doc.set(fieldname, value if value != "" else None)

	if modified:
		doc.modified = get_datetime(modified)
	doc.save()
	return get_receipt(name)


def _set_items(doc, rows):
	"""Replace the item lines, keeping row names so learned data stays attached."""
	existing = {row.name: row for row in doc.items}
	doc.set("items", [])
	for incoming in rows or []:
		values = {k: incoming.get(k) for k in ITEM_EDITABLE_FIELDS if k in incoming}
		if not cstr(values.get("item_name")).strip():
			continue
		values["qty"] = flt(values.get("qty")) or 1
		values["rate"] = flt(values.get("rate"))
		if not flt(values.get("amount")):
			values["amount"] = values["qty"] * values["rate"]
		row = existing.get(incoming.get("name"))
		if row:
			row.update(values)
			doc.append("items", row)
		else:
			doc.append("items", values)


# --- Suppliers ----------------------------------------------------------------------------

LEGAL_FORMS = (
	"gmbh & co. kg", "gmbh & co kg", "gmbh", "ug (haftungsbeschränkt)", "ug", "ag", "kg", "ohg", "e.k.", "e.v.", "gbr",
	"ltd.", "ltd", "limited", "inc.", "inc", "llc", "s.a.", "sa", "sarl", "s.a.r.l.", "b.v.", "bv", "plc", "co.", "corp.",
)


def _normalize_company_name(name):
	text = cstr(name).lower().replace(",", " ")
	for form in LEGAL_FORMS:
		text = (" " + text + " ").replace(" " + form + " ", " ").strip()
	return " ".join(text.split())


def _extracted_supplier(doc):
	"""What the AI read about the issuer: name, VAT ID, IBAN and address."""
	_run, extraction = _latest_extraction(doc.name)
	extraction = extraction or {}
	address = extraction.get("supplier_address") or {}
	if not isinstance(address, dict):
		address = {"line1": cstr(address)}
	return {
		"supplier_name": extraction.get("supplier_name") or doc.supplier_name or "",
		"tax_id": doc.supplier_tax_id or (extraction.get("values") or {}).get("supplier_tax_id") or "",
		"iban": doc.supplier_iban or (extraction.get("values") or {}).get("supplier_iban") or "",
		"address_line1": address.get("line1") or "",
		"address_line2": address.get("line2") or "",
		"pincode": address.get("pincode") or "",
		"city": address.get("city") or "",
		"country": _country(address.get("country")),
	}


def _country(value):
	value = cstr(value).strip()
	if value and frappe.db.exists("Country", value):
		return value
	aliases = {"deutschland": "Germany", "de": "Germany", "ireland": "Ireland", "irland": "Ireland",
		"österreich": "Austria", "schweiz": "Switzerland", "usa": "United States", "united states of america": "United States"}
	return aliases.get(value.lower()) or frappe.db.get_single_value("System Settings", "country") or ""


@frappe.whitelist(methods=["POST"])
def get_supplier_suggestions(name):
	"""Prefill for "Create supplier" and existing suppliers that look like the issuer.

	Candidates come from the VAT ID, the IBAN (supplier Bank Accounts) and a fuzzy
	comparison of names without legal forms ("Apple Distribution Limited" ≈
	"Apple Distribution International Ltd."). Nothing is set automatically.
	"""
	from rapidfuzz import fuzz

	doc = frappe.get_doc("Accounting Receipt", name)
	doc.check_permission("read")
	extracted = _extracted_supplier(doc)
	candidates = {}

	def add(supplier, score, reason):
		entry = candidates.setdefault(supplier, {"supplier": supplier, "score": 0, "reasons": []})
		entry["score"] = max(entry["score"], score)
		if reason not in entry["reasons"]:
			entry["reasons"].append(reason)

	tax_id = cstr(extracted["tax_id"]).replace(" ", "")
	if tax_id:
		for supplier in frappe.get_all("Supplier", filters={"tax_id": tax_id, "disabled": 0}, pluck="name"):
			add(supplier, 100, _("same VAT ID"))
	iban = cstr(extracted["iban"]).replace(" ", "").upper()
	if iban:
		for row in frappe.get_all("Bank Account", filters={"iban": iban, "party_type": "Supplier"}, fields=["party"]):
			add(row.party, 100, _("same IBAN"))
	wanted = _normalize_company_name(extracted["supplier_name"])
	if wanted:
		for row in frappe.get_all("Supplier", filters={"disabled": 0}, fields=["name", "supplier_name"]):
			score = fuzz.token_set_ratio(wanted, _normalize_company_name(row.supplier_name))
			if score >= 70:
				add(row.name, round(score), _("similar name"))

	ranked = sorted(candidates.values(), key=lambda c: -c["score"])[:5]
	for entry in ranked:
		entry["supplier_name"] = frappe.db.get_value("Supplier", entry["supplier"], "supplier_name")
	return {"extracted": extracted, "candidates": ranked}


@frappe.whitelist(methods=["POST"])
def create_supplier_from_receipt(name, supplier_name, supplier_group=None, tax_category=None, tax_id=None,
		country=None, address_line1=None, address_line2=None, pincode=None, city=None, iban=None, bank_name=None):
	"""Create the issuer as Supplier (+ billing Address, + Bank Account when an IBAN is given)
	and set it on the receipt. Returns the receipt as the cockpit shows it."""
	from phamos.api.accounting_spa import get_receipt
	from phamos.phamos.doctype.accounting_receipt.data_extract import resolve_link_for_extract

	doc = frappe.get_doc("Accounting Receipt", name)
	doc.check_permission("write")
	frappe.has_permission("Supplier", "create", throw=True)

	supplier_name = cstr(supplier_name).strip()
	if not supplier_name:
		frappe.throw(_("Supplier name is required"))
	existing = resolve_link_for_extract("Supplier", supplier_name)
	if existing:
		frappe.throw(_("Supplier {0} already exists. Pick it instead.").format(existing))
	if not tax_category and frappe.db.count("Tax Category"):
		frappe.throw(_("Tax Category is required to create a Supplier."))

	supplier = frappe.get_doc(
		{
			"doctype": "Supplier",
			"supplier_name": supplier_name,
			"supplier_type": "Company",
			"supplier_group": supplier_group
			or frappe.db.get_single_value("Buying Settings", "supplier_group")
			or frappe.db.get_value("Supplier Group", {"is_group": 0}, "name"),
			"tax_category": tax_category,
			"tax_id": cstr(tax_id).replace(" ", "") or None,
			"country": country or None,
			"default_currency": doc.currency,
		}
	).insert()

	if address_line1 or city:
		address = frappe.get_doc(
			{
				"doctype": "Address",
				"address_title": supplier_name,
				"address_type": "Billing",
				"address_line1": address_line1 or "-",
				"address_line2": address_line2,
				"pincode": pincode,
				"city": city or "-",
				"country": country or frappe.db.get_single_value("System Settings", "country"),
				"is_primary_address": 1,
				"links": [{"link_doctype": "Supplier", "link_name": supplier.name}],
			}
		).insert()
		supplier.db_set("supplier_primary_address", address.name, update_modified=False)

	iban = cstr(iban).replace(" ", "").upper()
	if iban:
		frappe.get_doc(
			{
				"doctype": "Bank Account",
				"account_name": supplier_name,
				"bank": _bank_for(iban, bank_name),
				"party_type": "Supplier",
				"party": supplier.name,
				"iban": iban,
				"is_company_account": 0,
			}
		).insert()

	doc.reload()
	doc.supplier = supplier.name
	if not doc.supplier_tax_id and tax_id:
		doc.supplier_tax_id = cstr(tax_id).replace(" ", "")
	doc.save()
	return get_receipt(name)


def _bank_for(iban, bank_name=None):
	"""Bank record for a supplier account: the given name, else one named after the German
	bank code (BLZ) in the IBAN, else after the IBAN country."""
	name = cstr(bank_name).strip() or (f"BLZ {iban[4:12]}" if iban.startswith("DE") and len(iban) >= 12 else f"Bank {iban[:2]}")
	if not frappe.db.exists("Bank", name):
		frappe.get_doc({"doctype": "Bank", "bank_name": name}).insert(ignore_permissions=True)
	return name


# --- Work queue and list ------------------------------------------------------------------

QUEUE_SECTIONS = (
	("decide", "Needs your decision"),
	("ready", "Ready to send"),
	("waiting", "Waiting for payment"),
	("problems", "Problems"),
)
QUEUE_FIELDS = [
	"name", "title", "status", "receipt_type", "posting_date", "due_date", "sum", "currency",
	"sum_in_company_currency", "supplier", "supplier_name", "supplier_reference", "attachment",
	"is_paid", "sent_to_datev", "ai_run", "ai_confidence", "ai_summary", "creation", "modified",
]
READY_MIN_CONFIDENCE = 90
OPEN_STATUSES = ("Inbox", "Needs Decision")


def next_action(row, run):
	"""(section, reasons) for one receipt; section None means nothing left to do.

	run: {"status", "flags"} of the receipt's latest AI run, or None.
	"""
	if row.status == "Cancelled":
		return None, []
	reasons = []
	if not cstr(row.attachment).lower().endswith(".pdf"):
		return "problems", [_("No PDF attached")]
	if run and run.get("status") == "Failed":
		return "problems", [_("The AI could not read the PDF")]
	if row.is_paid and row.sent_to_datev:
		return None, []

	if row.status in OPEN_STATUSES:
		flags = [f for f in (run or {}).get("flags") or [] if f.get("severity") in ("warn", "block")]
		reasons = [f.get("message") for f in flags if f.get("message")]
		if not run:
			reasons.append(_("Not read by the AI yet"))
		if not row.supplier:
			reasons.append(_("No supplier"))
		if not flt(row.sum):
			reasons.append(_("No amount"))
		if not row.posting_date:
			reasons.append(_("No date"))
		if run and flt(row.ai_confidence) and flt(row.ai_confidence) < READY_MIN_CONFIDENCE:
			reasons.append(_("The AI is unsure ({0} %)").format(round(flt(row.ai_confidence))))
		if row.receipt_type in ("Contract", "Reminder", "Statement"):
			reasons.append(_("{0}: not a voucher").format(_(row.receipt_type)))
		reasons = list(dict.fromkeys(reasons))
		if reasons:
			return "decide", reasons
		return ("waiting", []) if row.sent_to_datev else ("ready", [])

	if not row.sent_to_datev:
		return "ready", []
	if row.status in ("Approved to Pay", "Sent to DATEV") and not row.is_paid:
		return "waiting", []
	return None, []


def _latest_runs(run_names):
	if not run_names:
		return {}
	rows = frappe.get_all(
		"AI Agent Run", filters={"name": ("in", list(run_names))}, fields=["name", "status", "run_flags"]
	)
	return {r.name: {"status": r.status, "flags": frappe.parse_json(r.run_flags or "[]") or []} for r in rows}


def _queue_row(row, section, reasons, today):
	overdue_days = None
	if row.due_date and not row.is_paid and row.status not in ("Do Not Pay", "Cancelled"):
		overdue_days = (getdate(today) - getdate(row.due_date)).days
	return {
		"name": row.name,
		"title": row.title,
		"status": row.status,
		"receipt_type": row.receipt_type,
		"posting_date": row.posting_date,
		"due_date": row.due_date,
		"overdue_days": overdue_days if overdue_days and overdue_days > 0 else 0,
		"sum": row.sum,
		"currency": row.currency,
		"supplier": row.supplier,
		"supplier_name": row.supplier_name,
		"supplier_reference": row.supplier_reference,
		"is_paid": 1 if row.is_paid else 0,
		"sent_to_datev": 1 if row.sent_to_datev else 0,
		"ai_confidence": row.ai_confidence,
		"ai_summary": row.ai_summary,
		"reason": reasons[0] if reasons else "",
		"reasons": reasons,
		"section": section,
	}


def _sort_key(item):
	"""Overdue first, then due soon, then larger amounts, then older receipts."""
	due = getdate(item["due_date"]) if item["due_date"] else None
	return (
		0 if item["overdue_days"] else 1,
		due or getdate("2999-12-31"),
		-flt(item["sum"]),
		str(item["posting_date"] or ""),
	)


@frappe.whitelist(methods=["POST"])
def get_receipt_queue():
	"""Receipts that need something, grouped by what happens next."""
	frappe.has_permission("Accounting Receipt", "read", throw=True)
	rows = frappe.get_list(
		"Accounting Receipt",
		fields=QUEUE_FIELDS,
		filters={"status": ("!=", "Cancelled")},
		order_by="creation asc",
		limit_page_length=2000,
	)
	runs = _latest_runs({r.ai_run for r in rows if r.ai_run})
	today = frappe.utils.today()
	grouped = {key: [] for key, _label in QUEUE_SECTIONS}
	for row in rows:
		section, reasons = next_action(row, runs.get(row.ai_run))
		if section:
			grouped[section].append(_queue_row(row, section, reasons, today))
	sections = []
	for key, label in QUEUE_SECTIONS:
		items = sorted(grouped[key], key=_sort_key)
		sections.append({"key": key, "title": _(label), "count": len(items), "items": items})
	waiting = grouped["waiting"]
	return {
		"sections": sections,
		"counts": {key: len(grouped[key]) for key, _label in QUEUE_SECTIONS},
		"overdue": sum(1 for item in waiting if item["overdue_days"]),
	}


@frappe.whitelist(methods=["POST"])
def list_receipts(search=None, from_date=None, to_date=None, status=None, supplier=None, receipt_type=None,
		sort="posting_date", order="desc", limit=500):
	"""All receipts with filters, for the searchable list. Returns {items, total, truncated}."""
	frappe.has_permission("Accounting Receipt", "read", throw=True)
	filters = []
	if from_date:
		filters.append(["posting_date", ">=", from_date])
	if to_date:
		filters.append(["posting_date", "<=", to_date])
	statuses = frappe.parse_json(status) if isinstance(status, str) and status.startswith("[") else status
	if statuses:
		filters.append(["status", "in", statuses if isinstance(statuses, list) else [statuses]])
	if supplier:
		filters.append(["supplier", "=", supplier])
	if receipt_type:
		filters.append(["receipt_type", "=", receipt_type])
	or_filters = None
	if cstr(search).strip():
		like = f"%{cstr(search).strip()}%"
		or_filters = [["title", "like", like], ["supplier_name", "like", like], ["supplier_reference", "like", like], ["name", "like", like]]
	sort = sort if sort in ("posting_date", "due_date", "sum_in_company_currency", "modified", "creation") else "posting_date"
	order = "asc" if order == "asc" else "desc"
	limit = min(cint(limit) or 500, 2000)
	rows = frappe.get_list(
		"Accounting Receipt",
		fields=QUEUE_FIELDS,
		filters=filters,
		or_filters=or_filters,
		order_by=f"{sort} {order}, creation desc",
		limit_page_length=limit + 1,
	)
	truncated = len(rows) > limit
	rows = rows[:limit]
	runs = _latest_runs({r.ai_run for r in rows if r.ai_run})
	today = frappe.utils.today()
	items = []
	for row in rows:
		section, reasons = next_action(row, runs.get(row.ai_run))
		items.append(_queue_row(row, section, reasons, today))
	return {"items": items, "truncated": truncated, "total": frappe.db.count("Accounting Receipt", filters=filters) if not or_filters else None}


@frappe.whitelist(methods=["POST"])
def send_receipts_to_datev(names):
	"""Send several receipts to DATEV. Returns {"sent": [...], "failed": [{name, message}]}."""
	from phamos.phamos.doctype.accounting_receipt.accounting_receipt import send_to_datev

	names = frappe.parse_json(names) if isinstance(names, str) else (names or [])
	sent, failed = [], []
	for name in names[:50]:
		try:
			result = send_to_datev(name)
		except frappe.PermissionError:
			result = {"ok": False, "message": _("Not permitted")}
		(sent.append(name) if result.get("ok") else failed.append({"name": name, "message": result.get("message")}))
	return {"sent": sent, "failed": failed}


# --- Purchase Invoices ---------------------------------------------------------------------


@frappe.whitelist(methods=["POST"])
def suggest_accounts(name):
	"""Propose expense accounts for the receipt's lines that have none (library, then Mistral)."""
	from phamos.accounting.classify import suggest_accounts as suggest

	return suggest(name)


@frappe.whitelist(methods=["POST"])
def get_approval_options(name):
	"""What the approve dialog offers: company bank accounts, modes of payment, the due date,
	and whether the supplier has the bank account the Payment Request needs."""
	from phamos.accounting.branching import company_bank_accounts, open_payment_request, supplier_bank_account
	from phamos.phamos.doctype.accounting_receipt.accounting_receipt import submitted_purchase_invoice

	doc = frappe.get_doc("Accounting Receipt", name)
	doc.check_permission("read")
	company = doc.company or frappe.defaults.get_global_default("company")
	pi = submitted_purchase_invoice(doc)
	pi_values = frappe.db.get_value("Purchase Invoice", pi, ["due_date", "outstanding_amount", "grand_total", "currency"], as_dict=True) if pi else {}
	accounts = company_bank_accounts(company)
	supplier_account = supplier_bank_account(doc.supplier)
	return {
		"purchase_invoice": pi,
		"outstanding_amount": pi_values.get("outstanding_amount"),
		"currency": pi_values.get("currency") or doc.currency,
		"due_date": str(doc.due_date or pi_values.get("due_date") or "") or None,
		"bank_accounts": accounts,
		"bank_account": doc.bank_account or (accounts[0].name if accounts else None),
		"modes_of_payment": frappe.get_all("Mode of Payment", filters={"enabled": 1, "type": ("in", ("Bank", "General"))}, pluck="name", order_by="name"),
		"mode_of_payment": doc.mode_of_payment or ("Wire Transfer" if frappe.db.exists("Mode of Payment", "Wire Transfer") else None),
		"supplier_bank_account": supplier_account,
		"supplier_iban": frappe.db.get_value("Bank Account", supplier_account, "iban") if supplier_account else None,
		"receipt_iban": doc.supplier_iban,
		"payment_request": open_payment_request(doc),
		"can_create_payment_request": 1 if frappe.has_permission("Payment Request", "create") else 0,
	}


@frappe.whitelist(methods=["POST"])
def approve_receipt(name, bank_account=None, mode_of_payment=None, due_date=None, create_payment_request=1):
	"""Approve to pay: store how and when it is paid, set the status and create the
	Payment Request for the submitted Purchase Invoice. All or nothing."""
	from phamos.accounting.branching import make_payment_request, open_payment_request
	from phamos.api.accounting_spa import get_receipt

	doc = frappe.get_doc("Accounting Receipt", name)
	doc.check_permission("write")
	if bank_account:
		company = doc.company or frappe.defaults.get_global_default("company")
		account = frappe.db.get_value("Bank Account", bank_account, ["is_company_account", "company", "account"], as_dict=True)
		if not account or not account.is_company_account or account.company != company:
			frappe.throw(_("{0} is not a bank account of {1}.").format(bank_account, company))
		doc.bank_account = bank_account
		doc.payment_account = account.account
	if mode_of_payment:
		doc.mode_of_payment = mode_of_payment
	if due_date:
		doc.due_date = due_date
	doc.status = "Approved to Pay"
	doc.save()
	payment_request = open_payment_request(doc)
	if cint(create_payment_request) and not payment_request:
		payment_request = make_payment_request(doc, mode_of_payment=doc.mode_of_payment, bank_account=doc.bank_account).name
	return {"payment_request": payment_request, "receipt": get_receipt(name)}


@frappe.whitelist(methods=["POST"])
def submit_purchase_invoice(name):
	"""Submit the receipt's draft Purchase Invoice (needed before approving to pay)."""
	from phamos.api.accounting_spa import get_receipt

	receipt = frappe.get_doc("Accounting Receipt", name)
	receipt.check_permission("write")
	if not receipt.purchase_invoice:
		frappe.throw(_("This receipt has no Purchase Invoice yet."))
	pi = frappe.get_doc("Purchase Invoice", receipt.purchase_invoice)
	if pi.docstatus != 0:
		frappe.throw(_("Purchase Invoice {0} is not a draft.").format(pi.name))
	pi.check_permission("submit")
	pi.submit()
	return {"purchase_invoice": pi.name, "receipt": get_receipt(name)}


@frappe.whitelist(methods=["POST"])
def make_purchase_invoice(name, submit=0):
	"""Create the Purchase Invoice from the receipt's lines (draft unless submit=1)."""
	from phamos.accounting.branching import make_purchase_invoice as build
	from phamos.api.accounting_spa import get_receipt

	doc = frappe.get_doc("Accounting Receipt", name)
	doc.check_permission("write")
	frappe.has_permission("Purchase Invoice", "create", throw=True)
	pi = build(doc, submit=cint(submit))
	return {
		"purchase_invoice": pi.name,
		"docstatus": pi.docstatus,
		"grand_total": pi.grand_total,
		"warnings": pi.flags.receipt_warnings or [],
		"desk_url": f"/app/purchase-invoice/{pi.name}",
		"receipt": get_receipt(name),
	}
