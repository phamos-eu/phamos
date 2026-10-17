# Copyright (c) 2026, phamos.eu and contributors
# For license information, please see license.txt

"""The assignment library: which expense account a kind of receipt line goes to.

Entries (doctype Account Assignment) map a normalized line description, for one supplier
or for all, to an expense account. They come from people choosing accounts in the
cockpit, from submitted Purchase Invoices and from a one-time import of past invoices.
The AI's own proposals are stored too, at the lowest validation level, and only count
once a person accepts them.

The receipt and invoice lines stay the source of truth; the library can be rebuilt.
"""

import re
import unicodedata

import frappe
from frappe import _
from frappe.utils import add_months, cint, cstr, getdate, nowdate, strip_html
from rapidfuzz import fuzz

DOCTYPE = "Account Assignment"
VALIDATION_RANK = {"AI": 0, "Confirmed": 1, "Officially Validated": 2}
BASE_SCORE = {"Officially Validated": 100, "Confirmed": 95}
AUTO_APPLY_SCORE = 85
MATCH_SCORE = 85
MAX_PATTERN = 140

STOP_WORDS = set(
	"""
	januar februar maerz april mai juni juli august september oktober november dezember
	jan feb mar apr jun jul aug sep sept okt oct nov dez dec
	january february march may june july october december
	monat monate monatlich monthly month months jahr jahrlich jaehrlich yearly annual year woche weekly
	rechnung invoice rechnungsnr beleg quittung receipt gutschrift credit note
	zeitraum period leistungszeitraum from to bis vom von ab zu zum zur fuer for the a an der die das den dem des und and of
	mit with ohne without inkl inklusive incl zzgl plus excl in im on at per pro je
	mwst ust vat tax steuer netto brutto net gross summe total betrag amount gesamt
	eur euro usd chf gbp nr no nummer number pos position stk st stueck pcs piece pieces x
	h std stunden stunde hours hour tag tage days day gb tb mb
	""".split()
)


# --- normalization -------------------------------------------------------------------------


def normalize_description(text):
	"""Lowercase words that identify a kind of purchase, without numbers, dates, ids,
	amounts, months, units or invoice words. "iCloud+ with 200 GB (Monthly)" and
	"iCloud+ 2 TB (monthly)" both become "icloud+"."""
	text = strip_html(cstr(text)).lower()
	text = text.replace("ä", "ae").replace("ö", "oe").replace("ü", "ue").replace("ß", "ss")
	text = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode()
	text = re.sub(r"[^a-z0-9&+\s\-]", " ", text)
	words = []
	for token in text.split():
		token = token.strip("-")
		if not token or _is_number_or_id(token):
			continue
		for part in token.split("-"):
			if len(part) > 1 and not _is_number_or_id(part) and part not in STOP_WORDS and part not in words:
				words.append(part)
	return " ".join(words)[:MAX_PATTERN].strip()


def _is_number_or_id(token):
	digits = sum(c.isdigit() for c in token)
	if not digits:
		return False
	if token.isdigit():
		return True
	# ids such as p-0155, re12345, 2026-10 (three digits or more with at most three letters)
	return digits >= 3 and sum(c.isalpha() for c in token) <= 3


# --- matching ------------------------------------------------------------------------------


def entries(company):
	return frappe.get_all(
		DOCTYPE,
		filters={"company": company, "disabled": 0},
		fields=["name", "supplier", "pattern", "expense_account", "cost_center", "validation", "hits", "misses"],
	)


def is_retired(entry):
	return entry.validation != "Officially Validated" and cint(entry.misses) >= 2 and cint(entry.misses) > cint(entry.hits)


def base_score(entry):
	return BASE_SCORE.get(entry.validation) or 75 + 5 * min(cint(entry.hits), 2)


