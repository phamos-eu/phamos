// Progressive enhancement for the Web Profile listing pages (phamos/phamos#1492).
// Without this script the pages still work: the filters are a plain GET form and paging uses
// ordinary links. With it: filters apply without a reload (URL kept in sync), more results load
// on scroll over the real ?page=n links, and the filters become a drawer on small screens.
// Frappe's standard language picker (navbar, Website Settings > Show Language Picker) on Web Profile
// pages: the language lives in the URL (/de/..., /en/...), so the picker offers the page's language
// versions (from its hreflang links) and opens the matching URL instead of only reloading.
// Side-by-side columns that stay in view while the other one scrolls (listing filters and results,
// the profile sidebar). A column taller than the window moves with the page until its end
// (scrolling down) or its start (scrolling up) is in view, then stays pinned; one that fits stays
// pinned at the top. The browser does the pinning: sticky with top and bottom limits
// (--wp-<name>-top / -bottom). When the scroll direction changes, the column's place in its grid
// area is set to where it is now, so it moves on from there instead of waiting or jumping.
// Scrolling down it hangs from the top of the area (margin above), scrolling up it stands on its
// bottom (margin below): a sticky element keeps its margins inside the area, so a margin on the side
// it moves towards would block it. A column that fills its area simply scrolls.
// columns: [{ selector, name, top, bottom (gaps to the window edges), before, after (resting
// margins, default 0 / 64 = the gap to the footer) }]; the CSS reads the variables.
function pinColumns(columns) {
	const style = document.documentElement.style;
	const set = (column, key, value) => {
		const prop = `--wp-${column.name}-${key}`;
		if (style.getPropertyValue(prop) !== value) style.setProperty(prop, value);
	};
	const element = (column) => {
		const el = document.querySelector(column.selector);
		return el && getComputedStyle(el).position === "sticky" ? el : null; // static on phones
	};
	const fits = (column, el) => el.offsetHeight + column.top + column.bottom <= window.innerHeight;
	const place = (column, align, before, after) => {
		set(column, "align", align);
		set(column, "before", before + "px");
		set(column, "after", after + "px");
	};
	for (const column of columns) {
		column.before = column.before || 0;
		column.after = column.after ?? 64;
	}
	// Limits follow the column's height (other filters, more results loaded, window resized).
	const measure = () => {
		for (const column of columns) {
			const el = element(column);
			if (!el) continue;
			const tall = !fits(column, el);
			set(column, "top", (tall ? window.innerHeight - el.offsetHeight - column.bottom : column.top) + "px");
			set(column, "bottom", tall ? window.innerHeight - el.offsetHeight - column.top + "px" : "auto");
			if (!tall) place(column, "start", column.before, column.after);
		}
	};
	let lastY = window.scrollY;
	let direction = 0;
	let frame = 0;
	const onScroll = () => {
		frame = 0;
		measure();
		const y = window.scrollY;
		const now = Math.sign(y - lastY);
		lastY = y;
		if (!now || now === direction) return;
		direction = now;
		for (const column of columns) {
			const el = element(column);
			if (!el || fits(column, el)) continue;
			const area = el.parentElement.getBoundingClientRect();
			const pad = getComputedStyle(el.parentElement);
			const rect = el.getBoundingClientRect();
			if (now > 0) {
				const above = Math.floor(rect.top - area.top - parseFloat(pad.paddingTop));
				place(column, "start", Math.max(column.before, above), column.after);
			} else {
				const below = Math.floor(area.bottom - parseFloat(pad.paddingBottom) - rect.bottom);
				place(column, "end", 0, Math.max(column.after, below));
			}
		}
	};
	window.addEventListener("scroll", () => { if (!frame) frame = requestAnimationFrame(onScroll); }, { passive: true });
	window.addEventListener("resize", measure);
	measure();
	return { measure };
}

