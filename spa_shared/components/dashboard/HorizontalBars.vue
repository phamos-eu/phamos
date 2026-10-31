<template>
	<section class="rounded-lg border border-outline-gray-2 bg-surface-white p-5">
		<h2 class="mb-4 text-base font-semibold text-ink-gray-9">{{ title }}</h2>
		<p v-if="!rows.length" class="text-sm text-ink-gray-5">{{ emptyText || __("Nothing to show yet.") }}</p>
		<div v-else class="space-y-3">
			<div
				v-for="row in rows"
				:key="row.key ?? row.label"
				:role="selectable ? 'button' : undefined"
				:tabindex="selectable ? 0 : undefined"
				:class="selectable ? 'cursor-pointer rounded hover:bg-surface-gray-1 focus-visible:outline focus-visible:outline-2 focus-visible:outline-outline-gray-4' : ''"
				@click="selectable && emit('select', row)"
				@keydown.enter.prevent="selectable && emit('select', row)"
				@keydown.space.prevent="selectable && emit('select', row)"
			>
				<div class="mb-1 flex justify-between gap-3 text-xs">
					<span class="truncate text-ink-gray-7" :title="row.label">{{ row.label }}</span>
					<span class="font-semibold tabular-nums text-ink-gray-9">{{ format ? format(row.value, row) : row.value }}</span>
				</div>
				<div class="h-2 overflow-hidden rounded-full bg-surface-gray-2">
					<div
						class="h-full rounded-full"
						:style="{ width: `${(Number(row.value) / max) * 100}%`, background: BAR_COLORS[row.theme || 'blue'] }"
					/>
				</div>
			</div>
		</div>
	</section>
</template>

<script setup>
import { computed } from "vue"
import { __ } from "@spa/utils/i18n.js"

const props = defineProps({
	title: { type: String, required: true },
	rows: { type: Array, default: () => [] },
	emptyText: { type: String, default: "" },
	// Optional (value, row) => string for the number shown next to the label.
	format: { type: Function, default: null },
	// Rows become keyboard-focusable buttons that emit `select` with the row (drill-down).
	selectable: { type: Boolean, default: false },
})

const emit = defineEmits(["select"])

// Theme variables from frappe-ui, so the bars follow light and dark mode.
const BAR_COLORS = {
	blue: "var(--ink-blue-3)",
	green: "var(--ink-green-3)",
	amber: "var(--ink-amber-3)",
	red: "var(--ink-red-3)",
	gray: "var(--ink-gray-4)",
}

const max = computed(() => Math.max(1, ...props.rows.map((row) => Number(row.value) || 0)))
</script>
