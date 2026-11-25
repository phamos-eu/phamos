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
		// The legacy name of the same switch, for older self-hosted Jitsi: keep both.
		"config.prejoinPageEnabled=false",
	]
	if (displayName) settings.push(`userInfo.displayName=${encodeURIComponent(JSON.stringify(displayName))}`)
	return `https://${domain}/${encodeURIComponent(room)}#${settings.join("&")}`
}

/** Window name of the call: opening it again brings the same window back. */
export function encounterCallWindowName(video) {
	return `ophice-call-${String(video?.room || "").replace(/[^A-Za-z0-9_-]/g, "")}`
}

// --- The bubble with the embedded call (#2108): a slim top bar (own window, "Esc to close", #2135);
// below it the chat (with both chips) on the left and the video on the right. It is moved and
// resized freely within these rules:
// - the video between 16:9 (widest) and 1:1 (tallest); the chat takes the rest of the width
// - the chat at least 144px (half its old fixed width)
// - the line between chat and video can be dragged (#2135): a wider chat narrows the video down
//   to 4:3, not further
export const CALL_PAD = 16 // the video's inset, 8px on each side
export const CALL_BORDER = 1 // between chat and video
export const CALL_HEADER = 37 // the top bar, with its border
export const CALL_CHAT_MIN = 144
// The chat column needs room for the two chips, a message and the text field.
export const CALL_MIN_H = 240
const SIDES = CALL_BORDER + CALL_PAD
const TOP = CALL_HEADER + CALL_PAD
// Tallest bubble for a width: a square video next to the smallest chat.
export const callMaxHeight = (w) => w - SIDES - CALL_CHAT_MIN + TOP
export const CALL_MIN_W = CALL_MIN_H - callMaxHeight(0)
// The old size: chat 288 and a 768 x 432 video.
export const CALL_DEFAULT = { w: 288 + SIDES + 768, h: TOP + 432 }

/**
 * The size shown for a wanted size, inside a stage of view.width x view.height. `size.chat` is the
 * chat width the user dragged to (#2135); without it the video takes all it may (16:9).
 * @returns {{ w: number, h: number, videoW: number, videoH: number, chatW: number }}
 */
export function callBox(size, view) {
	const vw = view?.width || Infinity
	const vh = view?.height || Infinity
	const w = Math.max(CALL_MIN_W, Math.min(vw, size?.w || CALL_DEFAULT.w))
	const h = Math.max(CALL_MIN_H, Math.min(vh, callMaxHeight(w), size?.h || CALL_DEFAULT.h))
	const videoH = h - TOP
	const room = w - SIDES - CALL_CHAT_MIN
	const wanted = Number.isFinite(size?.chat) ? w - SIDES - size.chat : Infinity
	// The wanted chat narrows the video to 4:3 at most; a small bubble still squeezes it to 1:1.
	const videoW = Math.max(
		videoH,
		Math.min(Math.round((videoH * 16) / 9), room, Math.max(Math.round((videoH * 4) / 3), wanted))
	)
	return { w, h, videoW, videoH, chatW: w - SIDES - videoW }
}

/**
 * Drag the line between chat and video (#2135): the chat width as shown after moving it by dx.
 * Stored as shown, so a drag past the 4:3 limit doesn't jump back later.
 */
export function splitCall(size, chatW, dx, view) {
	return callBox({ ...size, chat: Math.max(CALL_CHAT_MIN, chatW + dx) }, view).chatW
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
