import { computed, getCurrentInstance, onBeforeUnmount, reactive, ref, watch } from "vue"
import { call } from "frappe-ui"
import { sessionUser } from "@spa/session.js"
import {
	compareModified,
	computeDirtyFields,
	createCoalescedRunner,
	createSaveScheduler,
	errorMessage,
	fieldEquals,
	fromServerValue,
	isEmptyValue,
	isFieldLocked,
	isTimestampConflict,
	mergeServerDoc,
	toServerValue,
} from "@spa/utils/autosaveCore.js"
import { callKeepalive } from "@spa/utils/keepaliveCall.js"

const LOCKED_RETRY_MS = 10000

/**
 * Autosave for a cockpit detail view (Issue, Task, checklist item, Demo, ...).
 *
 * Why this exists (GitLab #1426): the detail views used to write the whole save
 * response back into their fields. Anything typed while the request was in
 * flight was replaced by the older server copy and the rich text editor jumped
 * to the end. This composable keeps a local draft per field and only ever
 * adopts server values for fields the user is not editing.
 *
 * Options
 *   doc:        () => current server document (prop getter; may be replaced)
 *   key:        identity field of `doc` (default "name")
 *   fields:     field definitions, see autosaveCore.js
 *   request:    (name, payload, modified) => ({ method, args }) for a save
 *   parse:      (result, name) => server doc (default: identity). Throw an
 *               error with `exc_type = "TimestampMismatchError"` and `latest`
 *               for APIs that report conflicts in the response body.
 *   fetch:      (name) => Promise<server doc>, used after a conflict and for
 *               realtime refreshes
 *   readonly:   () => boolean, no saves while true
 *   useModified: send `modified` as optimistic lock (default true)
 *   debounceMs / maxWaitMs
 *   onSaved:    (serverDoc) => void, e.g. emit("updated") so lists refresh
 *   onRemoteApplied: (serverDoc) => void, after a realtime refresh
 *   onError:    (message, error) => void, for errors that are not shown inline
 */
