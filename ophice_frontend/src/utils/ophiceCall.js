// A Jitsi call in its own browser window: encounter calls and meeting areas (#2108, #2078).

/**
 * Address of the call page: the room on its Jitsi host, with my name filled in.
 * @param {{ domain: string, room: string }} video  the call: an encounter's (open_encounter) or an area's
 * @param {string} displayName  my name in the call
 * @returns {string} the URL, or "" without a call
 */
export function jitsiCallUrl(video, displayName = "") {
	const domain = String(video?.domain || "").trim().replace(/^https?:\/\//, "").replace(/\/+$/, "")
	const room = String(video?.room || "").trim()
	if (!domain || !room || /[/\\?#@\s]/.test(domain)) return ""
	// Jitsi reads settings from the fragment as JSON values; the fragment never reaches a server.
	// Whoever opens the call wants to talk: mic and camera on, straight in without the pre-join
	// screen (#2108). The browser still asks once for the permission to use them.
	const settings = [
		"config.startWithAudioMuted=false",
		"config.startWithVideoMuted=false",
		"config.prejoinConfig.enabled=false",
		"config.prejoinPageEnabled=false",
	]
	if (displayName) settings.push(`userInfo.displayName=${encodeURIComponent(JSON.stringify(displayName))}`)
	return `https://${domain}/${encodeURIComponent(room)}#${settings.join("&")}`
}

/** Window name of the call: opening it again brings the same window back. */
export function encounterCallWindowName(video) {
	return `ophice-call-${String(video?.room || "").replace(/[^A-Za-z0-9_-]/g, "")}`
}

// --- The bubble with the embedded call (#2108): chat on the left, video on the right. It is
// moved and resized freely within these rules:
// - the video between 16:9 (widest) and 1:1 (tallest); the chat takes the rest of the width
// - the chat at least 144px (half its old fixed width)
export const CALL_HEADER = 41 // the bubble's title bar
export const CALL_PAD = 16 // the video's inset, 8px on each side
export const CALL_BORDER = 1 // between chat and video
export const CALL_CHAT_MIN = 144
export const CALL_VIDEO_MIN_H = 120
export const CALL_MIN_H = CALL_HEADER + CALL_PAD + CALL_VIDEO_MIN_H
// Tallest bubble for a width: a square video next to the smallest chat.
export const callMaxHeight = (w) => w - CALL_BORDER - CALL_PAD - CALL_CHAT_MIN + CALL_HEADER + CALL_PAD
export const CALL_MIN_W = CALL_MIN_H - callMaxHeight(0)
// The old fixed size: chat 288 and a 768 x 432 video.
export const CALL_DEFAULT = { w: 288 + CALL_BORDER + CALL_PAD + 768, h: CALL_HEADER + CALL_PAD + 432 }

/**
 * The size shown for a wanted size, inside a stage of view.width x view.height.
 * @returns {{ w: number, h: number, videoW: number, videoH: number, chatW: number }}
 */
export function callBox(size, view) {
	const vw = view?.width || Infinity
	const vh = view?.height || Infinity
	const w = Math.max(CALL_MIN_W, Math.min(vw, size?.w || CALL_DEFAULT.w))
	const h = Math.max(CALL_MIN_H, Math.min(vh, callMaxHeight(w), size?.h || CALL_DEFAULT.h))
	const videoH = h - CALL_HEADER - CALL_PAD
	const videoW = Math.max(videoH, Math.min(Math.round((videoH * 16) / 9), w - CALL_BORDER - CALL_PAD - CALL_CHAT_MIN))
	return { w, h, videoW, videoH, chatW: w - CALL_BORDER - CALL_PAD - videoW }
}

/**
 * Resize from an edge or corner: kind holds n, s, e and/or w. The opposite side stays put.
 * @param {{ left: number, top: number, w: number, h: number }} from  the box at the drag's start
 * @returns {{ left: number, top: number, w: number, h: number }}
 */
export function resizeCall(from, kind, dx, dy, view) {
	let w = from.w
	let h = from.h
	if (kind.includes("e")) w = from.w + dx
	if (kind.includes("w")) w = from.w - dx
	if (kind.includes("s")) h = from.h + dy
	if (kind.includes("n")) h = from.h - dy
	const maxW = kind.includes("w") ? from.left + from.w : view.width - from.left
	const maxH = kind.includes("n") ? from.top + from.h : view.height - from.top
	w = Math.max(CALL_MIN_W, Math.min(maxW, w))
	h = Math.max(CALL_MIN_H, Math.min(maxH, callMaxHeight(w), h))
	return {
		left: kind.includes("w") ? from.left + from.w - w : from.left,
		top: kind.includes("n") ? from.top + from.h - h : from.top,
		w,
		h,
	}
}
