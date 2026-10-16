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

	// --- tickets ---------------------------------------------------------------------------------------
	const ticketDialog = document.querySelector("[data-wp-ticket-dialog]");
	if (ticketDialog) {
		const form = ticketDialog.querySelector("[data-wp-ticket-form]");
		const qty = form.querySelector("[data-wp-qty]");
		const rows = form.querySelector("[data-wp-attendees]");
		const template = form.querySelector("[data-wp-attendee-row]");
		const billing = form.querySelector("[data-wp-billing]");
		const companyBox = form.querySelector("[data-wp-company]");
		const status = form.querySelector("[data-wp-ticket-status]");
		const submit = form.querySelector("button[type=submit]");
		const free = form.dataset.free === "1";
		const gross = parseFloat(form.dataset.gross || "0");
		const taxRate = parseFloat(form.dataset.taxRate || "0");
		const max = parseInt(form.dataset.max || "10", 10);
		const money = new Intl.NumberFormat(form.dataset.lang === "de" ? "de-DE" : "en-GB",
			{ style: "currency", currency: form.dataset.currency || "EUR" });

		function count() {
			return Math.min(Math.max(parseInt(qty.value || "1", 10) || 1, 1), max);
		}

		function renderRows() {
			const wanted = count();
			while (rows.children.length < wanted) rows.appendChild(template.content.firstElementChild.cloneNode(true));
			while (rows.children.length > wanted) rows.lastElementChild.remove();
			renderSummary();
		}

		function people() {
			return [...rows.children].map((row) => ({
				full_name: row.querySelector('[data-field="full_name"]').value.trim(),
				email: row.querySelector('[data-field="email"]').value.trim(),
			}));
		}

		function renderSummary() {
			const list = form.querySelector("[data-wp-summary-people]");
			if (!list) return;
			list.replaceChildren(...people().map((p, i) => {
				const li = document.createElement("li");
				li.textContent = p.full_name || `Ticket ${i + 1}`;
				return li;
			}));
			const n = count();
			const total = gross * n;
			const tax = total - total / (1 + taxRate / 100);
			form.querySelector("[data-wp-summary-line]").textContent = `${n} × ${money.format(gross)}`;
			form.querySelector("[data-wp-summary-net]").textContent = money.format(total);
			form.querySelector("[data-wp-summary-tax]").textContent = money.format(tax);
			form.querySelector("[data-wp-summary-total]").textContent = money.format(total);
		}

		qty.addEventListener("input", renderRows);
		rows.addEventListener("input", renderSummary);
		// The first ticket holder fills the billing name and email unless they were changed by hand.
		rows.addEventListener("change", () => {
			const first = people()[0] || {};
			for (const [field, value] of [["billing_name", first.full_name], ["billing_email", first.email]]) {
				const input = form.elements[field];
				if (input && (!input.value || input.dataset.auto === "1")) {
					input.value = value || "";
					input.dataset.auto = "1";
				}
			}
		});
		["billing_name", "billing_email"].forEach((f) => form.elements[f] && form.elements[f].addEventListener("input", (e) => (e.target.dataset.auto = "0")));
		const toggle = form.querySelector("[data-wp-company-toggle]");
		if (toggle) {
			toggle.addEventListener("change", () => {
				companyBox.hidden = !toggle.checked;
				form.elements.company.required = toggle.checked;
			});
		}

		wireDialog(ticketDialog, "tickets", () => {
			status.textContent = "";
			status.classList.remove("wp-error");
			if (!rows.children.length) renderRows();
			setTimeout(() => qty.focus(), 0);
		});

		form.addEventListener("submit", async (event) => {
			event.preventDefault();
			status.classList.remove("wp-error");
			if (!form.checkValidity()) {
				status.classList.add("wp-error");
				status.textContent = status.dataset.invalid;
				form.reportValidity();
				return;
			}
			const body = new FormData();
			for (const name of ["event", "lang", "website"]) body.append(name, form.elements[name].value);
			body.append("qty", String(count()));
			body.append("attendees", JSON.stringify(people()));
			if (!free) {
				const v = (name) => (form.elements[name] ? form.elements[name].value.trim() : "");
				body.append("billing", JSON.stringify({
					full_name: v("billing_name"), email: v("billing_email"), phone: v("phone"),
					is_company: toggle && toggle.checked ? 1 : 0, company: v("company"), vat_id: v("vat_id"),
					address_line1: v("address_line1"), postcode: v("postcode"), city: v("city"), country: v("country"),
				}));
			}
			const consents = {};
			for (const name of ["terms", "privacy", "newsletter", "attendee_contact", "public_listing"]) {
				consents[name] = form.elements[name].checked ? 1 : 0;
			}
			body.append("consents", JSON.stringify(consents));
			submit.disabled = true;
			status.textContent = status.dataset.sending;
			try {
				const result = await post(form, body);
				form.querySelectorAll("fieldset, .wp-consents, [data-wp-ticket-actions]").forEach((el) => (el.hidden = true));
				const success = form.querySelector("[data-wp-ticket-success]");
				success.querySelector("[data-wp-ticket-reference]").textContent = result.reference || "";
				success.hidden = false;
			} catch (error) {
				submit.disabled = false;
				status.classList.add("wp-error");
				status.textContent = error.message || status.dataset.failed;
			}
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
