// Raven inside the cockpits (#1615): one Raven v3 channel in a same-origin iframe, without the rest
// of Raven. Spike #1613 settled the shape: the frame is at least 768px wide, so Raven renders its
// desktop layout (below 768px message actions are touch-only), and this CSS hides the channel
// list and the workspace rail. The guard keeps the frame on its channel and its threads; anything
// else opens in a real Raven window.
//
// The selectors follow Raven's markup (apps/web/src/components/layout/AppShell.tsx). Re-check
// them on every Raven upgrade (#1619). Below 768px (phones) Raven's mobile layout already shows
// only the channel, so the rules only apply from 768px on.

export const RAVEN_EMBED_STYLE_ID = "phamos-raven-embed"

export const RAVEN_EMBED_CSS = `
/* Thread pills ("3 replies") with new replies for the user (#1623): Raven does not mark them.
   Styled like Raven's own unread cues: the pill reads as unread (darker, semibold, like an unread
   channel in its sidebar) and carries Raven's red unread badge (PrimarySidebar's UnreadBadge:
   surface-red-6, ink-base text, ink-red-1 in dark mode). Raven's tokens follow its theme. */
a[data-phamos-unread] { color: var(--ink-gray-8) !important; font-weight: 600; }
a[data-phamos-unread]::after {
	content: attr(data-phamos-unread);
	display: inline-flex;
	align-items: center;
	height: 1rem;
	padding: 0 0.375rem;
	border-radius: 9999px;
	background: var(--surface-red-6);
	color: var(--ink-base);
	font-size: 10px;
	font-weight: 600;
	line-height: 1;
	white-space: nowrap;
}
.dark a[data-phamos-unread]::after { color: var(--ink-red-1); }
/* Raven warns above the composer that a mentioned non-member "won't be notified". In a record
   chat that is wrong: on sending, everyone mentioned who can read the record joins the chat and
   is assigned (#1620, #1784). That row (Raven's MentionWarningBanner, the one with the info
   icon) shows our sentence instead; the leave rows stay. */
[data-phamos-note] > span:last-child { display: none; }
[data-phamos-note]::after { content: attr(data-phamos-note); }
@media (min-width: 768px) {
	/* Channel list next to the chat */
	[class*="md:w-(--sidebar-width)"] { display: none !important; }
	/* Workspace rail (search, notifications, people …) left of the app */
	#root > .h-dvh > div:first-child:not(main) { display: none !important; }
}
`

const RAVEN_BASE = "/raven"
const HOME_GRACE_MS = 500

function decode(path) {
	try {
		return decodeURIComponent(path)
	} catch (e) {
		return path
	}
}

/**
 * Where a path inside the frame belongs:
 * - "channel": the embedded channel or one of its threads (stays in the frame)
 * - "home": Raven's own start pages, which its Back button leads to (closes the drawer)
 * - "raven": another Raven page (opens in a new Raven window)
 * - "outside": not Raven at all, e.g. a link card to a cockpit (opens in the cockpit)
 * @param {string} path pathname inside the frame, encoded or not
 * @param {string} channelPath "/raven/<workspace>/<channel>"
 */
export function classifyPath(path, channelPath) {
	const p = decode(path || "").replace(/\/+$/, "")
	const channel = decode(channelPath || "").replace(/\/+$/, "")
	if (channel && (p === channel || p.startsWith(`${channel}/thread/`))) return "channel"
	if (p !== RAVEN_BASE && !p.startsWith(`${RAVEN_BASE}/`)) return "outside"
	const workspace = channel.split("/").slice(0, 3).join("/") // "/raven/<workspace>"
	if (p === RAVEN_BASE || p === workspace) return "home"
	return "raven"
}

/** Add the embed CSS to the frame's document once. */
export function injectEmbedStyle(doc) {
	if (!doc?.head || doc.getElementById(RAVEN_EMBED_STYLE_ID)) return
	const style = doc.createElement("style")
	style.id = RAVEN_EMBED_STYLE_ID
	style.textContent = RAVEN_EMBED_CSS
	doc.head.appendChild(style)
}

