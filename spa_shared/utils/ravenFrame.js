// One Raven frame per cockpit page (#1796). Raven takes about a second to boot, and an iframe
// reloads whenever it is moved in the DOM, so a frame inside each chat panel booted Raven again
// for every Issue opened from the list. This frame lives in <body> for the whole page and is laid
// over the panel that currently uses it (its "slot"); switching chats only reroutes Raven.
//
// Fixed position, so it paints in the page's top stacking context: each panel says how high
// (zIndex). In the Issue column that is 1, above the column it covers and below frappe-ui's
// dialogs (z-10) and popovers; over the chat overlay (z-40) it is 41. While no panel uses it, it
// stays hidden at its last size, so Raven keeps its layout, and parks (PARKING_PATH).

import { routeFrame } from "@spa/utils/ravenEmbed.js"

/**
 * Where the frame waits while no chat shows it: a hidden frame still showing a chat would mark
 * that chat's new messages as read. Not Raven's start page: on the desktop layout that reopens
 * the last channel. "Scheduled messages" is a plain page of its own that loads no chat.
 */
export const PARKING_PATH = "/raven/scheduled-messages"

let frame = null
let loaded = false
/** The panel using the frame: { slot, onLoad } */
let owner = null
let rafId = 0
let lastRect = ""

function createFrame() {
	frame = document.createElement("iframe")
	frame.setAttribute("data-phamos-raven-frame", "")
	Object.assign(frame.style, {
		position: "fixed",
		left: "0px",
		top: "0px",
		width: "768px",
		height: "600px",
		border: "0",
		zIndex: "1",
		visibility: "hidden",
		pointerEvents: "none",
	})
	// Every load, including Raven reloading itself, goes to the panel using the frame. Without
	// one (its chat closed before Raven finished booting), Raven must not stay on that chat.
	frame.addEventListener("load", () => {
		loaded = true
		if (owner) owner.onLoad()
		else park()
	})
	document.body.appendChild(frame)
}

// Move the hidden Raven off any chat. Never throws: a Raven that is not reachable stays put.
function park() {
	try {
		const win = frame.contentWindow
		if (win.location.pathname !== PARKING_PATH) routeFrame(win, PARKING_PATH, { replace: true })
	} catch (e) {
		// not loaded yet or reloading: its load event parks it
	}
}

function setHidden() {
	frame.style.visibility = "hidden"
	frame.style.pointerEvents = "none"
	lastRect = ""
}

// Follow the slot every animation frame while a panel uses the frame: layout changes (sidebar,
// thread hint, the overlay sliding in) move it without resizing it, which a ResizeObserver misses.
function follow() {
	if (!owner) return
	const rect = owner.slot.isConnected ? owner.slot.getBoundingClientRect() : null
	if (!rect || !rect.width || !rect.height) {
		if (lastRect) setHidden()
	} else {
		const key = `${rect.left},${rect.top},${rect.width},${rect.height}`
		if (key !== lastRect) {
			lastRect = key
			Object.assign(frame.style, {
				left: `${rect.left}px`,
				top: `${rect.top}px`,
				width: `${rect.width}px`,
				height: `${rect.height}px`,
				visibility: "visible",
				pointerEvents: "auto",
			})
		}
	}
	rafId = requestAnimationFrame(follow)
}

/**
 * Lay the frame over `slot` for a panel. The first panel boots Raven at `url`; later ones get the
 * running Raven and route it themselves. `onLoad` runs on each load while the panel holds it.
 * @returns {{ frame: HTMLIFrameElement, loaded: boolean }}
 */
export function acquireRavenFrame({ slot, url, title, zIndex = 1, onLoad }) {
	if (!frame) createFrame()
	cancelAnimationFrame(rafId)
	owner = { slot, onLoad }
	frame.title = title || ""
	frame.style.zIndex = String(zIndex)
	if (!frame.getAttribute("src")) frame.src = url
	lastRect = ""
	follow()
	return { frame, loaded }
}

/**
 * Boot Raven ahead of the first chat, parked and hidden, so that chat opens without the wait
 * (#1796). Call it once the page is idle and has chats; it does nothing when Raven runs already.
 */
export function prewarmRavenFrame() {
	if (frame) return
	createFrame()
	frame.src = PARKING_PATH
}

/** The panel with this slot moved between column and overlay: put the frame at its new height. */
export function setRavenFrameLayer(slot, zIndex) {
	if (owner?.slot === slot) frame.style.zIndex = String(zIndex)
}

/**
 * The panel with this slot no longer shows the frame: hide it and park Raven. A panel that lost
 * the frame to another one changes nothing.
 */
export function releaseRavenFrame(slot) {
	if (!owner || owner.slot !== slot) return
	owner = null
	cancelAnimationFrame(rafId)
	setHidden()
	if (loaded) park()
}

/** The running Raven's window, or null before the first panel loaded it. */
export function ravenFrameWindow() {
	return loaded ? frame?.contentWindow || null : null
}
