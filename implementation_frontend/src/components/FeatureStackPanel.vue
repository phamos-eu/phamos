<template>
	<!-- Dots too close together are drawn as one dot with a count (#2034); selecting it lists
	     its features here, in date order (#2035 decision 6). One click opens a feature. -->
	<aside class="flex min-h-0 flex-col rounded-lg border border-outline-gray-2 bg-surface-white" :aria-label="title">
		<div class="flex items-center gap-2 border-b border-outline-gray-1 px-4 py-2.5">
			<h2 class="min-w-0 flex-1 truncate text-base font-semibold text-ink-gray-9">{{ title }}</h2>
			<button type="button" class="rounded p-1 text-ink-gray-5 hover:bg-surface-gray-2 hover:text-ink-gray-9" :aria-label="__('Close')" :title="__('Close (Esc)')" @click="$emit('close')">
				<FeatherIcon name="x" class="h-4 w-4" />
			</button>
		</div>
		<ul class="min-h-0 flex-1 overflow-y-auto py-1 text-sm">
			<li v-for="f in features" :key="f.name">
				<button
					type="button"
					class="flex w-full items-center gap-2 px-4 py-1.5 text-left hover:bg-surface-gray-1 focus:bg-surface-gray-2 focus:outline-none"
					@click="$emit('open-feature', f.name)"
				>
					<span class="w-3 shrink-0 text-center text-ink-gray-6" :title="f.kind === 'finished' ? __('finished') : __('planned')">{{ f.kind === "finished" ? "●" : "○" }}</span>
					<span class="min-w-0 flex-1 truncate text-ink-gray-9">{{ f.title }}</span>
					<span class="shrink-0 text-xs text-ink-gray-5">{{ date(f.date) }}</span>
				</button>
			</li>
		</ul>
	</aside>
</template>

<script setup>
import { computed } from "vue"
import dayjs from "dayjs"
import { FeatherIcon } from "frappe-ui"
import { __ } from "@spa/utils/i18n.js"

const props = defineProps({
	/** [{ name, title, kind: "planned" | "finished", date }] (stackFeatures) */
	features: { type: Array, required: true },
})
defineEmits(["close", "open-feature"])

const title = computed(() => __("{0} features", [props.features.length]))

function date(value) {
	return value ? dayjs(value).format("D MMM YYYY") : "—"
}
</script>
