// The mini map's dock in the cockpit sidebar (#2155). A cockpit inside Ophice runs in a frame of
// the same origin; the sidebar keeps an empty spot and Ophice lays its mini map over it. The two
// pages talk by postMessage:
// - the frame says where the spot is, in Ophice's page coordinates (DOCK_RECT)
// - Ophice says how tall the spot must be, and whether to show it as a drop target (DOCK_SIZE)

export const DOCK_RECT = "phamos-ophice-dock-rect"
export const DOCK_SIZE = "phamos-ophice-dock-size"
/** The spot while the mini map is dragged: tall enough to aim at. */
export const DROP_TARGET_HEIGHT = 72
/** The dock takes at most this share of the sidebar's height; the menu above it scrolls. */
export const DOCK_MAX_SHARE = 0.6

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

/** Released here, the dragged mini map docks: over the sidebar column, at or below the spot. */
export function isOverDock(x, y, dock, slack = 24) {
	if (!dock) return false
	const top = Math.min(dock.top, dock.bottom - DROP_TARGET_HEIGHT)
	return x >= dock.left - slack && x <= dock.left + dock.width + slack && y >= top - slack && y <= dock.bottom + slack
}
