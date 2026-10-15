<template>
	<section class="rounded-lg border border-outline-gray-2 bg-surface-white p-5">
		<div class="mb-4">
			<h2 class="text-base font-semibold text-ink-gray-9">{{ title }}</h2>
			<p v-if="subtitle" class="text-sm text-ink-gray-5">{{ subtitle }}</p>
		</div>
		<div
			class="grid h-48 items-end gap-2 border-b border-outline-gray-2 px-2"
			:style="{ gridTemplateColumns: `repeat(${Math.max(periods.length, 1)}, minmax(0, 1fr))` }"
		>
			<div v-for="period in periods" :key="period.label" class="flex h-full min-w-0 flex-col justify-end gap-1">
				<div class="flex flex-1 items-end justify-center gap-1">
					<div
						v-for="(value, index) in period.values"
						:key="index"
						class="w-2 rounded-t"
						:style="{ height: `${barHeight(value, max)}%`, background: SERIES_COLORS[index] }"
						:title="`${value} ${series[index]?.label || ''}`.trim()"
					/>
				</div>
				<div class="truncate text-center text-[10px] text-ink-gray-5">{{ period.label }}</div>
				<div
					v-if="period.footer != null"
					class="truncate pb-2 text-center text-[10px] font-medium tabular-nums"
					:class="period.footerTone === 'good' ? 'text-ink-green-3' : period.footerTone === 'bad' ? 'text-ink-red-3' : 'text-ink-gray-5'"
				>
					{{ period.footer }}
				</div>
			</div>
		</div>
		<div class="mt-3 flex flex-wrap gap-4 text-xs text-ink-gray-6">
			<span v-for="(item, index) in series" :key="item.label" class="inline-flex items-center gap-1">
				<i class="inline-block h-2.5 w-2.5 rounded-sm" :style="{ background: SERIES_COLORS[index] }" />{{ item.label }}
			</span>
			<span v-if="note" class="text-ink-gray-5">{{ note }}</span>
		</div>
	</section>
</template>

<script setup>
import { computed } from "vue"
import { barHeight } from "@spa/utils/dashboardFormat.js"

const props = defineProps({
	title: { type: String, required: true },
	subtitle: { type: String, default: "" },
	// [{ label, values: [a, b, ...], footer?, footerTone?: "good" | "bad" }]
	periods: { type: Array, default: () => [] },
	series: { type: Array, default: () => [] },
	note: { type: String, default: "" },
})

const SERIES_COLORS = ["var(--ink-blue-3)", "var(--ink-green-3)", "var(--ink-amber-3)", "var(--ink-gray-4)"]

const max = computed(() => Math.max(1, ...props.periods.flatMap((period) => period.values.map(Number))))
</script>
