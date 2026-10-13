/**
 * Pure helpers behind useAutosaveDoc: value comparison, dirty tracking, merging
 * a server payload into local drafts, and the save scheduler.
 *
 * DOM-free and Vue-free so they can be unit-tested (see autosaveCore.test.js).
 *
 * Field definitions (`defs`) map a fieldname to:
 *   kind:       "text" | "html" | "select" | "number" | "date" | "datetime"
 *   trim:       compare/send trimmed text (text only)
 *   required:   refuse to save an empty value
 *   immediate:  save right away instead of after the debounce (selects, dates)
 *   toServer:   (value) => value sent to the API
 *   fromServer: (value) => value shown in the form
 *   label:      human label for banners ("Description")
 */

const EMPTY_PARAGRAPH = /<p>(\s|&nbsp;|<br[^>]*>)*<\/p>/gi

export function isEmptyHtml(html) {
	if (!html) return true
	const text = String(html)
		.replace(/<img[^>]*>/gi, "img")
		.replace(/<[^>]+>/g, "")
		.replace(/&nbsp;/g, " ")
		.trim()
	return !text
}

/**
 * Canonical form of editor HTML for equality checks only (never sent anywhere).
 * Ignores whitespace between tags, trailing empty paragraphs and the
 * ProseMirror trailing-break placeholder.
 */
export function normalizeHtml(html) {
	if (isEmptyHtml(html)) return ""
	let out = String(html)
		.replace(/\s+/g, " ")
		.replace(/>\s+</g, "><")
		.replace(/<br class="ProseMirror-trailingBreak">/gi, "<br>")
		.trim()
	// Drop trailing empty paragraphs (TipTap adds one after lists/images).
	let previous
	do {
		previous = out
		out = out.replace(/(<p>(\s|&nbsp;|<br[^>]*>)*<\/p>)+$/i, "")
	} while (out !== previous)
	return out.replace(EMPTY_PARAGRAPH, "<p></p>")
}

function blank(v) {
	return v === null || v === undefined ? "" : v
}

export function fieldEquals(def, a, b) {
	const kind = def?.kind || "text"
	if (kind === "html") return normalizeHtml(a) === normalizeHtml(b)
	if (kind === "number") return Number(a || 0) === Number(b || 0)
	if (kind === "text" && def?.trim) return String(blank(a)).trim() === String(blank(b)).trim()
	return String(blank(a)) === String(blank(b))
}

export function fromServerValue(def, value) {
	if (def?.fromServer) return def.fromServer(value)
	if (def?.kind === "number") return Number(value ?? 0)
	return blank(value)
}

export function toServerValue(def, value) {
	if (def?.toServer) return def.toServer(value)
	if (def?.kind === "html") return isEmptyHtml(value) ? "" : value
	if (def?.kind === "text" && def?.trim) return String(blank(value)).trim()
	if (def?.kind === "number") return Number(value || 0)
	return blank(value)
}

export function isEmptyValue(def, value) {
	if (def?.kind === "html") return isEmptyHtml(value)
	return !String(blank(value)).trim()
}

export function computeDirtyFields(defs, draft, lastSynced) {
	return Object.keys(defs).filter((f) => !fieldEquals(defs[f], draft[f], lastSynced[f]))
}

/**
 * Merge a server payload into local state.
 *
 * - Clean fields adopt the server value, unless the field is focused: then the
 *   value is returned in `deferred` and applied when the field loses focus, so
 *   a cursor never moves under the user's hands.
 * - Dirty fields keep the local draft. When the server value changed compared
 *   to what we last knew (`baseline`) the field is reported in `conflicts`,
 *   except for `source: "save"` where the change is our own write coming back.
 *
 * Fields missing from `server` are left untouched (partial payloads).
 * Returns new objects; inputs are not mutated.
 */
export function mergeServerDoc({ defs, server, draft, baseline, lastSynced, focused = new Set(), source }) {
	const next = {
		draft: { ...draft },
		baseline: { ...baseline },
		lastSynced: { ...lastSynced },
		deferred: {},
		conflicts: [],
	}
	if (!server) return next
	for (const f of Object.keys(defs)) {
		if (!(f in server)) continue
		const def = defs[f]
		const serverValue = fromServerValue(def, server[f])
		const dirty = !fieldEquals(def, draft[f], lastSynced[f])
		const changedOnServer = !fieldEquals(def, serverValue, baseline[f])
		next.baseline[f] = serverValue
		if (!dirty) {
			if (focused.has(f) && !fieldEquals(def, serverValue, draft[f])) {
				next.deferred[f] = serverValue
				continue
			}
			next.draft[f] = serverValue
			next.lastSynced[f] = serverValue
		} else if (changedOnServer && source !== "save") {
			next.conflicts.push(f)
		}
	}
	return next
}

/**
 * Order two Frappe `modified` strings ("YYYY-MM-DD HH:MM:SS[.ffffff]").
 * Frappe drops the fraction when it is zero, so both sides are padded first.
 * Returns -1, 0 or 1; a missing value sorts first.
 */
export function compareModified(a, b) {
	const norm = (v) => {
		if (!v) return ""
		const [base, frac = ""] = String(v).replace("T", " ").split(".")
		return `${base}.${frac.padEnd(6, "0").slice(0, 6)}`
	}
	const x = norm(a)
	const y = norm(b)
	if (x === y) return 0
	return x < y ? -1 : 1
}

/**
 * Trailing debounce with a maximum wait and explicit flush/cancel.
 * `run` is called at most once per burst; `flush()` runs it immediately.
 */
export function createSaveScheduler({ wait = 500, maxWait = 3000, run }) {
	let waitTimer = null
	let maxTimer = null

	function clear() {
		if (waitTimer) clearTimeout(waitTimer)
		if (maxTimer) clearTimeout(maxTimer)
		waitTimer = null
		maxTimer = null
	}

	function fire() {
		clear()
		return run()
	}

	return {
		schedule() {
			if (waitTimer) clearTimeout(waitTimer)
			waitTimer = setTimeout(fire, wait)
			if (!maxTimer && maxWait) maxTimer = setTimeout(fire, maxWait)
		},
		flush: fire,
		cancel: clear,
		isPending: () => waitTimer !== null,
	}
}

/**
 * Serialise async runs. A call while a run is in flight does not start a
 * second one and is not dropped either: exactly one follow-up run happens
 * after the current one, and every caller gets a promise for the whole chain.
 */
export function createCoalescedRunner(fn) {
	let inflight = null
	let again = false

	async function loop() {
		try {
			do {
				again = false
				await fn()
			} while (again)
		} finally {
			inflight = null
		}
	}

	return {
		run() {
			if (inflight) {
				again = true
				return inflight
			}
			inflight = loop()
			return inflight
		},
		isRunning: () => inflight !== null,
		idle: () => (inflight ? inflight.catch(() => {}) : Promise.resolve()),
	}
}

/** Frappe error helpers (errors thrown by frappe-ui `call`). */
export function isTimestampConflict(e) {
	return e?.exc_type === "TimestampMismatchError" || Boolean(e?.latest)
}

export function isFieldLocked(e) {
	return e?.exc_type === "FieldLockedError"
}

export function errorMessage(e, fallback) {
	return e?.messages?.[0] || e?.message || fallback
}
