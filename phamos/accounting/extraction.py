# Copyright (c) 2026, phamos.eu and contributors
# For license information, please see license.txt

"""Read a receipt PDF with Mistral and fill the Accounting Receipt (extraction v2).

Differences to the first version (mistral_pdf.py / data_extract.py):
- an explicit schema instead of "every editable field", so the AI is never asked for
  system fields (DATEV flags, links to invoices, company …) or the note for the office;
- clear rules for the fields that went wrong most: the invoice number (not order or
  customer number) and the supplier (the issuer, never our own company);
- values only fill empty fields unless the run overwrites on purpose;
- item lines, net and tax amounts, the issuer's VAT ID and IBAN;
- the OCR text is kept on the receipt, so later runs skip the OCR call.
"""

import hashlib

import frappe
from frappe import _
from frappe.utils import cstr, flt, fmt_money, getdate
from frappe.utils.file_manager import get_file

from phamos.ai_agents import llm
from phamos.ai_agents.context import FAILED, PASSED, SkillResult
from phamos.phamos.doctype.accounting_receipt.data_extract import _parse_german_number, resolve_link_for_extract

DOCTYPE = "Accounting Receipt"
MAX_DOCUMENT_CHARS = 20000
LOW_CONFIDENCE = 0.7
RECEIPT_TYPES = ("Invoice", "Credit Note", "Receipt", "Tax Notice", "Contract", "Reminder", "Statement", "Other")

# key in the AI answer -> (receipt field, description for the prompt)
HEADER_FIELDS = {
	"receipt_type": (
		"receipt_type",
		f"what the document is, one of: {', '.join(RECEIPT_TYPES)} (Receipt = till/card receipt, e.g. fuel or restaurant)",
	),
	"invoice_number": (
		"supplier_reference",
		"the number of this invoice or receipt as issued by the supplier (labels like Rechnungsnummer, Rechnungs-Nr., "
		"Belegnummer, Bon-Nr., Invoice No., Document No.). NEVER an order number (Bestellnummer, Order ID), customer "
		"number (Kundennummer), delivery note number (Lieferschein), contract number or account number",
	),
	"invoice_date": ("posting_date", "date of the invoice/receipt, YYYY-MM-DD"),
	"due_date": (
		"due_date",
		"YYYY-MM-DD. If only payment terms are given (e.g. 'zahlbar innerhalb von 14 Tagen'), add those days to the "
		"invoice date. Omit if the document says it is already paid",
	),
	"supplier_name": ("supplier", "legal name of the company or person that ISSUED the document"),
	"supplier_tax_id": ("supplier_tax_id", "VAT ID (USt-IdNr.) or tax number of the issuer"),
	"supplier_iban": ("supplier_iban", "IBAN of the issuer's bank account, without spaces"),
	"currency": ("currency", "ISO currency code, e.g. EUR"),
	"total_gross": ("sum", "total amount including tax"),
	"total_net": ("net_total", "total amount without tax"),
	"total_tax": ("total_taxes", "total tax amount"),
	"payment_reference": ("payment_reference", "reference to use on the bank transfer, if stated"),
}
# Read but kept in the run analysis only (used by later phases).
ANALYSIS_ONLY = {
	"payment_status": "paid | unpaid | unknown — 'paid' only if the document says so (bezahlt, paid, Kartenzahlung, Lastschrift erfolgt)",
	"paid_with": "how it was paid if stated: card, direct debit, paypal, cash, transfer",
	"supplier_address": "object with line1, line2, pincode, city, country of the issuer",
}


