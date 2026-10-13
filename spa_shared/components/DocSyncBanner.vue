<template>
	<div class="flex min-w-0 flex-wrap items-center justify-end gap-2 text-xs">
		<div
			v-if="autosave.conflict"
			class="flex items-center gap-2 rounded-md border border-outline-amber-1 bg-surface-amber-1 px-2 py-1 text-ink-amber-3"
		>
			<FeatherIcon name="alert-triangle" class="h-3.5 w-3.5 flex-shrink-0" />
			<span class="min-w-0">
				{{ autosave.conflict.by ? `${autosave.conflict.by} also changed` : "Also changed elsewhere:" }}
				{{ conflictLabels }}. Your version is kept.
			</span>
			<button type="button" class="font-semibold underline-offset-2 hover:underline" @click="autosave.acceptServerVersion()">
				Use theirs
			</button>
			<button type="button" class="opacity-70 hover:opacity-100" title="Dismiss" @click="autosave.dismissConflict()">
				<FeatherIcon name="x" class="h-3.5 w-3.5" />
			</button>
		</div>
		<div
			v-else-if="autosave.remoteUpdate"
			class="flex items-center gap-2 rounded-md border border-outline-blue-1 bg-surface-blue-1 px-2 py-1 text-ink-blue-3"
		>
			<FeatherIcon name="refresh-cw" class="h-3.5 w-3.5 flex-shrink-0" />
			<span>Updated by {{ autosave.remoteUpdate.by }} just now</span>
			<button type="button" class="opacity-70 hover:opacity-100" title="Dismiss" @click="autosave.dismissRemoteUpdate()">
				<FeatherIcon name="x" class="h-3.5 w-3.5" />
			</button>
		</div>

		<span v-if="statusText" class="whitespace-nowrap" :class="statusClass" :title="autosave.error || ''">
			{{ statusText }}
		</span>
	</div>
</template>

<script setup>
/** Save state, conflicts and remote updates for one useAutosaveDoc instance. */
import { computed, onBeforeUnmount, ref, watch } from "vue"
import { FeatherIcon } from "frappe-ui"

const props = defineProps({
	autosave: { type: Object, required: true },
})

const showSaved = ref(false)
let savedTimer = null
let remoteTimer = null

watch(
	() => props.autosave.status,
	(status) => {
		clearTimeout(savedTimer)
		showSaved.value = status === "saved"
		if (status === "saved") savedTimer = setTimeout(() => (showSaved.value = false), 2000)
	}
)

watch(
	() => props.autosave.remoteUpdate,
	(update) => {
		clearTimeout(remoteTimer)
		if (update) remoteTimer = setTimeout(() => props.autosave.dismissRemoteUpdate(), 8000)
	}
)

onBeforeUnmount(() => {
	clearTimeout(savedTimer)
	clearTimeout(remoteTimer)
})

const conflictLabels = computed(() =>
	(props.autosave.conflict?.fields || []).map((f) => props.autosave.fieldLabel(f)).join(", ")
)

const statusText = computed(() => {
	const a = props.autosave
	if (a.status === "saving") return "Saving…"
	if (a.status === "pending") return "Unsaved"
	if (a.status === "error" || a.status === "blocked") return a.error || "Not saved"
	if (showSaved.value) return "Saved"
	return ""
})

const statusClass = computed(() => {
	const s = props.autosave.status
	if (s === "error") return "text-ink-red-4"
	if (s === "blocked") return "text-ink-amber-3"
	return "text-ink-gray-5"
})
</script>
