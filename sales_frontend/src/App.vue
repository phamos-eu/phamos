<template>
	<div class="flex h-full min-h-0 bg-gray-50 text-gray-900 dark:bg-gray-950 dark:text-gray-100">
		<SalesSidebar />
		<div class="flex min-w-0 flex-1 flex-col">
			<header
				class="flex flex-shrink-0 items-center justify-between gap-3 border-b border-gray-200 bg-white px-5 py-2.5 dark:border-gray-800 dark:bg-gray-900"
			>
				<div class="min-w-0">
					<div class="text-base font-semibold tracking-tight">{{ pageTitle }}</div>
					<div class="text-xs text-gray-500 dark:text-gray-400">{{ pageSubtitle }}</div>
				</div>
				<div class="flex flex-shrink-0 items-center gap-3">
					<TimesheetPanel />
					<a
						href="/app"
						class="rounded-md px-3 py-1.5 text-sm text-gray-600 hover:bg-gray-100 dark:text-gray-300 dark:hover:bg-gray-800"
					>
						Desk
					</a>
					<button
						class="rounded-md px-3 py-1.5 text-sm text-gray-600 hover:bg-gray-100 dark:text-gray-300 dark:hover:bg-gray-800"
						@click="session.logout.submit()"
					>
						Log out
					</button>
				</div>
			</header>
			<main class="min-h-0 flex-1 overflow-hidden">
				<router-view />
			</main>
		</div>
	</div>
</template>

<script setup>
import { computed, inject } from "vue"
import { useRoute } from "vue-router"
import SalesSidebar from "./components/SalesSidebar.vue"
import TimesheetPanel from "@spa/components/TimesheetPanel.vue"

const session = inject("$session")
const route = useRoute()

const pageTitle = computed(() => {
	if (route.name === "Tasks" || route.name === "TaskDetail") return "Tasks"
	return "Issues"
})

const pageSubtitle = computed(() => {
	if (route.name === "Tasks" || route.name === "TaskDetail") {
		return "Sales department tasks — Gantt, Kanban, and Raven discussion"
	}
	return "Sales department issues — assigned to you and created by you"
})
</script>
