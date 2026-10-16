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

	// --- tickets: three steps, then the optional questions ----------------------------------------------
	const ticketDialog = document.querySelector("[data-wp-ticket-dialog]");
	if (ticketDialog) {
		const form = ticketDialog.querySelector("[data-wp-ticket-form]");
		const $ = (selector) => form.querySelector(selector);
		const steps = [...form.querySelectorAll("[data-wp-step]")];
		const labels = [...form.querySelectorAll("[data-wp-step-label]")];
		const qty = $("[data-wp-qty]");
		const attends = $("[data-wp-attends]");
		const companions = $("[data-wp-companions]");
		const template = $("[data-wp-companion-row]");
		const status = $("[data-wp-ticket-status]");
		const back = $("[data-wp-back]");
		const next = $("[data-wp-next]");
		const submit = $("[data-wp-submit]");
		const toggle = $("[data-wp-company-toggle]");
		const free = form.dataset.free === "1";
		const gross = parseFloat(form.dataset.gross || "0");
		const taxRate = parseFloat(form.dataset.taxRate || "0");
		const max = parseInt(form.dataset.max || "10", 10);
		const money = new Intl.NumberFormat(form.dataset.lang === "de" ? "de-DE" : "en-GB",
			{ style: "currency", currency: form.dataset.currency || "EUR" });
		let current = 0;
		let order = null; // {reference, token} after a successful order

		const count = () => Math.min(Math.max(parseInt(qty.value || "1", 10) || 1, 1), max);
		const value = (name) => (form.elements[name] ? String(form.elements[name].value || "").trim() : "");

		function renderCompanions() {
			// Ticket holders besides the contact (all of them when the contact does not attend).
			const wanted = count() - (attends.checked ? 1 : 0);
			while (companions.children.length < wanted) companions.appendChild(template.content.firstElementChild.cloneNode(true));
			while (companions.children.length > wanted) companions.lastElementChild.remove();
			[...companions.children].forEach((row, i) => {
				row.querySelector("[data-wp-companion-label]").textContent = `${template.content.querySelector("[data-wp-companion-label]").textContent} ${i + (attends.checked ? 2 : 1)}`;
			});
			$("[data-wp-companions-block]").hidden = wanted < 1;
		}

		function holders() {
			const list = attends.checked ? [{ full_name: value("contact_name"), email: value("contact_email") }] : [];
			for (const row of companions.children) {
				list.push({
					full_name: row.querySelector('[data-field="full_name"]').value.trim(),
					email: row.querySelector('[data-field="email"]').value.trim(),
				});
			}
			return list;
		}

		function show(index) {
			current = index;
			steps.forEach((step, i) => (step.hidden = i !== index));
			labels.forEach((label, i) => {
				label.toggleAttribute("aria-current", i === index);
				label.classList.toggle("wp-step-done", i < index);
			});
			back.hidden = index === 0;
			next.hidden = index === steps.length - 1;
			submit.hidden = index !== steps.length - 1;
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

		function renderSummary() {
			const people = holders();
			$("[data-wp-summary-people]").replaceChildren(...people.map((p) => {
				const li = document.createElement("li");
				li.textContent = p.email && p.email !== value("contact_email") ? `${p.full_name} (${p.email})` : p.full_name;
				return li;
			}));
			$("[data-wp-summary-email]").textContent = value("contact_email");
			if (free) return;
			const lines = [value("is_company") && toggle.checked ? value("company") : "", value("billing_name"),
				value("address_line1"), `${value("postcode")} ${value("city")}`, form.elements.country.selectedOptions[0]?.textContent || "",
				value("vat_id") && toggle.checked ? value("vat_id") : ""].filter(Boolean);
			$("[data-wp-summary-billing]").replaceChildren(...lines.flatMap((line, i) => (i ? [document.createElement("br"), line] : [line])));
			const n = people.length;
			const total = gross * n;
			const title = form.dataset.priceTitle ? ` (${form.dataset.priceTitle})` : "";
			$("[data-wp-summary-line]").textContent = `${n} × ${money.format(gross)}${title}`;
			$("[data-wp-summary-amount]").textContent = money.format(total);
			$("[data-wp-summary-tax]").textContent = money.format(total - total / (1 + taxRate / 100));
			$("[data-wp-summary-total]").textContent = money.format(total);
		}

		qty.addEventListener("input", renderCompanions);
		attends.addEventListener("change", renderCompanions);
		if (toggle) {
			toggle.addEventListener("change", () => {
				$("[data-wp-company]").hidden = !toggle.checked;
				form.elements.company.required = toggle.checked;
			});
		}
		next.addEventListener("click", () => {
			if (!valid(steps[current])) return;
			if (current === 0 && !free) {
				// The billing step starts with the contact's name and email.
				for (const [field, source] of [["billing_name", "contact_name"], ["billing_email", "contact_email"]]) {
					if (!value(field)) form.elements[field].value = value(source);
				}
			}
			show(current + 1);
		});
		back.addEventListener("click", () => show(current - 1));
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
			if (order) return; // keep the thank-you panel after an order
			renderCompanions();
			show(0);
		});

		form.addEventListener("submit", async (event) => {
			event.preventDefault();
			if (current !== steps.length - 1) return next.click();
			const people = holders();
			const body = new FormData();
			for (const name of ["event", "lang", "website"]) body.append(name, form.elements[name].value);
			body.append("contact", JSON.stringify({ full_name: value("contact_name"), email: value("contact_email"), phone: value("phone") }));
			body.append("attends", attends.checked ? "1" : "0");
			body.append("companions", JSON.stringify(people.slice(attends.checked ? 1 : 0)));
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
			status.classList.remove("wp-error");
			status.textContent = status.dataset.sending;
			try {
				const result = await post(form, body);
				order = { reference: result.reference, token: result.token };
				steps.forEach((step) => (step.hidden = true));
				$("[data-wp-steps]").hidden = true;
				$("[data-wp-ticket-actions]").hidden = true;
				const success = $("[data-wp-ticket-success]");
				success.querySelector("[data-wp-ticket-reference]").textContent = result.reference || "";
				success.querySelector("[data-wp-ticket-email]").textContent = result.tickets_to || value("contact_email");
				success.hidden = false;
			} catch (error) {
				submit.disabled = false;
				back.disabled = false;
				status.classList.add("wp-error");
				status.textContent = error.message || status.dataset.failed;
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
			try {
				const result = await post({ action: form.dataset.consentAction }, body);
				consentStatus.classList.remove("wp-error");
				consentStatus.textContent = result.status === "confirmation_sent" ? consentStatus.dataset.optin : consentStatus.dataset.saved;
			} catch (error) {
				button.disabled = false;
				consentStatus.classList.add("wp-error");
				consentStatus.textContent = error.message || consentStatus.dataset.failed;
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