/**
 * Keep the frame on its channel. Raven routes with history.pushState/replaceState (react-router)
 * and its Back button uses history.back(), so wrapping both and listening to popstate sees every
 * move. A move away is undone and handed to `onLeave(kind, href)`; opening one of the channel's
 * threads (from the hint or Raven's own pill) calls `onThread(threadId)`.
 * Link clicks to non-Raven pages are caught before the frame navigates.
 * @returns {() => void} removes the guard
 */
export function installGuard(win, channelPath, onLeave, onThread = null) {
	const history = win.history
	const originals = { pushState: history.pushState, replaceState: history.replaceState }
	let lastAllowed = win.location.pathname + win.location.search
	// Raven's router (react-router) keeps its own place in history.state ({ key, idx }) and has
	// already switched views by the time it pushes or replaces the address.
	let lastAllowedState = history.state
	let homeTimer = null
	// Set while the frame is on its way back to the channel: Raven may move on again before it
	// gets there (two pushes, a redirect), which must not open two windows (#1794).
	let leaving = false

	function leave(kind, how, pushedKey) {
		if (leaving) return
		leaving = true
		const href = win.location.href
		if (how === "pushState" && pushedKey && history.state?.key === pushedKey) {
			// A real Back to the channel's entry: the router sees its index go down and renders the
			// channel again. Rewriting the address with the new entry's state (same index) left the
			// router on the other page, e.g. a DM opened from a profile card. Only while that
			// pushed entry is still the current one, so Back never steps past the frame's own.
			history.back()
		} else {
			originals.replaceState.call(history, lastAllowedState, "", lastAllowed)
			win.dispatchEvent(new win.PopStateEvent("popstate", { state: history.state }))
		}
		// Back or Forward through the frame's history is no request to open anything: it only
		// closes the drawer when it lands on Raven's start page (#1794).
		if (how === "popstate" && kind !== "home") return
		onLeave(kind, href)
	}

	function check(how) {
		win.clearTimeout(homeTimer)
		const kind = classifyPath(win.location.pathname, channelPath)
		if (kind === "channel") {
			leaving = false
			const before = lastAllowed
			lastAllowed = win.location.pathname + win.location.search
			lastAllowedState = history.state
			const thread = threadIdFromHref(win.location.pathname)
			if (thread && thread !== threadIdFromHref(before)) onThread?.(thread)
			return
		}
		const pushedKey = how === "pushState" ? history.state?.key : null
		// Raven's mobile layout repairs a cold start by replacing the entry with the workspace
		// home and pushing the channel back on top (hooks/useMobileBack.ts). Only Back (popstate)
		// or a home page that is still shown a moment later means the user left the chat.
		if (kind === "home" && how !== "popstate") {
			homeTimer = win.setTimeout(() => {
				if (classifyPath(win.location.pathname, channelPath) === "home") leave("home", how, pushedKey)
			}, HOME_GRACE_MS)
			return
		}
		leave(kind, how, pushedKey)
	}

	const onPopState = () => check("popstate")

	for (const method of ["pushState", "replaceState"]) {
		history[method] = function (...args) {
			const result = originals[method].apply(history, args)
			check(method)
			return result
		}
	}
	win.addEventListener("popstate", onPopState)

	function onClick(event) {
		const anchor = event.target?.closest?.("a[href]")
		if (!anchor || event.defaultPrevented) return
		// Cmd/Ctrl/Shift-click: the browser opens its own tab or window, as the user asked.
		if (event.metaKey || event.ctrlKey || event.shiftKey) return
		const url = new URL(anchor.href, win.location.href)
		if (url.origin !== win.location.origin) return // external links: Raven opens them in a new tab
		const kind = classifyPath(url.pathname, channelPath)
		if (kind !== "outside") return
		event.preventDefault()
		event.stopPropagation()
		onLeave(kind, url.href)
	}
	win.document.addEventListener("click", onClick, true)

	return () => {
		history.pushState = originals.pushState
		history.replaceState = originals.replaceState
		win.clearTimeout(homeTimer)
		win.removeEventListener("popstate", onPopState)
		win.document.removeEventListener("click", onClick, true)
	}
}

