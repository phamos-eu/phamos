import { getCurrentInstance, onBeforeUnmount, reactive, watch } from "vue"
import { call } from "frappe-ui"
import { sessionUser } from "@spa/session.js"
import { callKeepalive } from "@spa/utils/keepaliveCall.js"

const API = "phamos.api.presence"
const LOCK_EVENT = "cockpit_field_lock"
// Well under the server's 30 s LOCK_TTL, so one lost heartbeat never drops an active lock.
const HEARTBEAT_MS = 10000

/**
 * Soft field locks: while a user edits a text field, everyone else sees
 * "<name> is editing…" and the field is read-only for them. Locks expire on
 * the server after 30 s without a heartbeat, so a closed tab never blocks a
 * field for long. Changes arrive through the document's realtime room.
 *
 *   const locks = useFieldLocks({ doctype: "Issue", name: () => issue.name, realtime })
 *   locks.lockedBy("description")   // other user's lock or null
 *   await locks.acquire("description") // false when someone else holds it
 *   locks.release("description")
 *
 * Field names for child rows use "<field>:<row name>", e.g. "note:abc123".
 */
export function useFieldLocks({ doctype, name, realtime, onReleased, enabled = () => true }) {
	const locks = reactive({}) // fieldname -> { user, full_name, user_image }
	const expiryTimers = {}
	const heartbeats = {}
	const mine = new Set()
	let current = null

	function clearExpiry(field) {
		clearTimeout(expiryTimers[field])
		delete expiryTimers[field]
	}

	function drop(field) {
		const had = locks[field]
		clearExpiry(field)
		delete locks[field]
		if (had && had.user !== sessionUser()) onReleased?.(field)
	}

	function apply(lock) {
		if (!lock || lock.doctype !== doctype || lock.name !== current) return
		const field = lock.fieldname
		if (lock.action === "released") return drop(field)
		clearExpiry(field)
		locks[field] = {
			user: lock.user,
			full_name: lock.full_name,
			user_image: lock.user_image,
			// Local time at which the server drops the lock without a heartbeat.
			expiresAt: Date.now() + Math.max(0, lock.expires_in || 0) * 1000,
		}
		expiryTimers[field] = setTimeout(() => drop(field), Math.max(1, lock.expires_in || 0) * 1000)
	}

	async function load() {
		if (!current || !enabled()) return
		const docname = current
		try {
			const rows = await call(`${API}.get_field_locks`, { doctype, name: docname })
			if (docname !== current) return
			for (const field of Object.keys(locks)) if (!mine.has(field)) drop(field)
			for (const row of rows || []) apply(row)
		} catch (e) {
			// Fail open: without lock info the editors still autosave safely.
		}
	}

	function stopHeartbeat(field) {
		clearInterval(heartbeats[field])
		delete heartbeats[field]
	}

	function lockedBy(field) {
		const lock = locks[field]
		return lock && lock.user !== sessionUser() ? lock : null
	}

	const pending = {} // fieldname -> in-flight acquire promise

	async function acquire(field) {
		if (!current || !enabled()) return true
		if (lockedBy(field)) return false
		const docname = current
		// Count the field as ours before the request returns, so a release
		// (blur, unmount, page close) that happens meanwhile is not skipped and
		// the lock is not left behind until it expires.
		mine.add(field)
		const request = call(`${API}.acquire_field_lock`, { doctype, name: docname, fieldname: field })
		pending[field] = request
		try {
			const result = await request
			if (pending[field] === request) delete pending[field]
			if (docname !== current || !mine.has(field)) return false
			apply(result?.lock)
			if (!result?.ok) {
				mine.delete(field)
				return false
			}
			stopHeartbeat(field)
			heartbeats[field] = setInterval(() => {
				call(`${API}.acquire_field_lock`, { doctype, name: docname, fieldname: field })
					.then((r) => apply(r?.lock))
					.catch(() => {})
			}, HEARTBEAT_MS)
			return true
		} catch (e) {
			if (pending[field] === request) delete pending[field]
			return true
		}
	}

	function release(field, { keepalive = false, docname = current } = {}) {
		stopHeartbeat(field)
		if (!mine.delete(field) || !docname) return
		if (docname === current && locks[field]?.user === sessionUser()) {
			clearExpiry(field)
			delete locks[field]
		}
		const args = { doctype, name: docname, fieldname: field }
		if (keepalive) {
			callKeepalive(`${API}.release_field_lock`, args)
			return
		}
		// Release after a still-running acquire, never before it.
		const inflight = pending[field] || Promise.resolve()
		inflight
			.catch(() => {})
			.then(() => call(`${API}.release_field_lock`, args))
			.catch(() => {})
	}

	function releaseAll(options = {}) {
		for (const field of [...mine]) release(field, options)
	}

	realtime?.on?.(LOCK_EVENT, apply)
	realtime?.onReconnect?.(load)

	watch(
		name,
		(docname, previous) => {
			if (previous) releaseAll({ docname: previous })
			for (const field of Object.keys(locks)) {
				clearExpiry(field)
				delete locks[field]
			}
			current = docname || null
			load()
		},
		{ immediate: true }
	)

	function onPageLeave() {
		releaseAll({ keepalive: true })
	}

	if (typeof window !== "undefined") {
		window.addEventListener("beforeunload", onPageLeave)
		window.addEventListener("pagehide", onPageLeave)
	}

	if (getCurrentInstance()) {
		onBeforeUnmount(() => {
			window.removeEventListener("beforeunload", onPageLeave)
			window.removeEventListener("pagehide", onPageLeave)
			releaseAll()
			for (const field of Object.keys(expiryTimers)) clearExpiry(field)
		})
	}

	return { locks, lockedBy, acquire, release, releaseAll, isMine: (field) => mine.has(field) }
}
