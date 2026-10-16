// One receipt in the editor: loading, AI reading state, DATEV, note, status decisions.
import { ref } from "vue"
import { call, toast } from "frappe-ui"

const SPA = "phamos.api.accounting_spa"
const RECEIPT_DOC = "phamos.phamos.doctype.accounting_receipt.accounting_receipt"
const POLL_INTERVAL_MS = 2000
const POLL_MAX_MS = 120000

export function failToast(title) {
	toast({ title, icon: "x-circle", iconClasses: "text-ink-red-4" })
}

export function okToast(title) {
	toast({ title, icon: "check-circle", iconClasses: "text-ink-green-3" })
}

function errorText(e, fallback) {
	return e?.messages?.[0] || e?.message || fallback
}

export function useReceiptDetail({ onChanged } = {}) {
	const receipt = ref(null)
	const loading = ref(false)
	const extractStatus = ref("idle")
	const extractUpdatedCount = ref(0)
	const extractErrorMessage = ref("")
	const showCompare = ref(false)
	let pollTimer = null
	let pollStartedAt = 0
	let pendingNoteSave = null

	function applyExtractStatus(status) {
		const s = status?.status || "idle"
		extractStatus.value = s
		extractUpdatedCount.value = s === "done" ? (status.updated || []).length : 0
		extractErrorMessage.value = s === "failed" ? status?.message || "The AI could not read the PDF." : ""
	}

	function stopPolling() {
		if (pollTimer) clearInterval(pollTimer)
		pollTimer = null
	}

	function startPolling(name) {
		stopPolling()
		pollStartedAt = Date.now()
		pollTimer = setInterval(async () => {
			try {
				const status = await call(`${SPA}.get_receipt_extract_status`, { name })
				applyExtractStatus(status)
				if (status.status === "done" || status.status === "failed") {
					stopPolling()
					await refresh()
					onChanged?.()
					if (status.status === "failed") failToast(extractErrorMessage.value)
				} else if (Date.now() - pollStartedAt > POLL_MAX_MS) {
					stopPolling()
					applyExtractStatus({ status: "failed", message: "The AI reading timed out." })
				}
			} catch (e) {
				stopPolling()
				applyExtractStatus({ status: "failed", message: errorText(e, "Could not check the AI reading") })
			}
		}, POLL_INTERVAL_MS)
	}

	async function load(name) {
		stopPolling()
		showCompare.value = false
		applyExtractStatus({ status: "idle" })
		if (!name) {
			receipt.value = null
			return
		}
		loading.value = true
		try {
			receipt.value = await call(`${SPA}.get_receipt`, { name })
			if (receipt.value?.has_pdf) {
				const status = await call(`${SPA}.get_receipt_extract_status`, { name })
				applyExtractStatus(status)
				if (status.status === "running") startPolling(name)
			}
		} catch (e) {
			receipt.value = null
			failToast(errorText(e, "Could not load the receipt"))
		} finally {
			loading.value = false
		}
	}

	async function refresh() {
		if (receipt.value?.name) receipt.value = await call(`${SPA}.get_receipt`, { name: receipt.value.name })
	}

	function setReceipt(updated) {
		if (updated?.name && updated.name === receipt.value?.name) receipt.value = updated
		onChanged?.({ quiet: true })
	}

	async function runExtract(overwrite = false) {
		if (!receipt.value?.has_pdf) return
		if (overwrite && !window.confirm("Read the PDF again and replace the values on this receipt with what the AI reads?")) return
		try {
			const res = await call(`${SPA}.enqueue_receipt_pdf_extract`, { name: receipt.value.name, overwrite: overwrite ? 1 : 0 })
			if (res?.queued || res?.reason === "already_running") {
				extractStatus.value = "running"
				startPolling(receipt.value.name)
			}
		} catch (e) {
			failToast(errorText(e, "Could not start the AI reading"))
		}
	}

	async function setStatus(status, label) {
		if (!receipt.value) return false
		try {
			receipt.value = await call(`${SPA}.update_receipt_status`, { name: receipt.value.name, status })
			okToast(label || status)
			onChanged?.({ quiet: true })
			return true
		} catch (e) {
			failToast(errorText(e, "Could not change the status"))
			return false
		}
	}

	async function sendToDatev() {
		if (pendingNoteSave) await pendingNoteSave
		if (!receipt.value) return false
		const info = await call(`${RECEIPT_DOC}.get_datev_send_info`, { accounting_receipt_name: receipt.value.name })
		if (!info?.ok || !info.recipient || !info.pdf_url) {
			failToast(info?.message || (!info?.recipient ? "No DATEV recipient is configured." : "PDF attachment is missing."))
			return false
		}
		const question = info.already_sent
			? `Already sent on ${info.sent_at} by ${info.sent_by}. Send ${info.pdf_name} to ${info.recipient} again?`
			: `Send ${info.pdf_name} to ${info.recipient}?`
		if (!window.confirm(question)) return false
		const res = await call(`${RECEIPT_DOC}.send_to_datev`, { accounting_receipt_name: receipt.value.name })
		;(res?.ok ? okToast : failToast)(res?.message || (res?.ok ? "Queued for DATEV." : "Sending failed."))
		await refresh()
		onChanged?.({ quiet: true })
		return Boolean(res?.ok)
	}

	// Leaving the note field (e.g. by clicking Send to DATEV) saves it; send and preview
	// wait for that save so the PDF always carries the note as typed.
	function saveNote(text) {
		pendingNoteSave = (async () => {
			if (!receipt.value) return
			try {
				const res = await call("phamos.api.accounting_receipts.update_receipt_note", { name: receipt.value.name, note: text })
				receipt.value = { ...receipt.value, note_text: res.note_text }
				okToast("Note saved")
			} catch (e) {
				failToast(errorText(e, "Could not save the note"))
			}
		})().finally(() => (pendingNoteSave = null))
		return pendingNoteSave
	}

	async function previewDatev() {
		if (pendingNoteSave) await pendingNoteSave
		if (!receipt.value) return
		try {
			const res = await call(`${RECEIPT_DOC}.preview_datev_pdf`, { accounting_receipt_name: receipt.value.name })
			if (res?.file_url) window.open(res.file_url, "_blank")
		} catch (e) {
			failToast(errorText(e, "Could not build the DATEV PDF"))
		}
	}

	return {
		receipt,
		loading,
		extractStatus,
		extractUpdatedCount,
		extractErrorMessage,
		showCompare,
		load,
		refresh,
		setReceipt,
		runExtract,
		setStatus,
		sendToDatev,
		saveNote,
		previewDatev,
		stopPolling,
	}
}
