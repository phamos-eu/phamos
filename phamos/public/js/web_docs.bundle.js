// Documentation pages /de/dokumentation, /en/documentation (phamos/phamos#2045).
// Only enhances: without JavaScript the pages work, the contents stay open and the buttons hidden.
//   - book contents beside a page: fold away, remembered in this browser (folded by default on phones)
//   - "On this page": the heading being read is highlighted
//   - floating buttons: back to the top, next heading / chapter below the current position
//   - book view: expand / collapse all chapters; a #chapter link opens its chapter
//   - search fields: suggestions while typing (phamos/phamos#2046); the form works without them

(() => {
	const NAV_KEY = "wp-docs-nav";
	const phone = () => matchMedia("(max-width: 860px)").matches;
	const smooth = () => (matchMedia("(prefers-reduced-motion: reduce)").matches ? "auto" : "smooth");

	function store(value) {
		try {
			localStorage.setItem(NAV_KEY, value);
		} catch (e) {
			// private window or blocked storage: the choice just isn't remembered
		}
	}

	function setupNav() {
		const layout = document.querySelector("[data-wp-docs-layout]");
		const toggle = document.querySelector("[data-wp-docs-nav-toggle]");
		if (!layout || !toggle) return;
		if (phone()) layout.classList.add("wp-docs-nav-closed"); // the text comes first on phones
		const sync = () => {
			const closed = layout.classList.contains("wp-docs-nav-closed");
			const label = closed ? toggle.dataset.labelShow : toggle.dataset.labelHide;
			toggle.setAttribute("aria-expanded", String(!closed));
			toggle.setAttribute("title", label);
			toggle.setAttribute("aria-label", label);
		};
		toggle.hidden = false;
		sync();
		toggle.addEventListener("click", () => {
			layout.classList.toggle("wp-docs-nav-closed");
			if (!phone()) store(layout.classList.contains("wp-docs-nav-closed") ? "closed" : "open");
			sync();
		});
		// keep the current page in view inside a long contents list; only the list scrolls, never the
		// window (scrollIntoView would move the page away from a #heading link)
		const nav = layout.querySelector(".wp-docs-nav");
		const current = layout.querySelector('.wp-docs-nav [aria-current="page"]');
		if (nav && current && !phone()) {
			const offset = current.getBoundingClientRect().top - nav.getBoundingClientRect().top;
			nav.scrollTop += offset - nav.clientHeight / 2;
		}
	}

	// Calls ``fn`` at most once per frame while scrolling.
	function onScroll(fn) {
		let queued = false;
		window.addEventListener(
			"scroll",
			() => {
				if (queued) return;
				queued = true;
				requestAnimationFrame(() => {
					queued = false;
					fn();
				});
			},
			{ passive: true }
		);
		fn();
	}

	// The last element above the upper third of the window is the one being read.
	function currentOf(elements) {
		let current = null;
		for (const el of elements) if (el.getBoundingClientRect().top <= window.innerHeight / 3) current = el;
		return current;
	}

	function setupOnThisPage() {
		const links = [...document.querySelectorAll("[data-wp-docs-onpage]")];
		const headings = links.map((a) => document.getElementById(a.dataset.wpDocsOnpage)).filter(Boolean);
		if (!headings.length) return;
		onScroll(() => {
			const id = (currentOf(headings) || headings[0]).id;
			links.forEach((a) => a.classList.toggle("is-current", a.dataset.wpDocsOnpage === id));
		});
	}

	function openTarget(el) {
		const details = el && (el.tagName === "DETAILS" ? el : el.closest("details"));
		if (details) details.open = true;
	}

	function setupJump() {
		const box = document.querySelector("[data-wp-docs-jump]");
		if (!box) return;
		const top = box.querySelector("[data-wp-docs-top]");
		const next = box.querySelector("[data-wp-docs-next]");
		const selector = next.dataset.wpDocsNext;
		const scope = document.querySelector("[data-wp-docs-content]") || document;
		const targets = () => [...scope.querySelectorAll(selector)].filter((el) => el.offsetParent !== null);
		const offset = 24;
		// Where the window must scroll to show ``el`` at the top. A smooth scroll can stop a few pixels
		// short, so a target counts as "next" only when it is clearly below the current position.
		const scrollTargetOf = (el) => window.scrollY + el.getBoundingClientRect().top - offset;
		const nextTarget = () => targets().find((el) => scrollTargetOf(el) > window.scrollY + 8);

		box.hidden = false;
		const update = () => {
			top.classList.toggle("is-hidden", window.scrollY < 400);
			next.classList.toggle("is-hidden", !nextTarget());
		};
		top.addEventListener("click", () => window.scrollTo({ top: 0, behavior: smooth() }));
		next.addEventListener("click", () => {
			const target = nextTarget();
			if (!target) return;
			openTarget(target);
			window.scrollTo({ top: scrollTargetOf(target), behavior: smooth() });
		});
		onScroll(update);
		window.addEventListener("resize", update);
		document.addEventListener("toggle", update, true);
	}

	function setupChapters() {
		const chapters = [...document.querySelectorAll("[data-wp-docs-chapter]")];
		if (!chapters.length) return;
		const toolbar = document.querySelector("[data-wp-docs-toolbar]");
		if (toolbar) {
			toolbar.hidden = false;
			toolbar.querySelector("[data-wp-docs-expand]").addEventListener("click", () => chapters.forEach((d) => (d.open = true)));
			toolbar.querySelector("[data-wp-docs-collapse]").addEventListener("click", () => chapters.forEach((d) => (d.open = false)));
		}
		const openHash = () => {
			let id = location.hash.slice(1);
			try {
				id = decodeURIComponent(id);
			} catch (e) {
				// a malformed "#%E0%A4" stays as it is instead of stopping the page's other buttons
			}
			const el = id && document.getElementById(id);
			if (el) {
				openTarget(el);
				el.scrollIntoView({ block: "start" });
			}
		};
		window.addEventListener("hashchange", openHash);
		openHash();
		// the chapter index marks the chapter the reader is in
		const index = [...document.querySelectorAll("[data-wp-docs-index]")];
		if (index.length) {
			onScroll(() => {
				const current = currentOf(chapters);
				index.forEach((a) => a.classList.toggle("is-current", !!current && a.dataset.wpDocsIndex === current.id));
			});
		}
	}

	function setupSearch(form) {
		const input = form.querySelector("[data-wp-docs-search-input]");
		const list = form.querySelector("[data-wp-docs-suggest]");
		const book = form.querySelector("[data-wp-docs-search-book]");
		if (!input || !list) return;
		let timer = null;
		let request = 0;
		let active = -1;

		const items = () => [...list.querySelectorAll("a")];
		const close = () => {
			list.hidden = true;
			list.replaceChildren();
			active = -1;
			input.setAttribute("aria-expanded", "false");
		};
		const highlight = (i) => {
			const links = items();
			active = (i + links.length) % links.length;
			links.forEach((a, n) => a.setAttribute("aria-selected", String(n === active)));
		};
		const render = (rows) => {
			list.replaceChildren();
			for (const row of rows) {
				// textContent only: titles come from BookStack
				const li = document.createElement("li");
				const a = document.createElement("a");
				a.href = row.url;
				a.setAttribute("role", "option");
				const title = document.createElement("span");
				title.className = "wp-docs-suggest-title";
				title.textContent = row.title;
				const sub = document.createElement("span");
				sub.className = "wp-docs-suggest-sub";
				sub.textContent = row.subtitle || "";
				a.append(title, sub);
				li.append(a);
				list.append(li);
			}
			list.hidden = !rows.length;
			input.setAttribute("aria-expanded", String(!!rows.length));
			active = -1;
		};
		const load = async () => {
			const q = input.value.trim();
			if (q.length < 2) return close();
			const params = new URLSearchParams({ q, lang: form.dataset.lang || "de" });
			if (book && book.checked) params.set("book", book.value);
			const mine = ++request;
			try {
				const response = await fetch(`/api/method/phamos.web_profile.docs_search.suggest?${params}`, {
					headers: { Accept: "application/json" },
				});
				if (!response.ok || mine !== request) return;
				render((await response.json()).message || []);
			} catch (e) {
				// offline or rate limited: the form still submits to the results page
			}
		};

		input.setAttribute("aria-autocomplete", "list");
		input.setAttribute("aria-expanded", "false");
		input.addEventListener("input", () => {
			clearTimeout(timer);
			timer = setTimeout(load, 200);
		});
		if (book) book.addEventListener("change", load);
		input.addEventListener("keydown", (event) => {
			const links = items();
			if (event.key === "ArrowDown" && links.length) {
				event.preventDefault();
				highlight(active + 1);
			} else if (event.key === "ArrowUp" && links.length) {
				event.preventDefault();
				highlight(active - 1);
			} else if (event.key === "Enter" && active >= 0 && links[active]) {
				event.preventDefault();
				window.location.href = links[active].href;
			} else if (event.key === "Escape") {
				close();
			}
		});
		document.addEventListener("click", (event) => {
			if (!form.contains(event.target)) close();
		});
	}

	// Wide tables (#2045): like the cockpits' "More below" (spa_shared ScrollHint, #1922), turned
	// sideways: a fade at each clipped edge and a "More to the right" pill that scrolls on.
	function setupTables() {
		const content = document.querySelector("[data-wp-docs-content]");
		const boxes = [...document.querySelectorAll("[data-wp-docs-table]")];
		if (!content || !boxes.length) return;
		const label = content.dataset.labelMoreRight || "More to the right";
		const title = content.dataset.labelScrollRest || label;
		const tolerance = 2; // as spa_shared/utils/scrollOverflow.js: rounding leaves no hint at the end

		for (const box of boxes) {
			const scroller = box.querySelector(".wp-docs-table-scroll");
			if (!scroller) continue;
			const left = document.createElement("div");
			left.className = "wp-docs-table-fade wp-docs-table-fade-left";
			left.setAttribute("aria-hidden", "true");
			const right = document.createElement("div");
			right.className = "wp-docs-table-fade wp-docs-table-fade-right";
			const pill = document.createElement("button");
			pill.type = "button";
			pill.className = "wp-docs-table-more";
			pill.title = title;
			pill.innerHTML = '<svg viewBox="0 0 24 24" aria-hidden="true" focusable="false"><path d="M9 6l6 6-6 6"/></svg>';
			pill.prepend(document.createTextNode(label));
			pill.addEventListener("mousedown", (event) => event.preventDefault());
			pill.addEventListener("click", () =>
				scroller.scrollBy({ left: Math.round(scroller.clientWidth * 0.8), behavior: smooth() })
			);
			right.append(pill);
			box.append(left, right);

			let frame = 0;
			const measure = () => {
				frame = 0;
				const { scrollLeft, clientWidth, scrollWidth } = scroller;
				box.classList.toggle("is-clipped-left", scrollLeft > tolerance);
				box.classList.toggle("is-clipped-right", scrollLeft + clientWidth < scrollWidth - tolerance);
			};
			const measureSoon = () => {
				if (!frame) frame = requestAnimationFrame(measure);
			};
			scroller.addEventListener("scroll", measureSoon, { passive: true });
			if ("ResizeObserver" in window) {
				// the box narrows with the window or the folded contents; images in cells load late
				const observer = new ResizeObserver(measureSoon);
				observer.observe(scroller);
				const table = scroller.querySelector("table");
				if (table) observer.observe(table);
			} else {
				window.addEventListener("resize", measureSoon);
			}
			measure();
		}
	}

	function init() {
		document.querySelectorAll("[data-wp-docs-search]").forEach(setupSearch);
		setupTables();
		setupNav();
		setupOnThisPage();
		setupChapters();
		setupJump();
	}

	if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", init);
	else init();
})();