def find(description, supplier, company, match_score=MATCH_SCORE, library=None):
	"""Candidate accounts for a line, best first:
	[{account, cost_center, score, source, entry, validation, hits, reason}].

	Tiers: exact pattern for this supplier, exact pattern for all suppliers (-5) or another
	supplier (-10), fuzzy pattern (score × similarity), and the supplier's usual account
	when all its confirmed entries point to one account. Two different accounts that score
	almost the same make the line unclear (capped at 70)."""
	pattern = normalize_description(description)
	library = entries(company) if library is None else library
	best = {}

	def offer(account, score, **info):
		if account not in best or score > best[account]["score"]:
			best[account] = {"account": account, "score": round(score, 1), **info}

	if pattern:
		for entry in library:
			if is_retired(entry):
				continue
			score = base_score(entry)
			if entry.supplier and entry.supplier != supplier:
				score -= 10
				scope = _("supplier {0}").format(entry.supplier)
			elif not entry.supplier:
				score -= 5
				scope = _("all suppliers")
			else:
				scope = _("this supplier")
			if entry.pattern == pattern:
				similarity = 100
			else:
				similarity = fuzz.token_sort_ratio(pattern, entry.pattern)
				if similarity < match_score:
					continue
				score = score * similarity / 100
			offer(
				entry.expense_account,
				score,
				cost_center=entry.cost_center,
				source="Library",
				entry=entry.name,
				validation=entry.validation,
				hits=cint(entry.hits),
				reason=_("Library {0} ({1}, {2}×, {3}): \"{4}\"{5}").format(
					entry.name, entry.validation, cint(entry.hits), scope, entry.pattern,
					"" if similarity == 100 else _(", {0} % similar").format(int(similarity)),
				),
			)

	usual = supplier_usual_account(supplier, library)
	if usual:
		offer(usual["account"], AUTO_APPLY_SCORE, cost_center=usual.get("cost_center"), source="Supplier History",
			entry=None, validation="Confirmed", hits=usual["hits"],
			reason=_("{0} is booked on this account every time ({1}×).").format(supplier, usual["hits"]))

	candidates = sorted(best.values(), key=lambda c: -c["score"])
	if len(candidates) > 1 and candidates[0]["score"] >= AUTO_APPLY_SCORE and candidates[0]["score"] - candidates[1]["score"] < 5:
		candidates[0]["score"] = min(candidates[0]["score"], 70)
		candidates[0]["reason"] += " " + _("Another account scores almost the same.")
	return candidates


def supplier_usual_account(supplier, library):
	"""The one account all confirmed entries of a supplier point to, with at least two uses."""
	if not supplier:
		return None
	rows = [e for e in library if e.supplier == supplier and VALIDATION_RANK[e.validation] >= 1 and not is_retired(e)]
	accounts = {e.expense_account for e in rows}
	hits = sum(cint(e.hits) for e in rows)
	if len(accounts) == 1 and hits >= 2:
		return {"account": accounts.pop(), "hits": hits, "cost_center": rows[0].cost_center}
	return None


# --- learning ------------------------------------------------------------------------------


def _key(company, supplier, pattern, account):
	return {"company": company, "supplier": supplier or ("is", "not set"), "pattern": pattern, "expense_account": account}


def learn(company, supplier, description, account, cost_center=None, validation="Confirmed", origin="Human",
		receipt=None, hits=1):
	"""Record that lines like `description` go to `account`. Adds `hits` uses and raises the
	validation if the new one is higher. Returns the entry name, or None for lines without
	words to match on or accounts that are not expense accounts."""
	from phamos.accounting.expense_accounts import is_expense_account

	pattern = normalize_description(description)
	if not pattern or not account or not is_expense_account(account, company):
		return None
	name = frappe.db.get_value(DOCTYPE, _key(company, supplier, pattern, account), "name")
	if name:
		current = frappe.db.get_value(DOCTYPE, name, ["validation", "hits"], as_dict=True)
		values = {"hits": cint(current.hits) + cint(hits), "last_used": nowdate()}
		if receipt:
			values["last_receipt"] = receipt
		if cost_center:
			values["cost_center"] = cost_center
		if VALIDATION_RANK[validation] > VALIDATION_RANK[current.validation]:
			values.update(validation=validation, validated_by=frappe.session.user, validated_at=frappe.utils.now_datetime())
		frappe.db.set_value(DOCTYPE, name, values)
		return name
	doc = frappe.get_doc(
		{
			"doctype": DOCTYPE,
			"company": company,
			"supplier": supplier,
			"sample_description": cstr(description).strip()[:140],
			"expense_account": account,
			"cost_center": cost_center,
			"validation": validation,
			"origin": origin,
			"hits": cint(hits),
			"last_used": nowdate(),
			"last_receipt": receipt,
		}
	)
	doc.insert(ignore_permissions=True)
	return doc.name


def record_miss(company, supplier, description, account):
	name = frappe.db.get_value(DOCTYPE, _key(company, supplier, normalize_description(description), account), "name")
	if name:
		frappe.db.set_value(DOCTYPE, name, "misses", cint(frappe.db.get_value(DOCTYPE, name, "misses")) + 1)
	return name


# --- receipts ------------------------------------------------------------------------------

AI_SOURCES = ("Library", "Supplier History", "AI")
CONFIRMING_STATUSES = ("Approved to Pay", "Sent to DATEV", "Paid")


def ai_user():
	return frappe.db.get_single_value("phamos Settings", "ai_accountant_user")


