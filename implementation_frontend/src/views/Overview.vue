<template>
	<!-- First draft of the Overview (#1675 builds it out): status basics only. -->
	<div class="h-full min-h-0 overflow-y-auto bg-surface-gray-1 p-5">
		<div class="mx-auto flex max-w-7xl flex-col gap-5">
			<div v-if="current.error" class="rounded-lg border border-outline-gray-2 bg-surface-white p-4 text-sm text-ink-red-4">
				{{ current.error }}
			</div>
			<template v-else-if="data">
				<div class="grid grid-cols-1 gap-3 md:grid-cols-2 xl:grid-cols-4">
					<StatCard
						:label="__('Phase')"
						:value="data.phase_number ? `${data.phase_number} / 6` : '—'"
						:hint="data.phase || ''"
					/>
					<StatCard :label="__('Status')" :value="data.status || '—'" :hint="data.trend ? __('Trend: {0}', [data.trend]) : ''" />
					<StatCard
						:label="__('Next review')"
						:value="data.next_review_due ? formatDate(data.next_review_due) : '—'"
						:hint="data.review_cadence || ''"
					/>
					<StatCard
						:label="__('Since')"
						:value="data.start_date ? formatDate(data.start_date) : '—'"
						:hint="data.customer_name || ''"
					/>
				</div>

				<section class="rounded-lg border border-outline-gray-2 bg-surface-white p-4">
					<h2 class="text-xs font-medium uppercase tracking-wide text-ink-gray-5">{{ __("Latest status") }}</h2>
					<p v-if="data.status_statement" class="mt-2 whitespace-pre-line text-sm text-ink-gray-8">{{ data.status_statement }}</p>
					<p v-else class="mt-2 text-sm text-ink-gray-5">{{ __("No status update yet.") }}</p>
				</section>
			</template>
			<div v-else class="text-sm text-ink-gray-5">{{ __("Loading…") }}</div>
		</div>
	</div>
</template>

<script setup>
import { computed } from "vue"
import dayjs from "dayjs"
import StatCard from "@spa/components/dashboard/StatCard.vue"
import { __ } from "@spa/utils/i18n.js"
import { current } from "../implementationStore.js"

defineProps({ implementation: { type: String, required: true } })

const data = computed(() => current.data)

function formatDate(value) {
	return dayjs(value).format("D MMM YYYY")
}
</script>