// Profile pages: the sidebar (key people, facts, contact) stays in view next to the text.
if (document.querySelector(".wp-profile-aside")) {
	pinColumns([{ selector: ".wp-profile-aside", name: "aside", top: 24, bottom: 24, before: 12 }]);
}

// The visitor's language choice, read by Frappe for guests (frappe.translate) and by the banner below.
function rememberLanguage(lang) {
	const secure = location.protocol === "https:" ? "; secure" : "";
	document.cookie = `preferred_language=${lang}; path=/; max-age=${60 * 60 * 24 * 365}; samesite=lax${secure}`;
}

// Language banner (phamos/phamos#1498): a visitor whose browser prefers another language that this
// page exists in is offered that version once. "Continue" opens the same page in that language,
// "Stay" (or Esc) keeps this one; either choice is remembered in the preferred_language cookie and
// the banner does not come back. Never a redirect: crawlers and shared links always get the URL
// they asked for. It overlays the bottom of the window: at the top it would cover the navbar, and
// pushing the page down would move content the visitor may already see (the script runs late).
const BANNER_TEXTS = {
	de: { label: "Sprache", message: "Diese Seite gibt es auch auf Deutsch.", go: "Weiter auf Deutsch", stay: "Auf Deutsch bleiben" },
	en: { label: "Language", message: "This page is also available in English.", go: "Continue in English", stay: "Stay in English" },
};

function languageBanner(alternates, pageLang) {
	pageLang = pageLang.split("-")[0];
	if (/(^|;\s*)preferred_language=/.test(document.cookie)) return;  // already chosen, here or in the picker
	if (/bot|crawl|spider|slurp|facebookexternalhit|lighthouse/i.test(navigator.userAgent)) return;
	// Logged-in users get their language from their User record, not from the cookie.
	const user = (document.cookie.match(/(?:^|;\s*)user_id=([^;]*)/) || [])[1];
	if (user && decodeURIComponent(user) !== "Guest") return;
	// The visitor's first browser language we have a version of; none, or this page's, means no banner.
	let lang = null;
	for (const code of (navigator.languages || [navigator.language]).map((l) => l.toLowerCase().split("-")[0])) {
		if (code === pageLang) return;
		if (alternates[code] && BANNER_TEXTS[code]) {
			lang = code;
			break;
		}
	}
	if (!lang || !BANNER_TEXTS[pageLang]) return;

	// The offer is in the visitor's language, "stay" in the page's, so both readers understand theirs.
	const texts = BANNER_TEXTS[lang];
	const banner = document.createElement("div");
	banner.className = "wp-lang-banner";
	banner.setAttribute("role", "region");
	banner.setAttribute("aria-label", texts.label);
	banner.lang = lang;
	banner.innerHTML = `<p></p><div class="wp-lang-banner-actions">
		<a class="wp-button wp-button-sm wp-button-primary" data-wp-lang-go></a>
		<button type="button" class="wp-button wp-button-sm" data-wp-lang-stay></button></div>`;
	banner.querySelector("p").textContent = texts.message;
	const go = banner.querySelector("[data-wp-lang-go]");
	go.textContent = texts.go;
	go.href = alternates[lang];
	go.hreflang = lang;
	const stay = banner.querySelector("[data-wp-lang-stay]");
	stay.textContent = BANNER_TEXTS[pageLang].stay;
	stay.lang = pageLang;

	// Esc is also how the contact dialog and the filter drawer close; then it is not an answer here.
	const onKey = (event) => {
		if (event.key !== "Escape" || event.defaultPrevented) return;
		if (document.querySelector("dialog[open]") || document.documentElement.classList.contains("wp-filters-open")) return;
		close();
	};
	const close = () => {
		rememberLanguage(pageLang);
		banner.remove();
		document.removeEventListener("keydown", onKey);
	};
	go.addEventListener("click", () => rememberLanguage(lang));
	stay.addEventListener("click", close);
	document.addEventListener("keydown", onKey);
	document.body.prepend(banner);  // first in the tab order, although it is shown at the bottom
}

