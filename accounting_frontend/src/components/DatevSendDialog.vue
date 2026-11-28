<template>
	<Dialog
		:options="{
			title: 'Send to DATEV',
			size: '4xl',
			actions: [
				{ label: 'Cancel', variant: 'subtle', onClick: () => emit('update:modelValue', false) },
				{ label: testSend ? 'Send test' : 'Send', variant: 'solid', loading: sending, disabled: !recipient.trim(), onClick: submit },
			],
		}"
		:model-value="modelValue"
		@update:model-value="emit('update:modelValue', $event)"
	>
		<template #body-content>
			<div class="flex flex-col gap-3 text-sm" @keydown.meta.enter="submit" @keydown.ctrl.enter="submit">
				<div class="grid grid-cols-2 gap-3">
					<label class="field">
						<span>From</span>
						<input :value="info.sender" type="email" class="input" disabled />
					</label>
					<label class="field">
						<span>To</span>
						<input v-model="recipient" type="email" class="input" autofocus />
						<span class="text-xs text-ink-gray-5">{{ info.recipient ? `DATEV address: ${info.recipient}` : "No DATEV address is configured." }}</span>
					</label>
				</div>
				<p v-if="testSend" class="rounded-md bg-surface-blue-1 px-3 py-2 text-ink-blue-3">
					Test send: the receipt is not marked as sent to DATEV.
				</p>
				<p v-if="info.already_sent && !testSend" class="rounded-md bg-surface-amber-1 px-3 py-2 text-ink-amber-3">
					Already sent on {{ info.sent_at }} by {{ info.sent_by }}.
				</p>
				<p v-if="pdf.loading" class="text-ink-gray-5">Building the PDF…</p>
				<p v-else-if="pdf.error" class="text-ink-red-4">{{ pdf.error }}</p>
				<template v-else-if="pdf.url">
					<p class="text-ink-gray-6">
						<a :href="pdf.url" target="_blank" rel="noopener" class="underline">{{ pdf.url.split("/").pop() }}</a>
						<span v-if="pdf.stamped"> · with the note for the accounting office</span>
					</p>
					<iframe :src="pdf.url" type="application/pdf" class="h-[60vh] w-full rounded-md border border-outline-gray-2" />
				</template>
			</div>
		</template>
	</Dialog>
</template>

<script setup>
// Send to DATEV (#1828): From, an editable To and the PDF exactly as it goes out.
// Another address than the configured one is a test send; the server does not mark the receipt.
import { computed, reactive, ref, watch } from "vue"
import { call, Dialog } from "frappe-ui"

const RECEIPT_DOC = "phamos.phamos.doctype.accounting_receipt.accounting_receipt"

const props = defineProps({
	modelValue: { type: Boolean, default: false },
	receiptName: { type: String, required: true },
	// get_datev_send_info: sender, recipient, already_sent, sent_at, sent_by
	info: { type: Object, required: true },
	sending: { type: Boolean, default: false },
})
const emit = defineEmits(["update:modelValue", "send"])

const recipient = ref("")
const pdf = reactive({ loading: false, url: "", stamped: false, error: "" })

const testSend = computed(() => {
	const value = recipient.value.trim().toLowerCase()
	return Boolean(value) && value !== (props.info.recipient || "").trim().toLowerCase()
})

async function loadPdf() {
	Object.assign(pdf, { loading: true, url: "", stamped: false, error: "" })
	try {
		const res = await call(`${RECEIPT_DOC}.preview_datev_pdf`, { accounting_receipt_name: props.receiptName })
		pdf.url = res?.file_url ? encodeURI(res.file_url) : ""
		pdf.stamped = Boolean(res?.stamped)
	} catch (e) {
		pdf.error = e?.messages?.[0] || e?.message || "Could not build the DATEV PDF"
	} finally {
		pdf.loading = false
	}
}

watch(
	() => props.modelValue,
	(open) => {
		if (!open) return
		recipient.value = props.info.recipient || ""
		loadPdf()
	},
	{ immediate: true }
)

function submit() {
	if (props.sending || !recipient.value.trim()) return
	emit("send", recipient.value.trim())
}
</script>