def mark_human_choices(doc):
	"""Before a receipt is saved by a person: lines whose account the person set or changed
	become source Human. A changed AI proposal is remembered as a miss for on_update."""
	if frappe.session.user == ai_user():
		return
	misses = []
	for row in doc.get("items") or []:
		if not row.expense_account:
			continue
		if row.assignment_source in AI_SOURCES and row.expense_account != row.ai_expense_account:
			if row.ai_expense_account:
				misses.append((row.item_name, row.ai_expense_account))
			row.assignment_source = "Human"
			row.assignment = None
		elif not row.assignment_source:
			row.assignment_source = "Human"
	doc.flags.assignment_misses = misses


def learn_from_receipt(doc, confirm_all=False):
	"""After a receipt is saved: write the person's choices to the library (Confirmed).
	With confirm_all (the receipt was approved, sent or invoiced) the AI's accepted
	proposals are confirmed as well. Each line is learned once per account."""
	company = doc.company or frappe.defaults.get_global_default("company")
	for description, account in doc.flags.pop("assignment_misses", None) or []:
		record_miss(company, doc.supplier, description, account)
	if frappe.session.user == ai_user() and not confirm_all:
		return
	confirm_all = confirm_all or doc.status in CONFIRMING_STATUSES
	for row in doc.get("items") or []:
		if not row.expense_account or row.expense_account == row.learned_account:
			continue
		if row.assignment_source != "Human" and not confirm_all:
			continue
		if row.learned_account:
			record_miss(company, doc.supplier, row.item_name, row.learned_account)
		entry = learn(company, doc.supplier, row.item_name, row.expense_account, row.cost_center or doc.cost_center,
			validation="Confirmed", origin="Human", receipt=doc.name)
		if entry:
			frappe.db.set_value(row.doctype, row.name, "learned_account", row.expense_account, update_modified=False)
			row.learned_account = row.expense_account


# --- Purchase Invoices and history -------------------------------------------------------


def line_description(item):
	"""What a Purchase Invoice line says: the description when it adds something, else the item name."""
	description = strip_html(cstr(item.description)).strip()
	return description if description and normalize_description(description) else cstr(item.item_name)


def learn_from_purchase_invoice(doc, method=None):
	"""Purchase Invoice on_submit: confirm the receipt's lines, or learn the invoice lines."""
	receipt = frappe.db.get_value("Accounting Receipt", {"purchase_invoice": doc.name}, "name")
	if receipt:
		learn_from_receipt(frappe.get_doc("Accounting Receipt", receipt), confirm_all=True)
		return
	for item in doc.items:
		if item.expense_account:
			learn(doc.company, doc.supplier, line_description(item), item.expense_account, item.cost_center,
				validation="Confirmed", origin="History")


@frappe.whitelist(methods=["POST"])
def rebuild_from_history(company=None, months=36):
	"""Fill the library from submitted Purchase Invoices of the last `months`.

	Idempotent: an entry's hits become at least the number of invoice lines behind it, so
	running it twice does not double count. Receipt lines are not touched."""
	frappe.only_for(("System Manager", "Accounts Manager"))
	company = company or frappe.defaults.get_global_default("company")
	since = add_months(getdate(nowdate()), -cint(months))
	rows = frappe.db.sql(
		"""select pi.supplier, pii.item_name, pii.description, pii.expense_account, pii.cost_center
		from `tabPurchase Invoice Item` pii join `tabPurchase Invoice` pi on pi.name = pii.parent
		where pi.docstatus = 1 and pi.company = %s and pi.posting_date >= %s and ifnull(pii.expense_account, '') != ''""",
		(company, since),
		as_dict=True,
	)
	counts = {}
	for row in rows:
		pattern = normalize_description(line_description(row))
		if not pattern:
			continue
		key = (row.supplier, pattern, row.expense_account)
		entry = counts.setdefault(key, {"hits": 0, "description": line_description(row), "cost_center": row.cost_center})
		entry["hits"] += 1
	created = updated = 0
	for (supplier, pattern, account), info in counts.items():
		name = frappe.db.get_value(DOCTYPE, _key(company, supplier, pattern, account), ["name", "hits", "validation"], as_dict=True)
		if name:
			values = {"hits": max(cint(name.hits), info["hits"])}
			if VALIDATION_RANK[name.validation] < 1:
				values["validation"] = "Confirmed"
			frappe.db.set_value(DOCTYPE, name.name, values)
			updated += 1
		elif learn(company, supplier, info["description"], account, info["cost_center"], "Confirmed", "History", hits=info["hits"]):
			created += 1
	return {"invoice_lines": len(rows), "created": created, "updated": updated}
