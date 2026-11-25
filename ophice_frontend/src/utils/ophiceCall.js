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

// Buttons of the embedded call's Jitsi toolbar; Jitsi hides every button not listed. "desktop" is
// screen sharing: always there, for everyone (#2136).
export const JITSI_TOOLBAR_BUTTONS = ["microphone", "camera", "desktop", "videoquality", "tileview", "hangup"]

/** Window name of the call: opening it again brings the same window back. */
export function encounterCallWindowName(video) {
	return `ophice-call-${String(video?.room || "").replace(/[^A-Za-z0-9_-]/g, "")}`
}

// --- The bubble with the embedded call (#2108): no title bar; chat (with both chips) on the left,
// video in the middle, a slim bar of buttons on the right. It is moved and resized freely within
// these rules:
// - the video between 16:9 (widest) and 1:1 (tallest); the chat takes the rest of the width
// - the chat at least 144px (half its old fixed width)
export const CALL_PAD = 16 // the video's inset, 8px on each side
export const CALL_BORDER = 1 // between chat and video
export const CALL_SIDEBAR = 41 // the button bar on the right, with its border
export const CALL_CHAT_MIN = 144
// The chat column needs room for the two chips, a message and the text field.
export const CALL_MIN_H = 240
const SIDES = CALL_BORDER + CALL_PAD + CALL_SIDEBAR
// Tallest bubble for a width: a square video next to the smallest chat.
export const callMaxHeight = (w) => w - SIDES - CALL_CHAT_MIN + CALL_PAD
export const CALL_MIN_W = CALL_MIN_H - callMaxHeight(0)
// The old size: chat 288 and a 768 x 432 video.
export const CALL_DEFAULT = { w: 288 + SIDES + 768, h: CALL_PAD + 432 }

/**
 * The size shown for a wanted size, inside a stage of view.width x view.height.
 * @returns {{ w: number, h: number, videoW: number, videoH: number, chatW: number }}
 */
export function callBox(size, view) {
	const vw = view?.width || Infinity
	const vh = view?.height || Infinity
	const w = Math.max(CALL_MIN_W, Math.min(vw, size?.w || CALL_DEFAULT.w))
	const h = Math.max(CALL_MIN_H, Math.min(vh, callMaxHeight(w), size?.h || CALL_DEFAULT.h))
	const videoH = h - CALL_PAD
	const videoW = Math.max(videoH, Math.min(Math.round((videoH * 16) / 9), w - SIDES - CALL_CHAT_MIN))
	return { w, h, videoW, videoH, chatW: w - SIDES - videoW }
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

// --- Video quality of the embedded call (PM, 2026-11-25): it starts at 180p, Jitsi's lowest level
// that still shows video ("low bandwidth" below it turns video off). Jitsi may report others (2160).
export const QUALITY_LEVELS = [180, 360, 720]

/** The level a Jitsi value counts as: the highest one it reaches (2160 → 720, 0 → 180). */
export function qualityLevel(height) {
	return [...QUALITY_LEVELS].reverse().find((level) => height >= level) || QUALITY_LEVELS[0]
}

/** One level up; after the highest back to the lowest. */
export function nextQualityLevel(height) {
	const i = QUALITY_LEVELS.indexOf(qualityLevel(height))
	return QUALITY_LEVELS[(i + 1) % QUALITY_LEVELS.length]
}

/**
 * Keeps our quality and Jitsi's in step. Jitsi has no start setting for it and drops the command
 * right after joining, so start() sends it until Jitsi reports it back, a few times at most. Until
 * then Jitsi's own values are ignored; once the tries run out, its last value counts. After that
 * every value Jitsi reports counts (its own toolbar may change it).
 * @param {(height: number) => void} send  sets the quality in Jitsi
 * @param {(height: number) => void} onValue  the quality to show
 */
export function qualitySync(send, onValue, { start = QUALITY_LEVELS[0], tries = 5, every = 1500 } = {}) {
	let settled = false
	let timer = null
	let last = 0
	function settle(height) {
		settled = true
		clearTimeout(timer)
		if (height) onValue(height)
	}
	function attempt(left) {
		if (settled) return
		if (left <= 0) return settle(last)
		send(start)
		timer = setTimeout(() => attempt(left - 1), every)
	}
	return {
		start: () => attempt(tries),
		/** A value Jitsi reported (videoQualityChanged). */
		reported(height) {
			if (!height) return
			last = height
			if (settled || height === start) settle(height)
		},
		/** The user picked a level on our button. */
		choose(height) {
			settle(height)
			send(height)
		},
		stop: () => clearTimeout(timer),
	}
}
