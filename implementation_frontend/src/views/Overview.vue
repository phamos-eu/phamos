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

				<!-- Open reports through Phriend, one click to where they stand (internal, #1671) -->
				<router-link
					v-if="issueCounts"
					:to="{ name: 'Issues', params: { implementation }, query: { scope: issueCounts.mine ? 'mine' : 'implementation' } }"
					class="flex items-center gap-4 rounded-lg border border-outline-gray-2 bg-surface-white p-4 hover:border-outline-gray-3"
				>
					<FeatherIcon name="inbox" class="h-5 w-5 text-ink-gray-6" />
					<div class="min-w-0 flex-1">
						<div class="text-xs font-medium uppercase tracking-wide text-ink-gray-5">{{ __("Open issues") }}</div>
						<div class="mt-1 text-sm text-ink-gray-8">
							{{ __("{0} open, {1} reported by you", [issueCounts.open, issueCounts.mine]) }}
						</div>
					</div>
					<span class="text-sm font-medium text-ink-gray-7">{{ __("See where they stand") }} →</span>
				</router-link>

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
import { computed, ref, watch } from "vue"
import { call } from "frappe-ui"
import dayjs from "dayjs"
import StatCard from "@spa/components/dashboard/StatCard.vue"
import { __ } from "@spa/utils/i18n.js"
import { current } from "../implementationStore.js"
import { scope } from "../scopeStore.js"
import spaConfig from "../config"

const props = defineProps({ implementation: { type: String, required: true } })

const data = computed(() => current.data)

const issueCounts = ref(null)
watch(
	() => props.implementation,
	async (implementation) => {
		issueCounts.value = null
		if (!scope.isInternal) return
		try {
			issueCounts.value = await call(`${spaConfig.api}.get_issue_counts`, { implementation })
		} catch (e) {
			issueCounts.value = null
		}
	},
	{ immediate: true }
)

function formatDate(value) {
	return dayjs(value).format("D MMM YYYY")
}
</script>