(function () {
	const alternates = {};
	for (const link of document.querySelectorAll('link[rel="alternate"][hreflang]')) {
		if (link.hreflang !== "x-default") alternates[link.hreflang] = link.href;
	}
	if (!Object.keys(alternates).length) return;  // only pages with language versions (profiles, Web Pages)
	const pageLang = document.documentElement.lang;

	// Runs before Frappe's own change handler, which would only set a cookie and reload.
	document.addEventListener("change", (event) => {
		const select = event.target.closest("#language-switcher select");
		if (!select || !alternates[select.value]) return;
		event.stopPropagation();
		rememberLanguage(select.value);
		window.location.href = alternates[select.value];
	}, true);

	languageBanner(alternates, pageLang);

	// Frappe fills the options asynchronously; keep only this page's languages, current one selected.
	const select = document.querySelector("#language-switcher select");
	if (!select) return;
	const tidy = () => {
		if (!select.options.length) return;
		for (const option of [...select.options]) {
			if (!alternates[option.value]) option.remove();
		}
		select.value = pageLang;
		document.documentElement.lang = pageLang;
	};
	new MutationObserver(tidy).observe(select, { childList: true });
	tidy();
})();

// Shared contact dialog (phamos.web_profile.contact.submit). Every contact button on a profile
// page opens the same <dialog>; the button's data attributes say whom the request is for.
(function () {
	const dialog = document.querySelector("[data-wp-contact-dialog]");
	if (!dialog || typeof dialog.showModal !== "function") return;
	const form = dialog.querySelector("[data-wp-contact]");
	const status = form.querySelector("[data-wp-contact-status]");
	const submit = form.querySelector("button[type=submit]");
	let opener = null;

	document.addEventListener("click", (event) => {
		const button = event.target.closest("[data-wp-contact-open]");
		if (!button) return;
		opener = button;
		// Buttons in Web Pages may only carry data-section="contact"; texts then come from the dialog.
		const defaults = dialog.dataset;
		const section = button.dataset.section || "contact";
		const slug = button.dataset.slug || "general";
		const title = button.dataset.title || defaults.defaultTitle;
		const intro = button.dataset.intro || defaults.defaultIntro;
		const consent = button.dataset.consent || defaults.defaultConsent;
		form.elements.section.value = section;
		form.elements.slug.value = slug;
		dialog.querySelector("[data-wp-dialog-title]").textContent = title;
		dialog.querySelector("[data-wp-dialog-intro]").textContent = intro;
		dialog.querySelector("[data-wp-dialog-consent]").textContent = consent;
		status.textContent = "";
		status.classList.remove("wp-error");
		submit.disabled = false;
		dialog.showModal();
		form.elements.sender_name.focus();
	});
	dialog.querySelector("[data-wp-dialog-close]").addEventListener("click", () => dialog.close());
	// Click on the backdrop (outside the form) closes the dialog.
	dialog.addEventListener("click", (event) => {
		if (event.target === dialog) dialog.close();
	});
	dialog.addEventListener("close", () => opener && opener.focus());

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
			const headers = { Accept: "application/json" };
			if (window.frappe && frappe.csrf_token) headers["X-Frappe-CSRF-Token"] = frappe.csrf_token;
			const response = await fetch(form.action, { method: "POST", body: new FormData(form), headers, credentials: "same-origin" });
			const data = await response.json().catch(() => ({}));
			if (!response.ok) throw new Error(serverMessage(data) || status.dataset.failed);
			const keep = { section: form.elements.section.value, slug: form.elements.slug.value, lang: form.elements.lang.value };
			form.reset();
			Object.entries(keep).forEach(([name, value]) => (form.elements[name].value = value));
			status.textContent = status.dataset.sent;
		} catch (error) {
			submit.disabled = false;
			status.classList.add("wp-error");
			status.textContent = error.message || status.dataset.failed;
		}
	});

	function serverMessage(data) {
		try {
			const messages = JSON.parse(data._server_messages || "[]").map((m) => JSON.parse(m).message);
			return messages.join(" ").replace(/<[^>]*>/g, "");
		} catch (e) {
			return "";
		}
	}
})();

