<template>
	<div class="h-full overflow-y-auto p-6">
		<div class="mx-auto max-w-5xl">
			<div class="mb-6">
				<h2 class="text-lg font-semibold text-gray-900 dark:text-gray-100">Implementations</h2>
				<p class="mt-1 text-sm text-gray-500 dark:text-gray-400">
					Choose a workflow to manage customer implementations.
				</p>
			</div>

			<div v-if="loading" class="text-sm text-gray-500 dark:text-gray-400">Loading…</div>
			<div v-else-if="error" class="text-sm text-red-600 dark:text-red-400">{{ error }}</div>

			<div v-else class="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
				<router-link
					:to="{ name: 'WeeklyMonitoring' }"
					class="group rounded-xl border border-gray-200 bg-white p-5 shadow-sm transition hover:border-gray-300 hover:shadow-md dark:border-gray-800 dark:bg-gray-900 dark:hover:border-gray-700"
				>
					<div class="mb-3 flex items-center gap-3">
						<div class="rounded-lg bg-blue-50 p-2 text-blue-700 dark:bg-blue-950 dark:text-blue-300">
							<FeatherIcon name="calendar" class="h-5 w-5" />
						</div>
						<div>
							<div class="font-medium text-gray-900 group-hover:text-gray-950 dark:text-gray-100">
								Weekly Implementation Monitoring
							</div>
							<div class="text-xs text-gray-500 dark:text-gray-400">Primary workflow</div>
						</div>
					</div>
					<p class="mb-4 text-sm text-gray-600 dark:text-gray-300">
						Walk through each active implementation with the account manager and update maturity,
						forecast, and future-hour predictions.
					</p>
					<div class="flex items-center gap-4 text-sm">
						<div>
							<span class="font-semibold text-gray-900 dark:text-gray-100">{{ summary.active_count }}</span>
							<span class="text-gray-500 dark:text-gray-400"> active</span>
						</div>
						<div>
							<span class="font-semibold text-green-700 dark:text-green-400">{{ summary.reviewed_today_count }}</span>
							<span class="text-gray-500 dark:text-gray-400"> reviewed today</span>
						</div>
					</div>
				</router-link>

				<div
					v-for="card in comingSoonCards"
					:key="card.title"
					class="rounded-xl border border-dashed border-gray-200 bg-gray-50 p-5 opacity-70 dark:border-gray-800 dark:bg-gray-900/50"
				>
					<div class="mb-3 flex items-center gap-3">
						<div class="rounded-lg bg-gray-100 p-2 text-gray-500 dark:bg-gray-800 dark:text-gray-400">
							<FeatherIcon :name="card.icon" class="h-5 w-5" />
						</div>
						<div>
							<div class="font-medium text-gray-700 dark:text-gray-300">{{ card.title }}</div>
							<div class="text-xs text-gray-400">Coming soon</div>
						</div>
					</div>
					<p class="text-sm text-gray-500 dark:text-gray-400">{{ card.description }}</p>
				</div>
			</div>
		</div>
	</div>
</template>

<script setup>
import { onMounted, ref } from "vue"
import { call } from "frappe-ui"

const API = "phamos.api.project_management_spa"

const loading = ref(true)
const error = ref("")
const summary = ref({ active_count: 0, reviewed_today_count: 0 })

const comingSoonCards = [
	{
		title: "Stakeholder Meetings",
		icon: "users",
		description: "Plan and review customer stakeholder meetings from the cockpit.",
	},
	{
		title: "Monthly Implementation Summary",
		icon: "file-text",
		description: "Run MIS billing and delivery workflows for implementations.",
	},
]

onMounted(async () => {
	try {
		summary.value = await call(`${API}.get_implementations_hub_summary`)
	} catch (e) {
		error.value = e?.messages?.[0] || e?.message || "Could not load implementations summary"
	} finally {
		loading.value = false
	}
})
</script>
