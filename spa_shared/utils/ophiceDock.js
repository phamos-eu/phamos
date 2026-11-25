// The mini map's dock: a right sidebar in the cockpit (#2155). A cockpit inside Ophice runs in a
// frame of the same origin; the right sidebar keeps an empty spot and Ophice lays its mini map
// over it. The two pages talk by postMessage:
// - the frame says whether it has a dock and where its spot is, in Ophice's page coordinates
//   (DOCK_RECT)
// - Ophice says whether the map is docked (the sidebar opens) or being dragged (a drop strip shows
//   over the right edge, without moving the page) (DOCK_SIZE)

export const DOCK_RECT = "phamos-ophice-dock-rect"
export const DOCK_SIZE = "phamos-ophice-dock-size"

/** True inside Ophice's cockpit frame (CockpitFrame.vue marks its iframe). */
export function inOphiceFrame(win = globalThis.window) {
	try {
		return Boolean(win?.frameElement && "ophiceFrame" in win.frameElement.dataset)
	} catch {
		// another origin's frame: not Ophice
		return false
	}
}

/** The message's data when it is a dock message of this type from this site, else null. */
export function dockMessage(event, type, origin = globalThis.location?.origin) {
	const data = event?.data
	if (event?.origin !== origin || !data || typeof data !== "object" || data.type !== type) return null
	return data
}

/** The spot's box in Ophice's page: the frame's place plus the spot's place inside the frame. */
export function rectInParent(frameRect, spotRect) {
	return {
		left: frameRect.left + spotRect.left,
		top: frameRect.top + spotRect.top,
		width: spotRect.width,
		height: spotRect.height,
		bottom: frameRect.top + spotRect.bottom,
	}
}

/** Released here, the dragged mini map docks: over the right sidebar (or its drop strip). */
export function isOverDock(x, y, rect, slack = 24) {
	if (!rect) return false
	return x >= rect.left - slack && x <= rect.left + rect.width + slack && y >= rect.top - slack && y <= rect.bottom + slack
}