def run_extract_skill(ctx, skill):
	"""Read the PDF and fill empty receipt fields (OCR + one chat call)."""
	doc = ctx.doc
	content = _attachment_content(doc)
	if content is None:
		return SkillResult(FAILED, message=_("No PDF attached."), flags=[_flag("no_pdf", "block", _("No PDF attached."))])

	# Decide before reading: reading stores the document hash this check looks at.
	replaceable = {"currency"} if _currency_is_untouched_default(doc) else set()
	markdown = _document_text(ctx, content)
	from phamos.ai_agents.runner import applicable_skills, prompt_rules

	def _applicable(context):
		return applicable_skills(context, "Extract")

	answer, model = llm.chat_json(build_prompt(markdown, prompt_rules(ctx, "Extract"), doc.company), model=ctx.agent.llm_model or None)
	ctx.llm_calls += 1
	ctx.llm_model = model

	values, items, confidence, notes = map_answer(answer, doc)

	# Rules scoped to one supplier can only apply once the supplier is known. When this
	# read found a supplier that has its own rules, read again with them.
	if not ctx.party and values.get("supplier"):
		ctx.party = ("Supplier", values["supplier"])
		rules = prompt_rules(ctx, "Extract")
		if any(skill.party for skill in _applicable(ctx)):
			answer, model = llm.chat_json(build_prompt(markdown, rules, doc.company), model=ctx.agent.llm_model or None)
			ctx.llm_calls += 1
			values, items, confidence, notes = map_answer(answer, doc)
			notes["supplier_rules_applied"] = True

	fields_set = apply_values(doc, values, items, overwrite=ctx.overwrite, replaceable=replaceable)
	# Always keep the Version: the learning loop compares the AI's values with later human edits.
	doc.save(ignore_version=False)

	flags = [_flag("supplier_unknown", "warn", _("Supplier {0} is not in the system yet.").format(notes["supplier_name"]), "supplier")] if notes.get("supplier_name") and not values.get("supplier") else []
	company_currency = doc.company and frappe.get_cached_value("Company", doc.company, "default_currency")
	if company_currency and doc.currency != company_currency and flt(doc.conversion_rate) == 1:
		flags.append(_flag("no_exchange_rate", "warn",
			_("No exchange rate {0} → {1} for {2}; the amount in company currency is not converted.").format(
				doc.currency, company_currency, doc.posting_date), "conversion_rate"))
	flags += [
		_flag("low_confidence", "warn", _("The AI is unsure about {0}.").format(field), field)
		for field, score in confidence.items()
		if score is not None and score < LOW_CONFIDENCE
	]
	ctx.analysis["extraction"] = {"answer": answer, "values": _jsonable(values), "items": items, "confidence": confidence, **notes}
	overall = _overall_confidence(confidence)
	ctx.confidence = overall
	ctx.summary = summarize(doc)
	return SkillResult(PASSED, confidence=overall, fields_set=fields_set, flags=flags,
		message=_("{0} fields filled").format(len(fields_set)))


def extract_values(doc):
	"""Read the PDF and return {fieldname: value} without saving (Desk review dialog)."""
	content = _attachment_content(doc)
	if content is None:
		return None
	markdown = llm.ocr_pdf(content)
	from phamos.ai_agents.runner import get_agent, prompt_rules
	from phamos.ai_agents.context import AgentContext

	agent = get_agent(DOCTYPE)
	rules = prompt_rules(AgentContext(run=None, agent=agent, doc=doc, party=("Supplier", doc.supplier) if doc.supplier else None), "Extract") if agent else []
	answer, _model = llm.chat_json(build_prompt(markdown, rules, doc.company))
	values, items, _confidence, notes = map_answer(answer, doc)
	if notes.get("supplier_name") and not values.get("supplier"):
		values["supplier"] = notes["supplier_name"]  # the dialog offers to create it
	address = (answer.get("supplier_address") or {}) if isinstance(answer.get("supplier_address"), dict) else {}
	for key, target in (("line1", "address_line1"), ("line2", "address_line2"), ("pincode", "pincode"), ("city", "city"), ("country", "country")):
		if address.get(key):
			values[target] = address[key]
	return values


def build_prompt(document_markdown, rules, company=None):
	lines = [f'- "{key}": {description}' for key, (_field, description) in HEADER_FIELDS.items()]
	lines += [f'- "{key}": {description}' for key, description in ANALYSIS_ONLY.items()]
	lines.append('- "items": list of line items, each {"description", "quantity", "unit_price", "amount", "tax_rate"} (amounts without currency symbols)')
	lines.append('- "confidence": object with a number 0..1 for invoice_number, invoice_date, supplier_name, total_gross')
	recipient = f"The document was received by {company}. {company} is never the supplier.\n" if company else ""
	rules_text = ""
	if rules:
		rules_text = "\nAdditional rules, apply in this order:\n" + "\n".join(
			f"{i}. When: {cstr(r.case_description).strip()}\n   Do: {cstr(r.action).strip()}" for i, r in enumerate(rules, 1)
		)
	return f"""You read incoming invoices and receipts for the accounting team.
{recipient}Return one JSON object with these keys (omit keys you cannot find, never guess numbers):
{chr(10).join(lines)}
Numbers: the document may use German formatting (1.234,56 = 1234.56); output plain decimal numbers.{rules_text}

Document text (OCR):
---
{document_markdown[:MAX_DOCUMENT_CHARS]}
---"""


