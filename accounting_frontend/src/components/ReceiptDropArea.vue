<template>
	<div class="relative flex h-full min-h-0 flex-col" v-on="up.handlers">
		<div
			v-if="up.dropActive.value"
			class="pointer-events-none absolute inset-2 z-20 flex flex-col items-center justify-center gap-1 rounded-lg border-2 border-dashed border-ink-blue-3 bg-surface-white/90 text-center"
		>
			<p class="text-base font-semibold text-ink-gray-9">Drop PDFs or e-mails to create receipts</p>
			<p class="text-sm text-ink-gray-6">One receipt per PDF. E-mails without a PDF get one made from the mail text.</p>
		</div>
		<input ref="fileInput" type="file" multiple accept=".pdf,.eml,application/pdf,message/rfc822" class="hidden" @change="onPick" />
		<div
			v-if="up.dropNotice.value"
			class="flex items-start justify-between gap-3 border-b border-outline-gray-2 bg-surface-amber-1 px-5 py-2 text-sm text-ink-amber-3"
		>
			<span>{{ up.dropNotice.value }}</span>
			<button type="button" class="text-xs text-ink-gray-5 hover:text-ink-gray-8" @click="up.dropNotice.value = ''">Close</button>
		</div>
		<ReceiptUploadList :uploads="up.uploads.value" @open="(name) => emit('open', name)" @force="up.force" @clear="up.clear" />
		<slot :pick="pick" />
	</div>
</template>

<script setup>
import { onBeforeUnmount, ref } from "vue"
import ReceiptUploadList from "./ReceiptUploadList.vue"
import { useReceiptUploads } from "../composables/useReceiptUploads"

const emit = defineEmits(["changed", "open"])
const fileInput = ref(null)
const up = useReceiptUploads({ onChanged: (opts) => emit("changed", opts) })

function pick() {
	fileInput.value?.click()
}

function onPick(event) {
	up.start(Array.from(event.target.files || []))
	event.target.value = ""
}

onBeforeUnmount(() => up.stop())
</script>
