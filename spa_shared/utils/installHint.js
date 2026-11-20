/**
 * When to show the "install this cockpit as an app" hint, and for which browser (#1998).
 *
 * Each cockpit is installable as its own desktop app (#1458), but browsers hide "Install" in a
 * menu and Safari has no prompt at all. The hint explains it once per browser and cockpit.
 * Pure functions only, so they run under Vitest without a DOM; the Vue side is
 * spa_shared/installApp.js and components/InstallAppDialog.vue.
 */

/** How often "Later" may bring the hint back before it stays away. */
export const MAX_SHOWS = 3

/** Narrower than this is a phone: the cockpits are desktop apps, so no hint there. */
export const MIN_WIDTH = 640

const STORAGE_PREFIX = "phamos.installHint."

/**
 * Which browser's steps to show. Only used to choose the text, never to block anything.
 *
 * @param {string} userAgent navigator.userAgent
 * @param {Array<{brand: string}>} [brands] navigator.userAgentData.brands (Chromium only)
 * @returns {"chrome"|"edge"|"safari"|"firefox"|"other"}
 */
export function browserFamily(userAgent = "", brands = []) {
	const names = (brands || []).map((b) => (b.brand || "").toLowerCase())
	if (names.some((n) => n.includes("edge"))) return "edge"
	if (names.some((n) => n.includes("chrom"))) return "chrome"
	const ua = userAgent || ""
	if (/Edg\//.test(ua)) return "edge"
	if (/Firefox\/|FxiOS\//.test(ua)) return "firefox"
	// Chromium browsers (Chrome, Brave, Arc, Opera, Vivaldi) all carry "Chrome/".
	if (/Chrome\/|CriOS\//.test(ua)) return "chrome"
	if (/Safari\//.test(ua) && /Version\//.test(ua)) return "safari"
	return "other"
}

/**
 * Storage key of one cockpit, from its manifest id ("/implementation-cockpit").
 *
 * @param {string} manifestId
 */
export function storageKey(manifestId) {
	return STORAGE_PREFIX + (manifestId || "cockpit")
}

/**
 * The remembered state of one cockpit's hint. Blocked or broken storage counts as "never shown".
 *
 * @param {Storage|null} storage usually window.localStorage
 * @param {string} key from storageKey()
 * @returns {{shown: number, dismissed: boolean}}
 */
export function readState(storage, key) {
	try {
		const value = JSON.parse(storage?.getItem(key) || "null")
		return { shown: Number(value?.shown) || 0, dismissed: !!value?.dismissed }
	} catch (e) {
		return { shown: 0, dismissed: false }
	}
}

/**
 * Save the state; returns false when the browser blocks storage (private mode, policies).
 *
 * @param {Storage|null} storage
 * @param {string} key
 * @param {{shown: number, dismissed: boolean}} state
 */
export function writeState(storage, key, state) {
	try {
		storage.setItem(key, JSON.stringify({ shown: state.shown, dismissed: state.dismissed }))
		return true
	} catch (e) {
		return false
	}
}

/**
 * Whether to open the hint by itself on this page load.
 *
 * @param {object} env
 * @param {boolean} env.installed the page runs in the installed app window
 * @param {number} env.width the window's inner width
 * @param {{shown: number, dismissed: boolean}} env.state from readState()
 */
export function shouldShowHint({ installed, width, state }) {
	if (installed) return false
	if (width < MIN_WIDTH) return false
	if (state.dismissed) return false
	return state.shown < MAX_SHOWS
}
