<template>
	<!-- The Lead's notes, newest first (#1913). Adding and editing use LeadDetail's dialogs
	     (injected); the notes stay in the timeline as well. -->
	<div class="space-y-2">
		<Button size="sm" icon-left="plus" :label="__('Add note')" @click="ctx?.add()" />
		<p v-if="!sorted.length" class="text-sm text-ink-gray-5">{{ __("No notes yet") }}</p>
		<button
			v-for="note in sorted"
			:key="note.name"
			type="button"
			class="block w-full rounded-lg border border-gray-200 bg-white px-3 py-2 text-left hover:border-gray-300 hover:bg-gray-50 focus:outline-none focus-visible:ring-2 focus-visible:ring-outline-gray-4 dark:border-gray-700 dark:bg-gray-900 dark:hover:bg-gray-800/60"
			:title="__('Edit note')"
			@click="ctx?.edit(note)"
		>
			<div class="mb-1 flex items-center gap-2 text-xs text-ink-gray-5">
				<span class="truncate font-medium text-ink-gray-7">{{ note.added_by_name || note.added_by }}</span>
				<span class="ml-auto flex-shrink-0">{{ formatDatetime(note.added_on) }}</span>
			</div>
			<div class="line-clamp-4 whitespace-pre-line text-sm text-ink-gray-8">{{ plain(note.note) }}</div>
		</button>
	</div>
</template>

<script setup>
import { computed, inject, watch } from "vue"
import { Button } from "frappe-ui"
import { __ } from "@spa/utils/i18n.js"
import { formatDate, formatDatetime } from "@spa/utils/datetime"

defineProps({
	embedded: { type: Boolean, default: false },
})
const emit = defineEmits(["state"])

// { notes: Ref<[]>, add(), edit(note) } from LeadDetail
const ctx = inject("leadNotes", null)

const sorted = computed(() =>
	[...(ctx?.notes?.value || [])].sort((a, b) => String(b.added_on || "").localeCompare(String(a.added_on || "")))
)

// Text only, parsed without running anything: innerHTML on a detached element would still load
// an <img> and fire its handlers.
function plain(html) {
	return (new DOMParser().parseFromString(html || "", "text/html").body.textContent || "").trim()
}

// The rail: "3 notes · last 12.11.2026", and the count as the badge.
watch(
	sorted,
	(list) => {
		const count = list.length
		const summary = count
			? `${count === 1 ? __("1 note") : __("{0} notes", [count])} · ${__("last {0}", [formatDate(list[0].added_on)])}`
			: __("No notes yet")
		emit("state", { summary, badge: count ? String(count) : "" })
	},
	{ immediate: true }
)
</script>
