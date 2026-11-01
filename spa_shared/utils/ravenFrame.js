// One Raven frame per cockpit page (#1796). Raven takes about a second to boot, and an iframe
// reloads whenever it is moved in the DOM, so a frame inside each chat panel booted Raven again
// for every Issue opened from the list. This frame lives in <body> for the whole page and is laid
// over the panel that currently uses it (its "slot"); switching chats only reroutes Raven.
//
// Fixed position, z-index 41: above the chat overlay (z-40), below dialogs and popovers (z-50 and
// up). While no panel uses it, it stays hidden at its last size, so Raven keeps its layout.

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
		zIndex: "41",
		visibility: "hidden",
		pointerEvents: "none",
	})
	// Every load, including Raven reloading itself, goes to the panel using the frame.
	frame.addEventListener("load", () => {
		loaded = true
		owner?.onLoad()
	})
	document.body.appendChild(frame)
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
export function acquireRavenFrame({ slot, url, title, onLoad }) {
	if (!frame) createFrame()
	cancelAnimationFrame(rafId)
	owner = { slot, onLoad }
	frame.title = title || ""
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

/** The panel with this slot no longer shows the frame. */
export function releaseRavenFrame(slot) {
	if (!owner || owner.slot !== slot) return
	owner = null
	cancelAnimationFrame(rafId)
	setHidden()
}

/** The running Raven's window, or null before the first panel loaded it. */
export function ravenFrameWindow() {
	return loaded ? frame?.contentWindow || null : null
}
