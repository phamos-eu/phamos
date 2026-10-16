// Event pages (/de/veranstaltungen/<slug>, /en/events/<slug>): ticket order and "Keep me posted".
// Loaded only on event pages (www/web_profile/profile.html). Prices come from the server; the order is
// validated again by phamos.marketing.web.order_tickets.
(function () {
	function serverMessage(data) {
		try {
			const messages = JSON.parse(data._server_messages || "[]").map((m) => JSON.parse(m).message);
			return messages.join(" ").replace(/<[^>]*>/g, "");
		} catch (e) {
			return "";
		}
	}

	async function post(form, body) {
		const headers = { Accept: "application/json" };
		if (window.frappe && frappe.csrf_token) headers["X-Frappe-CSRF-Token"] = frappe.csrf_token;
		const response = await fetch(form.action, { method: "POST", body, headers, credentials: "same-origin" });
		const data = await response.json().catch(() => ({}));
		if (!response.ok) throw new Error(serverMessage(data) || "");
		return data.message || {};
	}

	function wireDialog(dialog, openerKey, onOpen) {
		if (!dialog || typeof dialog.showModal !== "function") return;
		let opener = null;
		document.addEventListener("click", (event) => {
			const button = event.target.closest(`[data-wp-dialog-open="${openerKey}"]`);
			if (!button) return;
			opener = button;
			onOpen && onOpen();
			dialog.showModal();
		});
		dialog.querySelectorAll("[data-wp-dialog-close]").forEach((b) => b.addEventListener("click", () => dialog.close()));
		dialog.addEventListener("click", (event) => event.target === dialog && dialog.close());
		dialog.addEventListener("close", () => opener && opener.focus());
	}

	// A short message at the bottom of the page, for things that happen after a dialog closed.
	function toast(text, error) {
		let box = document.querySelector("[data-wp-toast]");
		if (!box) {
			box = document.createElement("div");
			box.className = "wp-toast";
			box.setAttribute("role", "status");
			box.dataset.wpToast = "";
			document.body.appendChild(box);
		}
		box.textContent = text;
		box.classList.toggle("wp-error", !!error);
		box.classList.add("wp-toast-show");
		clearTimeout(box._timer);
		box._timer = setTimeout(() => box.classList.remove("wp-toast-show"), 6000);
	}

	// --- tickets: three steps, a 20-minute hold, then the optional questions ------------------------------
	const ticketDialog = document.querySelector("[data-wp-ticket-dialog]");
	if (ticketDialog) {
		const form = ticketDialog.querySelector("[data-wp-ticket-form]");
		const $ = (selector) => form.querySelector(selector);
		const steps = [...form.querySelectorAll("[data-wp-step]")];
		const labels = [...form.querySelectorAll("[data-wp-step-label]")];
		const qty = $("[data-wp-qty]");
		const attends = $("[data-wp-attends]");
		const companions = $("[data-wp-people-rows]");
		const selfRow = $("[data-wp-self]");
		const addButton = $("[data-wp-add-person]");
		const template = $("[data-wp-companion-row]");
		const status = $("[data-wp-ticket-status]");
		const holdNote = $("[data-wp-hold]");
		const holdText = $("[data-wp-hold-text]");
		const holdClock = $("[data-wp-hold-clock]");
		const holdLabel = holdText.textContent;
		const printButton = $("[data-wp-print]");
		const back = $("[data-wp-back]");
		const next = $("[data-wp-next]");
		const submit = $("[data-wp-submit]");
		const toggle = $("[data-wp-company-toggle]");
		const free = form.dataset.free === "1";
		const taxRate = parseFloat(form.dataset.taxRate || "0");
		const max = parseInt(form.dataset.max || "10", 10);
		const windowMs = parseInt(form.dataset.holdMinutes || "20", 10) * 60 * 1000;
		const draftKey = `wp-ticket:${form.elements.event.value}`;
		const locale = form.dataset.lang === "de" ? "de-DE" : "en-GB";
		const money = new Intl.NumberFormat(locale, { style: "currency", currency: form.dataset.currency || "EUR" });
		const newId = () => (window.crypto && crypto.randomUUID ? crypto.randomUUID() : `h-${Date.now()}-${Math.random().toString(36).slice(2)}`);
		let gross = parseFloat(form.dataset.gross || "0");
		let current = 0;
		let order = null; // {reference, token} after a successful order
		let holdId = newId();
		let expiresAt = 0;
		let holdTimer = null; // one tick per second while a hold runs

		const companionRows = () => [...companions.querySelectorAll(".wp-people-row:not([data-wp-self])")];
		const count = () => (attends.checked ? 1 : 0) + companionRows().length;
		const value = (name) => (form.elements[name] ? String(form.elements[name].value || "").trim() : "");
		const storage = {
			get() { try { return JSON.parse(localStorage.getItem(draftKey) || "null"); } catch (e) { return null; } },
			set(data) { try { localStorage.setItem(draftKey, JSON.stringify(data)); } catch (e) { /* private mode */ } },
			clear() { try { localStorage.removeItem(draftKey); } catch (e) { /* private mode */ } },
		};

		function addRow(values = {}) {
			if (count() >= max) return null;
			const row = template.content.firstElementChild.cloneNode(true);
			row.querySelector('[data-field="full_name"]').value = values.full_name || "";
			row.querySelector('[data-field="email"]').value = values.email || "";
			companions.appendChild(row);
			return row;
		}

		// The person table: you (when attending) plus one row per further ticket holder.
		function renderCompanions() {
			if (!count()) addRow(); // somebody needs a ticket
			selfRow.hidden = !attends.checked;
			selfRow.querySelector("[data-wp-self-name]").textContent = value("contact_name") || "–";
			selfRow.querySelector("[data-wp-self-email]").textContent = value("contact_email");
			const rows = [...(attends.checked ? [selfRow] : []), ...companionRows()];
			rows.forEach((row, i) => {
				row.querySelector(".wp-people-no").textContent = String(i + 1);
				const price = row.querySelector("[data-wp-row-price]");
				if (price) price.textContent = money.format(gross);
			});
			const n = rows.length;
			qty.value = String(n);
			addButton.disabled = n >= max;
			$("[data-wp-people-max]").hidden = n < max;
			const total = $("[data-wp-people-total]");
			if (total) total.textContent = money.format(gross * n);
		}

		function holders() {
			const list = attends.checked ? [{ full_name: value("contact_name"), email: value("contact_email") }] : [];
			for (const row of companionRows()) {
				list.push({
					full_name: row.querySelector('[data-field="full_name"]').value.trim(),
					email: row.querySelector('[data-field="email"]').value.trim(),
				});
			}
			return list;
		}

		// --- the draft: entries survive a reload or a closed dialog for 20 minutes -----------------------
		const draftFields = ["contact_name", "contact_email", "qty", "is_company", "company", "vat_id", "billing_name",
			"billing_email", "address_line1", "postcode", "city", "country", "phone"];
		let saveTimer = null;
		function saveDraft() {
			if (order) return;
			clearTimeout(saveTimer);
			saveTimer = setTimeout(() => {
				const fields = {};
				for (const name of draftFields) {
					const el = form.elements[name];
					if (el) fields[name] = el.type === "checkbox" ? el.checked : el.value;
				}
				storage.set({ ts: Date.now(), holdId, step: current, attends: attends.checked, fields,
					companions: companionRows().map((row) => ({
						full_name: row.querySelector('[data-field="full_name"]').value,
						email: row.querySelector('[data-field="email"]').value })) });
			}, 400);
		}
		function restoreDraft() {
			const draft = storage.get();
			if (!draft) return false;
			if (Date.now() - draft.ts > windowMs) { storage.clear(); return false; }
			holdId = draft.holdId || holdId;
			attends.checked = draft.attends !== false;
			for (const [name, val] of Object.entries(draft.fields || {})) {
				const el = form.elements[name];
				if (!el) continue;
				if (el.type === "checkbox") el.checked = !!val; else el.value = val;
			}
			if (toggle) { $("[data-wp-company]").hidden = !toggle.checked; form.elements.company.required = toggle.checked; }
			companionRows().forEach((row) => row.remove());
			(draft.companions || []).forEach((c) => addRow(c));
			renderCompanions();
			current = Math.min(draft.step || 0, steps.length - 1);
			return true;
		}

		// --- the hold: seats and their price for 20 minutes --------------------------------------------
		// Either the countdown ("Reserved for you 19:42") or a message instead of it.
		function showHold(text, error) {
			holdNote.hidden = !text;
			holdText.textContent = text || "";
			holdClock.hidden = true;
			holdNote.classList.toggle("wp-error", !!error);
		}
		function tick() {
			const left = Math.max(0, expiresAt - Date.now());
			if (!left) return expire();
			const minutes = Math.floor(left / 60000);
			const seconds = Math.floor((left % 60000) / 1000);
			holdClock.textContent = `${minutes}:${String(seconds).padStart(2, "0")}`;
			holdNote.classList.toggle("wp-hold-ending", left < 2 * 60 * 1000);
		}
		function startClock(prefix) {
			holdNote.hidden = false;
			holdNote.classList.remove("wp-error");
			holdText.textContent = prefix ? `${prefix} ${holdLabel}` : holdLabel;
			holdClock.hidden = false;
			clearInterval(holdTimer);
			tick();
			holdTimer = setInterval(tick, 1000);
		}
		async function hold() {
			if (order) return;
			const body = new FormData();
			body.append("event", form.elements.event.value);
			body.append("lang", form.elements.lang.value);
			body.append("hold_id", holdId);
			body.append("qty", String(holders().length || count()));
			try {
				const result = await post({ action: form.dataset.holdAction }, body);
				if (!result.ok) {
					clearInterval(holdTimer);
					expiresAt = 0;
					showHold(holdNote.dataset.soldout, true);
					return false;
				}
				expiresAt = result.expires;
				if (!free && result.gross && Math.abs(result.gross - gross) > 0.001) {
					// Another price row applies to this number of tickets (e.g. the early-bird quota is used up).
					gross = result.gross;
					form.dataset.priceTitle = result.price_title || "";
					renderCompanions();
				}
				startClock(restoredNote);
				restoredNote = "";
				return true;
			} catch (error) {
				return true; // the order re-checks everything; a failed hold must not block the visitor
			}
		}
		let restoredNote = "";
		function expire() {
			clearInterval(holdTimer);
			if (order) return;
			// Time is up: the entries are thrown away, seats and prices are checked again.
			expiresAt = 0;
			storage.clear();
			resetForm();
			showHold(holdNote.dataset.expired, true);
		}

		function show(index) {
			index = Math.max(0, Math.min(index, steps.length - 1));
			current = index;
			steps.forEach((step, i) => (step.hidden = i !== index));
			labels.forEach((label, i) => {
				label.toggleAttribute("aria-current", i === index);
				label.classList.toggle("wp-step-done", i < index);
			});
			back.hidden = index === 0;
			next.hidden = index === steps.length - 1;
			submit.hidden = index !== steps.length - 1;
			printButton.hidden = index !== steps.length - 1;
			submit.disabled = false;
			status.textContent = "";
			status.classList.remove("wp-error");
			if (index === steps.length - 1) renderSummary();
			const focus = steps[index].querySelector("input:not([type=hidden]):not([type=checkbox]), select");
			if (focus) setTimeout(() => focus.focus(), 0);
		}

		function valid(step) {
			const fields = [...step.querySelectorAll("input, select")].filter((f) => !f.closest("[hidden]"));
			const bad = fields.find((f) => !f.checkValidity());
			if (bad) {
				status.classList.add("wp-error");
				status.textContent = status.dataset.invalid;
				bad.reportValidity();
				return false;
			}
			return true;
		}

		// The review step reads like the order document: address field, item table, net, VAT, total.
		const cell = (text, className) => {
			const td = document.createElement("td");
			td.textContent = text;
			if (className) td.className = className;
			return td;
		};
		function renderSummary() {
			const people = holders();
			$("[data-wp-summary-email]").textContent = value("contact_email");
			const address = free
				? [value("contact_name"), value("contact_email")]
				: [toggle && toggle.checked ? value("company") : "", value("billing_name"), value("address_line1"),
					`${value("postcode")} ${value("city")}`, form.elements.country.selectedOptions[0]?.textContent || "",
					toggle && toggle.checked && value("vat_id") ? `${form.dataset.lang === "de" ? "USt-IdNr." : "VAT ID"} ${value("vat_id")}` : ""];
			$("[data-wp-summary-billing]").replaceChildren(...address.filter(Boolean).flatMap((line, i) =>
				(i ? [document.createElement("br"), line] : [line])));
			const title = form.dataset.priceTitle ? ` (${form.dataset.priceTitle})` : "";
			$("[data-wp-invoice-rows]").replaceChildren(...people.map((p, i) => {
				const tr = document.createElement("tr");
				const name = p.email && p.email !== value("contact_email") ? `${p.full_name} (${p.email})` : p.full_name;
				tr.append(cell(String(i + 1), "wp-num"), cell(`${form.dataset.itemName}${title}: ${name}`));
				if (!free) tr.append(cell("1", "wp-num"), cell(money.format(gross), "wp-num"), cell(money.format(gross), "wp-num"));
				return tr;
			}));
			if (free) return;
			const total = gross * people.length;
			const net = total / (1 + taxRate / 100);
			$("[data-wp-summary-net]").textContent = money.format(net);
			$("[data-wp-summary-tax]").textContent = money.format(total - net);
			$("[data-wp-summary-total]").textContent = money.format(total);
		}

		// "Print": just the order sheet, in a frame with the page's styles (a preview of the order PDF).
		function printInvoice() {
			const frame = document.createElement("iframe");
			frame.className = "wp-print-frame";
			frame.setAttribute("aria-hidden", "true");
			document.body.appendChild(frame);
			const styles = [...document.querySelectorAll('link[rel="stylesheet"], style')].map((el) => el.outerHTML).join("");
			const doc = frame.contentDocument;
			doc.open();
			doc.write(`<!doctype html><html lang="${form.dataset.lang}"><head><meta charset="utf-8"><title>${document.title}</title>${styles}<style>@page { size: A4; margin: 0; }</style></head>`
				+ `<body class="wp-print-body">${$("[data-wp-invoice]").outerHTML}</body></html>`);
			doc.close();
			const run = () => {
				frame.contentWindow.focus();
				frame.contentWindow.print();
				setTimeout(() => frame.remove(), 1000);
			};
			if (doc.readyState === "complete") setTimeout(run, 300); else frame.addEventListener("load", run);
		}
		printButton.addEventListener("click", printInvoice);

		function resetForm() {
			form.reset();
			order = null;
			holdId = newId();
			gross = parseFloat(form.dataset.gross || "0");
			companionRows().forEach((row) => row.remove());
			if (toggle) $("[data-wp-company]").hidden = true;
			$("[data-wp-steps]").hidden = false;
			$("[data-wp-ticket-actions]").hidden = false;
			$("[data-wp-ticket-success]").hidden = true;
			$("[data-wp-consents-save]").disabled = false;
			$("[data-wp-consents-status]").textContent = "";
			$("[data-wp-ticket-pdf]").hidden = true;
			back.disabled = false;
			renderCompanions();
			show(0);
		}

		addButton.addEventListener("click", () => {
			const row = addRow();
			renderCompanions();
			hold();
			saveDraft();
			if (row) row.querySelector('[data-field="full_name"]').focus();
		});
		companions.addEventListener("click", (event) => {
			const remove = event.target.closest("[data-wp-remove-person]");
			if (!remove) return;
			remove.closest(".wp-people-row").remove();
			renderCompanions();
			hold();
			saveDraft();
		});
		attends.addEventListener("change", () => { renderCompanions(); hold(); });
		for (const name of ["contact_name", "contact_email"]) form.elements[name].addEventListener("input", renderCompanions);
		form.addEventListener("input", saveDraft);
		form.addEventListener("change", saveDraft);
		if (toggle) {
			toggle.addEventListener("change", () => {
				$("[data-wp-company]").hidden = !toggle.checked;
				form.elements.company.required = toggle.checked;
			});
		}
		// One step at a time: a second click while the seats are being checked must not skip a step.
		let advancing = false;
		next.addEventListener("click", async () => {
			if (advancing || current >= steps.length - 1 || !valid(steps[current])) return;
			advancing = true;
			next.disabled = true;
			const from = current;
			try {
				if (!expiresAt || Date.now() > expiresAt) {
					if (!(await hold())) return;
				}
				if (from === 0 && !free) {
					// The billing step starts with the contact's name and email.
					for (const [field, source] of [["billing_name", "contact_name"], ["billing_email", "contact_email"]]) {
						if (!value(field)) form.elements[field].value = value(source);
					}
				}
				if (current === from) show(from + 1);
				saveDraft();
			} finally {
				advancing = false;
				next.disabled = false;
			}
		});
		back.addEventListener("click", () => current > 0 && show(current - 1));
		form.querySelectorAll("[data-wp-goto]").forEach((button) => button.addEventListener("click", () => {
			const target = steps.findIndex((step) => step.dataset.wpStep === button.dataset.wpGoto);
			if (target >= 0) show(target);
		}));
		form.querySelectorAll("[data-wp-terms-open]").forEach((link) => link.addEventListener("click", (event) => {
			event.preventDefault();
			const terms = form.querySelector("#wp-terms");
			if (terms) { terms.open = true; terms.scrollIntoView({ block: "nearest" }); }
		}));

		wireDialog(ticketDialog, "tickets", () => {
			if (order) return;
			const restored = !rows_started() && restoreDraft();
			if (!restored) renderCompanions();
			show(current);
			restoredNote = restored ? holdNote.dataset.restored : "";
			hold();
		});
		function rows_started() {
			return !!(value("contact_name") || value("contact_email"));
		}
		// After an order, closing the dialog starts afresh; before, the entries stay (and the draft).
		// Called directly as well: the "close" event can arrive late (or not at all) in background tabs.
		function finishOrder() {
			if (!order) return;
			if (ticketDialog.open) ticketDialog.close();
			storage.clear();
			resetForm();
			showHold("");
		}
		ticketDialog.addEventListener("close", finishOrder);
		$("[data-wp-ticket-success]").querySelectorAll("[data-wp-dialog-close]").forEach((button) =>
			button.addEventListener("click", finishOrder));

		form.addEventListener("submit", async (event) => {
			event.preventDefault();
			if (current !== steps.length - 1) return next.click();
			if (!expiresAt || Date.now() > expiresAt) {
				if (!(await hold())) return;
				renderSummary();
			}
			const people = holders();
			const body = new FormData();
			for (const name of ["event", "lang", "website"]) body.append(name, form.elements[name].value);
			body.append("contact", JSON.stringify({ full_name: value("contact_name"), email: value("contact_email"), phone: value("phone") }));
			body.append("attends", attends.checked ? "1" : "0");
			body.append("companions", JSON.stringify(people.slice(attends.checked ? 1 : 0)));
			body.append("hold_id", holdId);
			if (!free) {
				body.append("billing", JSON.stringify({
					full_name: value("billing_name"), email: value("billing_email"), phone: value("phone"),
					is_company: toggle && toggle.checked ? 1 : 0, company: value("company"), vat_id: value("vat_id"),
					address_line1: value("address_line1"), postcode: value("postcode"), city: value("city"), country: value("country"),
				}));
				body.append("expected_total", (gross * people.length).toFixed(2));
			}
			submit.disabled = true;
			back.disabled = true;
			submit.classList.add("wp-busy");
			status.classList.remove("wp-error");
			status.textContent = status.dataset.sending;
			try {
				const result = await post(form, body);
				order = { reference: result.reference, token: result.token };
				storage.clear();
				clearInterval(holdTimer);
				showHold("");
				steps.forEach((step) => (step.hidden = true));
				$("[data-wp-steps]").hidden = true;
				$("[data-wp-ticket-actions]").hidden = true;
				const success = $("[data-wp-ticket-success]");
				success.querySelector("[data-wp-ticket-reference]").textContent = result.reference || "";
				success.querySelector("[data-wp-ticket-email]").textContent = result.tickets_to || value("contact_email");
				const pdf = success.querySelector("[data-wp-ticket-pdf]");
				pdf.hidden = !result.pdf_url;
				if (result.pdf_url) pdf.href = result.pdf_url;
				success.hidden = false;
			} catch (error) {
				submit.disabled = false;
				back.disabled = false;
				status.classList.add("wp-error");
				status.textContent = error.message || status.dataset.failed;
			} finally {
				submit.classList.remove("wp-busy");
			}
		});

		const consentStatus = $("[data-wp-consents-status]");
		$("[data-wp-consents-save]").addEventListener("click", async (event) => {
			if (!order) return;
			const button = event.currentTarget;
			const consents = {};
			for (const name of ["newsletter", "attendee_contact", "public_listing"]) consents[name] = form.elements[name].checked ? 1 : 0;
			const body = new FormData();
			body.append("event", form.elements.event.value);
			body.append("lang", form.elements.lang.value);
			body.append("reference", order.reference);
			body.append("token", order.token);
			body.append("consents", JSON.stringify(consents));
			button.disabled = true;
			button.classList.add("wp-busy");
			try {
				const result = await post({ action: form.dataset.consentAction }, body);
				const optin = result.status === "confirmation_sent";
				// Done: the dialog closes at once, the page confirms in a toast.
				const message = optin ? consentStatus.dataset.optin : consentStatus.dataset.saved;
				finishOrder();
				toast(message);
			} catch (error) {
				button.classList.remove("wp-busy");
				button.disabled = false;
				consentStatus.classList.add("wp-error");
				consentStatus.textContent = error.message || consentStatus.dataset.failed;
			}
		});
	}

	// --- interest: Yes / Maybe / No, remembered in this browser ----------------------------------------
	const interest = document.querySelector("[data-wp-interest]");
	if (interest) {
		const key = `wp-interest:${interest.dataset.event}`;
		const read = () => { try { return localStorage.getItem(key); } catch (e) { return null; } };
		const write = (v) => { try { localStorage.setItem(key, v); } catch (e) { /* private mode */ } };
		const mark = (choice) => interest.querySelectorAll("[data-response]").forEach((b) =>
			b.setAttribute("aria-pressed", b.dataset.response === choice ? "true" : "false"));
		mark(read());
		interest.addEventListener("click", async (event) => {
			const button = event.target.closest("[data-response]");
			if (!button) return;
			const previous = read();
			const response = button.dataset.response;
			if (previous === response) return;
			const body = new FormData();
			body.append("event", interest.dataset.event);
			body.append("lang", interest.dataset.lang);
			body.append("response", response);
			if (previous) body.append("previous", previous);
			try {
				const result = await post({ action: interest.dataset.action }, body);
				write(response);
				mark(response);
				for (const [k, n] of Object.entries(result.counts || {})) {
					const el = interest.querySelector(`[data-count="${k}"]`);
					if (el) el.textContent = n;
				}
			} catch (error) { /* rate limit or offline: nothing to do */ }
		});
	}

	// --- create reminder: up to three dates, one calendar file --------------------------------------------
	const reminderDialog = document.querySelector("[data-wp-reminder-dialog]");
	if (reminderDialog) {
		const form = reminderDialog.querySelector("[data-wp-reminder-form]");
		const status = form.querySelector("[data-wp-reminder-status]");
		const inputs = [...form.querySelectorAll("[data-wp-reminder-at]")];
		const local = (date) => new Date(date.getTime() - date.getTimezoneOffset() * 60000).toISOString().slice(0, 16);
		try { form.querySelector("[data-wp-reminder-tz]").value = Intl.DateTimeFormat().resolvedOptions().timeZone || ""; } catch (e) { /* old browser */ }
		wireDialog(reminderDialog, "reminder", () => {
			status.textContent = "";
			const now = local(new Date());
			inputs.forEach((input) => (input.min = now));
			setTimeout(() => inputs[0].focus(), 0);
		});
		form.addEventListener("submit", (event) => {
			event.preventDefault();
			const dates = inputs.map((input) => input.value).filter(Boolean);
			if (!dates.length || inputs.some((input) => !input.checkValidity())) {
				status.classList.add("wp-error");
				status.textContent = status.dataset.invalid;
				return;
			}
			const params = new URLSearchParams({ event: form.elements.event.value, lang: form.elements.lang.value,
				tz: form.elements.tz.value, at: dates.join(",") });
			window.location.href = `${form.action}?${params}`;
			reminderDialog.close();
		});
	}

	// --- keep me posted (double opt-in) -----------------------------------------------------------------
	const subscribeDialog = document.querySelector("[data-wp-subscribe-dialog]");
	if (subscribeDialog) {
		const form = subscribeDialog.querySelector("[data-wp-subscribe-form]");
		const status = form.querySelector("[data-wp-subscribe-status]");
		const submit = form.querySelector("button[type=submit]");
		wireDialog(subscribeDialog, "subscribe", () => {
			status.textContent = "";
			submit.disabled = false;
			setTimeout(() => form.elements.email.focus(), 0);
		});
		form.addEventListener("submit", async (event) => {
			event.preventDefault();
			status.classList.remove("wp-error");
			if (!form.checkValidity()) {
				status.classList.add("wp-error");
				status.textContent = status.dataset.invalid;
				return;
			}
			submit.disabled = true;
			status.textContent = status.dataset.sending;
			try {
				const result = await post(form, new FormData(form));
				status.textContent = result.status === "already" ? status.dataset.already : status.dataset.sent;
			} catch (error) {
				submit.disabled = false;
				status.classList.add("wp-error");
				status.textContent = error.message || status.dataset.failed;
			}
		});
	}
})();
