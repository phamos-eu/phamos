<template>
	<div class="h-full min-h-0 overflow-y-auto bg-surface-gray-1 p-5">
		<div class="mx-auto flex max-w-7xl flex-col gap-5">
			<div v-if="error" class="rounded-lg border border-outline-gray-2 bg-surface-red-1 p-4 text-sm text-ink-red-4">{{ error }}</div>
			<div v-else-if="loading" class="flex min-h-64 items-center justify-center text-sm text-ink-gray-5">{{ __("Loading your Issues…") }}</div>
			<template v-else>
				<section class="grid grid-cols-1 gap-3 md:grid-cols-2 xl:grid-cols-4">
					<template v-for="stat in stats" :key="stat.key">
						<!-- Only tiles about open work lead to the list, which shows open records only (#1611). -->
						<RouterLink v-if="stat.linked" :to="{ name: 'IssuesList' }" class="rounded-lg focus-visible:outline focus-visible:outline-2 focus-visible:outline-outline-gray-4">
							<StatCard :label="stat.label" :value="stat.value" :hint="stat.hint" class="h-full hover:border-outline-gray-3" />
						</RouterLink>
						<StatCard v-else :label="stat.label" :value="stat.value" :hint="stat.hint" />
					</template>
				</section>

				<div class="grid grid-cols-1 gap-5 xl:grid-cols-3">
					<HorizontalBars :title="__('Open by status')" :rows="data.by_status" :empty-text="__('No open Issues.')" />
					<HorizontalBars :title="__('Open by age')" :rows="data.totals.open ? data.by_age : []" :empty-text="__('No open Issues.')" />
					<HorizontalBars :title="__('Open by priority')" :rows="data.by_priority" :empty-text="__('No open Issues.')" />
				</div>

				<section class="rounded-lg border border-outline-gray-2 bg-surface-white p-5">
					<h2 class="mb-3 text-base font-semibold text-ink-gray-9">{{ __("Oldest open Issues") }}</h2>
					<p v-if="!data.oldest.length" class="text-sm text-ink-gray-5">{{ __("Nothing open. Good.") }}</p>
					<ul v-else class="divide-y divide-outline-gray-1">
						<li v-for="issue in data.oldest" :key="issue.name">
							<RouterLink
								:to="{ name: 'IssueDetail', params: { name: issue.name } }"
								data-list-item
								class="flex items-center gap-3 py-2 text-sm hover:bg-surface-gray-1 focus:outline-none focus-visible:bg-surface-gray-2"
							>
								<span class="w-28 flex-none whitespace-nowrap text-xs text-ink-gray-5">{{ issue.name }}</span>
								<span class="min-w-0 flex-1 truncate text-ink-gray-8">{{ issue.subject }}</span>
								<Badge :label="issue.status" size="sm" variant="subtle" :theme="issue.status === 'Open' ? 'orange' : 'gray'" />
								<span class="w-20 flex-none text-right text-xs tabular-nums text-ink-gray-6">{{ days(issue.age_days) }}</span>
							</RouterLink>
						</li>
					</ul>
				</section>
			</template>
		</div>
	</div>
</template>

<script setup>
// My Issues at a glance (#1604): what waits on me, what waits on others, how old the open ones
// are. Every tile leads to the list; the oldest Issues open directly.
import { computed, onMounted, ref } from "vue"
import { Badge, call } from "frappe-ui"
import HorizontalBars from "@spa/components/dashboard/HorizontalBars.vue"
import StatCard from "@spa/components/dashboard/StatCard.vue"
import { useUserRealtime } from "@spa/composables/useUserRealtime.js"
import { __ } from "@spa/utils/i18n.js"
import spaConfig from "@/config"

const loading = ref(true)
const error = ref("")
const data = ref({ totals: {}, by_status: [], by_age: [], by_priority: [], oldest: [], recent_days: 7 })

const days = (value) => (value == null ? "—" : value === 1 ? __("{0} day", [value]) : __("{0} days", [value]))

const stats = computed(() => {
	const t = data.value.totals || {}
	return [
		{ key: "waiting_on_me", linked: true, label: __("Waiting on me"), value: t.waiting_on_me ?? 0, hint: __("Status Open: the next step is mine") },
		{ key: "waiting_on_others", linked: true, label: __("Waiting on others"), value: t.waiting_on_others ?? 0, hint: __("Replied or On Hold") },
		{ key: "open", linked: true, label: __("Open now"), value: t.open ?? 0, hint: t.oldest_days == null ? "" : __("Oldest: {0}", [days(t.oldest_days)]) },
		{ key: "resolved", label: __("Resolved"), value: t.resolved_recently ?? 0, hint: __("In the last {0} days", [data.value.recent_days]) },
	]
})

async function load() {
	try {
		data.value = await call(`${spaConfig.api}.get_issue_dashboard`)
		error.value = ""
	} catch (e) {
		error.value = e?.messages?.[0] || e?.message || __("Could not load your Issues")
	} finally {
		loading.value = false
	}
}

// Assignments are ToDos, so their realtime event also covers Issues assigned or closed elsewhere.
useUserRealtime("cockpit_todos_changed", load, { debounceMs: 500 })
onMounted(load)
</script>
