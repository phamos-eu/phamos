// Drop / pick PDFs and e-mails to create receipts. Shared by the queue and the list.
import { ref } from "vue"
import { droppedFiles, droppedMailLink, isExternalDrag, isReceiptFile, uploadReceiptFile } from "../receiptUpload"

export function useReceiptUploads({ onChanged } = {}) {
	const uploads = ref([])
	const dropActive = ref(false)
	const dropNotice = ref("")
	let dragDepth = 0
	let uploadSeq = 0
	let refreshTimer = null

	function onDragEnter(event) {
		if (!isExternalDrag(event)) return
		event.preventDefault()
		dragDepth += 1
		dropActive.value = true
	}

	function onDragOver(event) {
		if (!isExternalDrag(event)) return
		event.preventDefault()
		event.dataTransfer.dropEffect = "copy"
	}

	function onDragLeave(event) {
		if (!isExternalDrag(event)) return
		dragDepth = Math.max(0, dragDepth - 1)
		if (!dragDepth) dropActive.value = false
	}

	function onDrop(event) {
		if (!isExternalDrag(event)) return
		event.preventDefault()
		dragDepth = 0
		dropActive.value = false
		dropNotice.value = ""
		const files = droppedFiles(event)
		if (!files.length) {
			const types = Array.from(event.dataTransfer?.types || []).join(", ") || "nothing"
			dropNotice.value = droppedMailLink(event)
				? "Apple Mail handed over only a link to the message, not the mail itself. Drag the mail (or its PDF) to the Desktop first, then drop that file here."
				: `The drop contained no file the browser can read (received: ${types}). Drag the file from Finder or the Desktop, or use Upload.`
			return
		}
		start(files)
	}

	function start(files) {
		const rejected = files.filter((file) => !isReceiptFile(file)).map((file) => file.name)
		if (rejected.length) dropNotice.value = `Skipped ${rejected.join(", ")}: only PDFs and e-mails (.eml) create receipts.`
		for (const file of files.filter(isReceiptFile)) run(file, false)
	}

	async function run(file, allowDuplicate, existing = null) {
		const upload = existing || { id: ++uploadSeq, filename: file.name, file }
		Object.assign(upload, { state: "uploading", results: [], error: "" })
		if (!existing) uploads.value = [...uploads.value, upload]
		try {
			upload.results = await uploadReceiptFile(file, { allowDuplicate })
			upload.state = "done"
		} catch (e) {
			upload.state = "error"
			upload.error = e?.message || "Upload failed"
		}
		uploads.value = [...uploads.value]
		onChanged?.()
		refreshWhileAiReads()
	}

	// New receipts are read by the AI in the background; refresh a few times so the
	// extracted values show up without reloading the page.
	function refreshWhileAiReads() {
		if (refreshTimer) clearInterval(refreshTimer)
		let rounds = 0
		refreshTimer = setInterval(() => {
			rounds += 1
			onChanged?.({ quiet: true })
			if (rounds >= 10) stop()
		}, 3000)
	}

	function stop() {
		if (refreshTimer) clearInterval(refreshTimer)
		refreshTimer = null
	}

	return {
		uploads,
		dropActive,
		dropNotice,
		handlers: { dragenter: onDragEnter, dragover: onDragOver, dragleave: onDragLeave, drop: onDrop },
		start,
		force: (upload) => run(upload.file, true, upload),
		clear: () => (uploads.value = []),
		stop,
	}
}
