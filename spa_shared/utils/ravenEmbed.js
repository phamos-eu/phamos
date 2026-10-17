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
 * move. A move away is undone and handed to `onLeave(kind, href)`.
 * Link clicks to non-Raven pages are caught before the frame navigates.
 * @returns {() => void} removes the guard
 */
export function installGuard(win, channelPath, onLeave) {
	const history = win.history
	const originals = { pushState: history.pushState, replaceState: history.replaceState }
	let lastAllowed = win.location.pathname + win.location.search
	let homeTimer = null

	function leave(kind) {
		const href = win.location.href
		originals.replaceState.call(history, history.state, "", lastAllowed)
		win.dispatchEvent(new win.PopStateEvent("popstate", { state: history.state }))
		onLeave(kind, href)
	}

	function check(how) {
		win.clearTimeout(homeTimer)
		const kind = classifyPath(win.location.pathname, channelPath)
		if (kind === "channel") {
			lastAllowed = win.location.pathname + win.location.search
			return
		}
		// Raven's mobile layout repairs a cold start by replacing the entry with the workspace
		// home and pushing the channel back on top (hooks/useMobileBack.ts). Only Back (popstate)
		// or a home page that is still shown a moment later means the user left the chat.
		if (kind === "home" && how !== "popstate") {
			homeTimer = win.setTimeout(() => {
				if (classifyPath(win.location.pathname, channelPath) === "home") leave("home")
			}, HOME_GRACE_MS)
			return
		}
		leave(kind)
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