export function useAutosaveDoc(options) {
	const {
		doc: docGetter,
		key = "name",
		fields,
		request,
		parse = (result) => result,
		fetch: fetchDoc,
		readonly = () => false,
		useModified = true,
		debounceMs = 500,
		maxWaitMs = 3000,
		onSaved,
		onRemoteApplied,
		onError,
	} = options

	const fieldNames = Object.keys(fields)
	const draft = reactive({})
	const status = ref("idle") // idle | pending | saving | saved | error | blocked
	const error = ref("")
	const conflict = ref(null) // { fields, server, by }
	const remoteUpdate = ref(null) // { by, at }
	const currentName = ref(null)
	const dirtyFields = ref([])

	let lastSynced = {}
	let baseline = {}
	let deferred = {}
	let lockModified = null
	let applying = false
	let lockedRetry = null
	const focused = new Set()
	const knownModified = new Map()

	function refreshDirty() {
		dirtyFields.value = computeDirtyFields(fields, draft, lastSynced)
		return dirtyFields.value
	}

	function adoptModified(name, modified) {
		if (!modified) return
		const known = knownModified.get(name)
		if (!known || compareModified(modified, known) >= 0) knownModified.set(name, String(modified))
		if (name === currentName.value && (!lockModified || compareModified(modified, lockModified) >= 0)) {
			lockModified = String(modified)
		}
	}

	function withApplying(fn) {
		applying = true
		try {
			fn()
		} finally {
			applying = false
		}
	}

	function reset(doc) {
		withApplying(() => {
			currentName.value = doc?.[key] ?? null
			lastSynced = {}
			baseline = {}
			deferred = {}
			for (const f of fieldNames) {
				const value = fromServerValue(fields[f], doc?.[f])
				draft[f] = value
				lastSynced[f] = value
				baseline[f] = value
			}
			lockModified = doc?.modified ? String(doc.modified) : null
			if (doc?.[key] && doc?.modified) knownModified.set(doc[key], String(doc.modified))
			focused.clear()
			conflict.value = null
			remoteUpdate.value = null
			error.value = ""
			status.value = "idle"
		})
		refreshDirty()
	}

	function addConflicts(names, server) {
		if (!names.length) return
		const previous = conflict.value || { fields: [], server: {} }
		const merged = { fields: [...new Set([...previous.fields, ...names])], server: { ...previous.server } }
		for (const f of names) merged.server[f] = fromServerValue(fields[f], server[f])
		merged.by = server.modified_by_name || server.modified_by || previous.by || ""
		conflict.value = merged
	}

	/** Merge a server payload for the current document. Returns conflicting fields. */
	function applyServerDoc(server, source = "prop") {
		if (!server || server[key] !== currentName.value) return []
		const merged = mergeServerDoc({
			defs: fields,
			server,
			draft: { ...draft },
			baseline,
			lastSynced,
			focused,
			source,
		})
		withApplying(() => {
			for (const f of fieldNames) {
				if (draft[f] !== merged.draft[f]) draft[f] = merged.draft[f]
			}
		})
		baseline = merged.baseline
		lastSynced = merged.lastSynced
		// A deferral is replaced by the newest server value, or dropped once the
		// server value is applied (or equals what the user already has).
		for (const f of fieldNames) {
			if (!(f in server)) continue
			if (f in merged.deferred) deferred[f] = merged.deferred[f]
			else delete deferred[f]
		}
		adoptModified(currentName.value, server.modified)
		addConflicts(merged.conflicts, server)
		refreshDirty()
		if (status.value === "pending" && !dirtyFields.value.length) status.value = "saved"
		return merged.conflicts
	}

	function buildSnapshot({ ignoreReadonly = false } = {}) {
		const names = refreshDirty()
		if (!currentName.value || !names.length) return null
		if (!ignoreReadonly && readonly()) return null
		const payload = {}
		const sent = {}
		for (const f of names) {
			sent[f] = draft[f]
			payload[f] = toServerValue(fields[f], draft[f])
		}
		return { name: currentName.value, names, payload, sent, modified: lockModified }
	}

	async function sendSnapshot(snapshot) {
		const { method, args } = request(
			snapshot.name,
			snapshot.payload,
			useModified ? snapshot.modified : undefined
		)
		return parse(await call(method, args), snapshot.name)
	}

	async function runSave(isRetry = false) {
		const snapshot = buildSnapshot()
		if (!snapshot) {
			if (status.value === "pending" || status.value === "saving") status.value = "saved"
			return
		}
		const missing = snapshot.names.find((f) => fields[f].required && isEmptyValue(fields[f], draft[f]))
		if (missing) {
			error.value = `${fields[missing].label || missing} is required`
			status.value = "error"
			return
		}

		status.value = "saving"
		try {
			const server = await sendSnapshot(snapshot)
			adoptModified(snapshot.name, server?.modified)
			if (snapshot.name !== currentName.value) {
				onSaved?.(server)
				return
			}
			for (const f of snapshot.names) lastSynced[f] = snapshot.sent[f]
			applyServerDoc(server, "save")
			error.value = ""
			status.value = refreshDirty().length ? "pending" : "saved"
			onSaved?.(server)
		} catch (e) {
			if (snapshot.name !== currentName.value) {
				onError?.(errorMessage(e, "Could not save your last change"), e)
				return
			}
			if (isTimestampConflict(e) && !isRetry) {
				// Someone else saved in between. Take their version of the fields we
				// did not touch, keep ours for the fields we did, and retry once.
				try {
					const latest = e.latest || (await fetchDoc(snapshot.name))
					if (snapshot.name !== currentName.value) return
					applyServerDoc(latest, "conflict")
					return await runSave(true)
				} catch (inner) {
					e = inner
				}
			}
			if (isFieldLocked(e)) {
				status.value = "blocked"
				error.value = errorMessage(e, "Someone else is editing this field")
				scheduleLockedRetry()
				return
			}
			status.value = "error"
			error.value = isTimestampConflict(e)
				? "This was changed by someone else at the same time. Reload to see the latest version."
				: errorMessage(e, "Could not save")
		}
	}

	const runner = createCoalescedRunner(() => runSave())
	const scheduler = createSaveScheduler({
		wait: debounceMs,
		maxWait: maxWaitMs,
		run: () => runner.run(),
	})

	function scheduleLockedRetry() {
		clearTimeout(lockedRetry)
		lockedRetry = setTimeout(() => scheduler.schedule(), LOCKED_RETRY_MS)
	}

	function schedule() {
		if (readonly()) return
		status.value = "pending"
		scheduler.schedule()
	}

	function flush() {
		scheduler.cancel()
		return runner.run()
	}

	/**
	 * Save edits of a document that is no longer current (doc switch, unmount).
	 * Waits for an in-flight save first so it can use the newest `modified`.
	 */
	async function saveDetached(snapshot) {
		if (!snapshot) return
		try {
			await runner.idle()
			const fresh = { ...snapshot, modified: knownModified.get(snapshot.name) || snapshot.modified }
			let server
			try {
				server = await sendSnapshot(fresh)
			} catch (e) {
				if (!isTimestampConflict(e)) throw e
				const latest = e.latest || (await fetchDoc(snapshot.name))
				server = await sendSnapshot({ ...fresh, modified: latest?.modified })
			}
			adoptModified(snapshot.name, server?.modified)
			onSaved?.(server)
		} catch (e) {
			onError?.(errorMessage(e, "Could not save your last change"), e)
		}
	}

	function switchDoc(doc) {
		scheduler.cancel()
		// The edits were made while the old document was editable; the new
		// document's read-only state must not discard them.
		const snapshot = buildSnapshot({ ignoreReadonly: true })
		reset(doc)
		saveDetached(snapshot)
	}

	function setFocused(field, isFocused) {
		if (isFocused) {
			focused.add(field)
			return Promise.resolve()
		}
		focused.delete(field)
		if (field in deferred) {
			const value = deferred[field]
			delete deferred[field]
			if (fieldEquals(fields[field], draft[field], lastSynced[field])) {
				withApplying(() => {
					draft[field] = value
				})
				lastSynced[field] = value
			}
		}
		// Resolves once everything typed in the field is saved, so callers can
		// release a field lock only after the server has the text.
		return refreshDirty().length ? flush() : runner.idle()
	}

	/** Put the last saved value back (e.g. Escape in a text input). */
	function revert(field) {
		draft[field] = lastSynced[field]
	}

	function syncedValue(field) {
		return lastSynced[field]
	}

	function acceptServerVersion() {
		const c = conflict.value
		if (!c) return
		conflict.value = null
		for (const f of c.fields) draft[f] = c.server[f]
		flush()
	}

	function dismissConflict() {
		conflict.value = null
	}

	function dismissRemoteUpdate() {
		remoteUpdate.value = null
	}

	/**
	 * Called with the `modified` of a realtime `doc_update`. Ignores our own
	 * saves, otherwise refetches and merges (clean fields adopt silently).
	 */
	async function noteRemoteModified(modified) {
		const name = currentName.value
		if (!name || !modified || !fetchDoc) return
		await runner.idle()
		if (name !== currentName.value || compareModified(modified, lockModified) <= 0) return
		let latest
		try {
			latest = await fetchDoc(name)
		} catch (e) {
			return
		}
		if (!latest || name !== currentName.value) return
		const hadEdits = refreshDirty().length > 0 || focused.size > 0
		applyServerDoc(latest, "realtime")
		if (latest.modified_by && latest.modified_by !== sessionUser() && hadEdits) {
			remoteUpdate.value = { by: latest.modified_by_name || latest.modified_by, at: Date.now() }
		}
		onRemoteApplied?.(latest)
	}

	// --- wiring ---------------------------------------------------------------

	for (const f of fieldNames) {
		watch(
			() => draft[f],
			() => {
				if (applying || readonly()) return
				refreshDirty()
				if (fields[f].immediate) {
					status.value = "pending"
					flush()
				} else {
					schedule()
				}
			},
			{ flush: "sync" }
		)
	}

	reset(docGetter())

	watch(
		docGetter,
		(doc) => {
			// A different (or no) document: save the old one's edits, then reset.
			if ((doc?.[key] ?? null) !== currentName.value) switchDoc(doc)
			else if (doc) applyServerDoc(doc, "prop")
		},
		{ deep: true }
	)

	// Leaving the page: send what is unsaved with a keepalive request. Both
	// beforeunload and pagehide are used because not every browser (or embedded
	// webview) delivers pagehide on navigation; the sent values are marked as
	// synced so the second event does not send them again.
	function onPageLeave() {
		scheduler.cancel()
		const snapshot = buildSnapshot()
		if (!snapshot) return
		const { method, args } = request(
			snapshot.name,
			snapshot.payload,
			useModified ? knownModified.get(snapshot.name) || snapshot.modified : undefined
		)
		callKeepalive(method, args)
		for (const f of snapshot.names) lastSynced[f] = snapshot.sent[f]
		refreshDirty()
	}

	function onVisibility() {
		if (document.visibilityState === "hidden" && refreshDirty().length) flush()
	}

	if (typeof window !== "undefined") {
		window.addEventListener("beforeunload", onPageLeave)
		window.addEventListener("pagehide", onPageLeave)
		document.addEventListener("visibilitychange", onVisibility)
	}

	if (getCurrentInstance()) {
		onBeforeUnmount(() => {
			window.removeEventListener("beforeunload", onPageLeave)
			window.removeEventListener("pagehide", onPageLeave)
			document.removeEventListener("visibilitychange", onVisibility)
			clearTimeout(lockedRetry)
			scheduler.cancel()
			saveDetached(buildSnapshot({ ignoreReadonly: true }))
		})
	}

	return reactive({
		draft,
		status,
		error,
		conflict,
		remoteUpdate,
		dirtyFields,
		currentName,
		isDirty: computed(() => dirtyFields.value.length > 0),
		saving: computed(() => status.value === "saving"),
		fieldLabel: (f) => fields[f]?.label || f,
		schedule,
		flush,
		setFocused,
		revert,
		syncedValue,
		applyServerDoc,
		acceptServerVersion,
		dismissConflict,
		dismissRemoteUpdate,
		noteRemoteModified,
	})
}