def map_answer(answer, doc):
	"""AI answer -> (field values, item rows, confidence per field, notes for the analysis)."""
	answer = answer if isinstance(answer, dict) else {}
	values, notes = {}, {}
	for key, (fieldname, _description) in HEADER_FIELDS.items():
		raw = answer.get(key)
		if raw in (None, "", []):
			continue
		value = _convert(fieldname, raw)
		if fieldname == "supplier":
			notes["supplier_name"] = cstr(raw).strip()
			value = _find_supplier(cstr(raw).strip(), answer.get("supplier_tax_id"), doc.company)
		if fieldname == "currency" and not frappe.db.exists("Currency", value):
			value = None
		if fieldname == "receipt_type" and value not in RECEIPT_TYPES:
			value = "Other"
		if value not in (None, ""):
			values[fieldname] = value

	items = []
	for row in answer.get("items") or []:
		if not isinstance(row, dict) or not cstr(row.get("description")).strip():
			continue
		qty = flt(_parse_german_number(row.get("quantity"))) or 1
		amount = flt(_parse_german_number(row.get("amount")))
		rate = flt(_parse_german_number(row.get("unit_price"))) or (amount / qty if qty else 0)
		items.append({
			"item_name": cstr(row.get("description")).strip()[:140],
			"qty": qty,
			"rate": rate,
			"amount": amount or rate * qty,
			"tax_rate": flt(_parse_german_number(row.get("tax_rate"))) or None,
		})

	key_to_field = {key: field for key, (field, _d) in HEADER_FIELDS.items()}
	confidence = {}
	for key, score in (answer.get("confidence") or {}).items():
		try:
			confidence[key_to_field.get(key, key)] = max(0.0, min(1.0, float(score)))
		except (TypeError, ValueError):
			pass
	for key in ANALYSIS_ONLY:
		if answer.get(key) not in (None, ""):
			notes[key] = answer[key]
	return values, items, confidence, notes


def apply_values(doc, values, items, overwrite=False, replaceable=()):
	"""Write values into empty fields (or all, when overwriting). Fields in `replaceable`
	hold a default nobody chose and may be replaced too. Returns the fields set."""
	fields_set = []
	for fieldname, value in values.items():
		current = doc.get(fieldname)
		if not overwrite and fieldname not in replaceable and not _is_empty(current):
			continue
		if current == value:
			continue
		doc.set(fieldname, value)
		fields_set.append(fieldname)
	if items and (overwrite or not doc.get("items")):
		doc.set("items", [])
		for row in items:
			doc.append("items", row)
		fields_set.append("items")
	if doc.is_return:
		doc.due_date = None
	return fields_set


def summarize(doc):
	parts = [doc.receipt_type or _("Document")]
	if doc.supplier_name or doc.supplier:
		parts.append(_("from {0}").format(doc.supplier_name or doc.supplier))
	text = " ".join(parts)
	if doc.sum:
		text += f": {fmt_money(doc.sum, currency=doc.currency)}"
	if doc.supplier_reference:
		text += f" · {doc.supplier_reference}"
	return text


def _currency_is_untouched_default(doc):
	"""True while the currency is still the company default set on creation: no human has
	changed it and no earlier AI reading set it."""
	company_currency = doc.company and frappe.get_cached_value("Company", doc.company, "default_currency")
	if not company_currency or doc.currency != company_currency or doc.ai_document_hash:
		return False
	return not frappe.db.exists(
		"Version", {"ref_doctype": DOCTYPE, "docname": doc.name, "data": ["like", '%"currency"%']}
	)


def _attachment_content(doc):
	url = (doc.attachment or "").strip()
	if not url.lower().endswith(".pdf"):
		return None
	try:
		return get_file(url)[1]
	except Exception:
		return None


def _document_text(ctx, content):
	"""OCR text of the attachment, reusing the stored text while the PDF is unchanged."""
	doc = ctx.doc
	digest = hashlib.sha1(content).hexdigest()
	if doc.ai_document_hash == digest and doc.ai_document_text:
		return doc.ai_document_text
	markdown = llm.ocr_pdf(content)
	ctx.llm_calls += 1
	doc.ai_document_text = markdown
	doc.ai_document_hash = digest
	return markdown


def _find_supplier(name, tax_id, company):
	"""Existing Supplier by exact name or by VAT ID; never a fuzzy guess."""
	if tax_id:
		by_tax = frappe.db.get_value("Supplier", {"tax_id": cstr(tax_id).replace(" ", "")}, "name")
		if by_tax:
			return by_tax
	if company and name and name.lower() == cstr(company).lower():
		return None
	return resolve_link_for_extract("Supplier", name)


def _convert(fieldname, raw):
	if fieldname in ("posting_date", "due_date"):
		try:
			return getdate(raw)
		except Exception:
			return None
	if fieldname in ("sum", "net_total", "total_taxes"):
		return flt(_parse_german_number(raw)) or None
	if fieldname == "supplier_iban":
		return cstr(raw).replace(" ", "").upper()
	return cstr(raw).strip()


def _is_empty(value):
	return value in (None, "", 0, 0.0) or (isinstance(value, list) and not value)


def _overall_confidence(confidence):
	key_scores = [confidence.get(f) for f in ("supplier_reference", "posting_date", "supplier", "sum")]
	key_scores = [s for s in key_scores if s is not None]
	return round(100 * sum(key_scores) / len(key_scores), 1) if key_scores else None


def _flag(code, severity, message, field=None):
	return {"code": code, "severity": severity, "message": message, "field": field}


def _jsonable(values):
	return {k: (str(v) if hasattr(v, "isoformat") else v) for k, v in values.items()}