/**
 * Move the running Raven to `path` (its channel, a thread, a message) the way its router does
 * it: react-router keeps { usr, key, idx } in history.state and reads the index on popstate.
 * Without that shape Raven's mobile layout thinks the entry is the first one and replaces it
 * with its threads page (useMobileBack), and Back counts wrong (#1794).
 * `replace` switches the frame to another record's chat without a new history entry, so the
 * browser's Back leaves the page instead of stepping through earlier records' chats.
 * Goes through History.prototype, so a guard on this window does not judge the move itself.
 */
export function routeFrame(win, path, { replace = false } = {}) {
	const idx = Number.isInteger(win.history.state?.idx) ? win.history.state.idx : 0
	const state = { usr: null, key: Math.random().toString(36).slice(2, 10), idx: replace ? idx : idx + 1 }
	win.History.prototype[replace ? "replaceState" : "pushState"].call(win.history, state, "", path)
	win.dispatchEvent(new win.PopStateEvent("popstate", { state }))
}

const THREAD_ROUTE = /\/thread\/([^/?#]+)/

/** The thread id a Raven thread link points to, or "". */
export function threadIdFromHref(href) {
	const match = THREAD_ROUTE.exec(href || "")
	return match ? decode(match[1]) : ""
}

/**
 * Mark Raven's thread pills that have new replies (#1623): `data-phamos-unread` carries the
 * label the CSS shows ("2 new"). Pills without new replies lose the mark.
 * @param {Document} doc the frame's document
 * @param {Object<string, string>} labels thread id → label, for threads with new replies
 */
export function markUnreadThreads(doc, labels) {
	for (const link of doc.querySelectorAll('a[href*="/thread/"]')) {
		const label = labels[threadIdFromHref(link.getAttribute("href"))]
		if (label) {
			if (link.getAttribute("data-phamos-unread") !== label) link.setAttribute("data-phamos-unread", label)
		} else if (link.hasAttribute("data-phamos-unread")) {
			link.removeAttribute("data-phamos-unread")
		}
	}
}

/**
 * Replace Raven's "isn't in this channel" mention warning with `note` (#1784): the row of its
 * amber MentionWarningBanner that carries the info icon. Rows about leave keep Raven's text.
 * @param {Document} doc the frame's document
 * @param {string} note the sentence to show, or "" to leave Raven's warning alone
 */
export function markMentionNotes(doc, note) {
	for (const icon of doc.querySelectorAll(".bg-surface-amber-2 > div > span > svg.lucide-info")) {
		const row = icon.parentElement.parentElement
		if (!note) row.removeAttribute("data-phamos-note")
		else if (row.getAttribute("data-phamos-note") !== note) row.setAttribute("data-phamos-note", note)
	}
}

/**
 * Keep the marks while Raven renders messages (its list renders as you scroll), and the mention
 * note while the composer's warning comes and goes. `getLabels` and `getMentionNote` are read
 * on every pass, so callers just change what it returns and call the returned
 * `refresh`.
 * @returns {{ refresh: () => void, stop: () => void }}
 */
export function watchThreadMarks(doc, getLabels, getMentionNote = () => "") {
	let scheduled = false
	const win = doc.defaultView
	const run = () => {
		scheduled = false
		markUnreadThreads(doc, getLabels())
		markMentionNotes(doc, getMentionNote())
	}
	const schedule = () => {
		if (scheduled) return
		scheduled = true
		win.requestAnimationFrame(run)
	}
	const observer = new win.MutationObserver(schedule)
	observer.observe(doc.body, { childList: true, subtree: true })
	schedule()
	return { refresh: schedule, stop: () => observer.disconnect() }
}