(function () {
	const root = document.querySelector("[data-wp-listing]");
	if (!root) return;
	document.documentElement.classList.add("wp-js");

	const AUTO_LOADS = 3; // then a "Load more" button, so the footer stays reachable
	let autoLoads = 0;
	let controller = null;
	let observer = null;
	let searchTimer = null;

	const $ = (selector, scope = document) => scope.querySelector(selector);
	const form = () => $("[data-wp-form]");

	function formUrl() {
		// Defaults (status=current, sort=recommended) are left out so URLs stay short and canonical.
		const defaults = {};
		for (const el of document.querySelectorAll("[data-wp-default-for]")) {
			defaults[el.dataset.wpDefaultFor] = el.dataset.wpDefault;
		}
		const params = new URLSearchParams();
		for (const [key, value] of new FormData(form())) {
			if (value !== "" && defaults[key] !== value) params.append(key, value);
		}
		const query = params.toString();
		return form().getAttribute("action") + (query ? "?" + query : "");
	}

	async function fetchPage(url) {
		if (controller) controller.abort();
		controller = new AbortController();
		const response = await fetch(url, { signal: controller.signal, credentials: "same-origin" });
		if (!response.ok) throw new Error(response.status);
		return new DOMParser().parseFromString(await response.text(), "text/html");
	}

	// Swap results, filters and the header toggle for the server-rendered state of `url`.
	async function navigate(url, { push = true } = {}) {
		const results = $("[data-wp-results]");
		results.classList.add("wp-loading");
		try {
			const doc = await fetchPage(url);
			const search = $("[data-wp-search]");
			const hadFocus = document.activeElement === search;
			const caret = search ? search.selectionStart : null;

			results.replaceWith($("[data-wp-results]", doc));
			const scrollTop = ($(".wp-facet-scroll") || {}).scrollTop;
			$("[data-wp-sidebar]").replaceWith($("[data-wp-sidebar]", doc));
			const toggle = $("[data-wp-toggle]");
			if (toggle) toggle.replaceWith($("[data-wp-toggle]", doc));
			document.title = doc.title;

			const newSearch = $("[data-wp-search]");
			if (hadFocus && newSearch) {
				newSearch.focus();
				newSearch.setSelectionRange(caret, caret);
			}
			if (scrollTop && $(".wp-facet-scroll")) $(".wp-facet-scroll").scrollTop = scrollTop;
			if (push) history.pushState({ wp: true }, "", url);
			autoLoads = 0;
			bind();
			columns.measure(); // other filters and results, other heights
		} catch (error) {
			if (error.name !== "AbortError") window.location.href = url; // fall back to a full load
		} finally {
			const current = $("[data-wp-results]");
			if (current) current.classList.remove("wp-loading");
		}
	}

	// Append the next page's tiles; the URL follows so reload / share land on the same page.
	async function loadNext(link) {
		link.setAttribute("aria-busy", "true");
		try {
			const doc = await fetchPage(link.href);
			const grid = $("[data-wp-grid]");
			for (const item of doc.querySelectorAll("[data-wp-grid] > [data-wp-item]")) grid.append(item);
			$("[data-wp-pagination]").replaceWith($("[data-wp-pagination]", doc));
			history.replaceState({ wp: true }, "", link.href);
			columns.measure(); // more results, taller column
			bindPagination();
		} catch (error) {
			if (error.name !== "AbortError") window.location.href = link.href;
		}
	}

	function bindPagination() {
		if (observer) observer.disconnect();
		const pagination = $("[data-wp-pagination]");
		const next = $("[data-wp-next]");
		if (!pagination) return;
		// Scrolling replaces page-by-page navigation; keep the links for crawlers and no-JS.
		for (const el of pagination.querySelectorAll("[rel=prev], .wp-page-info")) el.hidden = true;
		if (!next) return;
		if (autoLoads >= AUTO_LOADS || !("IntersectionObserver" in window)) {
			next.textContent = next.dataset.wpLoadMoreLabel;
			next.addEventListener("click", (event) => {
				event.preventDefault();
				loadNext(next);
			});
			return;
		}
		observer = new IntersectionObserver(
			(entries) => {
				if (entries.some((entry) => entry.isIntersecting)) {
					observer.disconnect();
					autoLoads += 1;
					loadNext(next);
				}
			},
			{ rootMargin: "600px 0px" }
		);
		observer.observe(next);
	}

	function bind() {
		const f = form();
		f.addEventListener("submit", (event) => {
			event.preventDefault();
			navigate(formUrl());
		});
		for (const input of document.querySelectorAll("[data-wp-input], [data-wp-sort]")) {
			input.addEventListener("change", () => navigate(formUrl()));
		}
		const search = $("[data-wp-search]");
		if (search) {
			search.addEventListener("input", () => {
				clearTimeout(searchTimer);
				searchTimer = setTimeout(() => navigate(formUrl()), 300);
			});
		}
		for (const link of document.querySelectorAll("[data-wp-nav]")) {
			link.addEventListener("click", (event) => {
				event.preventDefault();
				navigate(link.href);
			});
		}
		for (const range of document.querySelectorAll("[data-wp-range]")) bindRange(range);
		const open = $("[data-wp-open-filters]");
		if (open) {
			open.addEventListener("click", () => {
				setDrawer(true);  // phones only; the button is hidden on desktop
			});
		}
		const close = $("[data-wp-close-filters]");
		if (close) close.addEventListener("click", () => setDrawer(false));
		bindPagination();
	}

	// Min/max slider: keep the two handles in order, show the values and the filled span while
	// dragging; the results update on release (the inputs' "change" event, bound above).
	function bindRange(range) {
		const min = Number(range.dataset.min), max = Number(range.dataset.max);
		const low = range.querySelector('[data-wp-range-input="low"]');
		const high = range.querySelector('[data-wp-range-input="high"]');
		const slider = range.querySelector(".wp-range-slider");
		const update = (moved) => {
			if (Number(low.value) > Number(high.value)) {
				if (moved === low) high.value = low.value;
				else low.value = high.value;
			}
			range.querySelector("[data-wp-range-low]").textContent = low.value;
			range.querySelector("[data-wp-range-high]").textContent = high.value;
			const pct = (v) => ((Number(v) - min) * 100) / (max - min);
			slider.style.setProperty("--low", pct(low.value) + "%");
			slider.style.setProperty("--high", pct(high.value) + "%");
			// Whichever handle was touched last stays on top, so it can always be grabbed again.
			low.style.zIndex = moved === low ? 3 : 2;
		};
		low.addEventListener("input", () => update(low));
		high.addEventListener("input", () => update(high));
	}

	const columns = pinColumns([
		{ selector: "[data-wp-sidebar]", name: "sidebar", top: 12, bottom: 12 },
		{ selector: "[data-wp-results]", name: "results", top: 0, bottom: 12 }, // search bar at the very top
	]);

	function setDrawer(open) {
		document.documentElement.classList.toggle("wp-filters-open", open);
		if (open) {
			const first = $("[data-wp-sidebar] input");
			if (first) first.focus();
		}
	}

	document.addEventListener("keydown", (event) => {
		if (event.key === "Escape") setDrawer(false);
	});
	document.addEventListener("click", (event) => {
		const sidebar = $("[data-wp-sidebar]");
		if (document.documentElement.classList.contains("wp-filters-open") && sidebar
			&& !sidebar.contains(event.target) && !event.target.closest("[data-wp-open-filters]")) {
			setDrawer(false);
		}
	});
	window.addEventListener("popstate", () => navigate(window.location.href, { push: false }));

	bind();
})();
