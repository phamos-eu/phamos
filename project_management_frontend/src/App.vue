<template>
	<CockpitShell :title="pageTitle" :subtitle="pageSubtitle">
		<template #sidebar>
			<CockpitSidebar label="PM" storage-key="pm-spa-sidebar-collapsed" :items="topItems">
				<template #default="{ collapsed, expand }">
					<div class="mt-1">
						<button
							type="button"
							class="flex w-full items-center gap-2 rounded-md px-2 py-2 text-sm font-medium transition"
							:class="implementationsGroupActive ? activeClass : inactiveClass"
							:title="collapsed ? 'Implementations' : undefined"
							@click="toggleImplementations(expand)"
						>
							<FeatherIcon name="layers" class="h-4 w-4 flex-shrink-0" />
							<span v-if="!collapsed" class="flex-1 truncate text-left">Implementations</span>
							<FeatherIcon
								v-if="!collapsed"
								:name="implementationsOpen ? 'chevron-down' : 'chevron-right'"
								class="h-3.5 w-3.5 flex-shrink-0 opacity-70"
							/>
						</button>

						<div
							v-if="implementationsOpen && !collapsed"
							class="ml-2 mt-1 flex flex-col gap-1 border-l border-gray-200 pl-2 dark:border-gray-700"
						>
							<router-link
								v-for="item in implementationItems"
								:key="item.name"
								:to="{ name: item.name }"
								class="flex items-center gap-2 rounded-md px-2 py-1.5 text-sm font-normal transition"
								:class="isActive(item) ? activeClass : inactiveClass"
							>
								<FeatherIcon :name="item.icon" class="h-3.5 w-3.5 flex-shrink-0" />
								<span class="truncate">{{ item.label }}</span>
							</router-link>
						</div>
					</div>
				</template>
			</CockpitSidebar>
		</template>
	</CockpitShell>
</template>

<script setup>
import { computed, onMounted, ref, watch } from "vue"
import { useRoute } from "vue-router"
import CockpitShell from "@spa/components/CockpitShell.vue"
import CockpitSidebar from "@spa/components/CockpitSidebar.vue"

const IMPL_NAV_KEY = "pm-spa-impl-nav-open"
const route = useRoute()
const implementationsOpen = ref(true)

const activeClass = "bg-gray-900 text-white dark:bg-gray-100 dark:text-gray-900"
const inactiveClass =
	"text-gray-600 hover:bg-gray-100 hover:text-gray-900 dark:text-gray-400 dark:hover:bg-gray-800 dark:hover:text-gray-100"

const topItems = [
	{
		name: "Issues",
		label: "Issues",
		icon: "inbox",
		match: ["Issues"],
		children: [
			{ name: "IssuesList", label: "List", icon: "list", match: ["IssuesList", "IssueDetail"] },
		],
	},
	{
		name: "Tasks",
		label: "Tasks",
		icon: "check-square",
		match: ["Tasks"],
		children: [
			{ name: "TasksGantt", label: "Gantt", icon: "bar-chart-2", match: ["TasksGantt", "TaskDetail"] },
		],
	},
	{
		name: "Checklists",
		label: "Checklists",
		icon: "list",
		match: ["Checklists", "ChecklistDetail"],
	},
]

const implementationItems = [
	{ name: "ImplementationsHub", label: "Overview", icon: "grid", match: ["ImplementationsHub"] },
	{
		name: "WeeklyMonitoring",
		label: "Weekly Monitoring",
		icon: "calendar",
		match: ["WeeklyMonitoring", "WeeklyMonitoringDetail"],
	},
]

const implementationsGroupActive = computed(() =>
	implementationItems.some((item) => item.match.includes(route.name))
)

function isActive(item) {
	return item.match.includes(route.name)
}

function toggleImplementations(expand) {
	expand?.()
	implementationsOpen.value = !implementationsOpen.value
	try {
		localStorage.setItem(IMPL_NAV_KEY, implementationsOpen.value ? "1" : "0")
	} catch (e) {
		/* ignore */
	}
}

watch(
	() => route.name,
	(name) => {
		if (implementationItems.some((item) => item.match.includes(name))) {
			implementationsOpen.value = true
		}
	},
	{ immediate: true }
)

onMounted(() => {
	try {
		const stored = localStorage.getItem(IMPL_NAV_KEY)
		if (stored !== null) implementationsOpen.value = stored === "1"
	} catch (e) {
		/* ignore */
	}
})

const pageTitle = computed(() => {
	if (route.name === "Tasks" || route.name === "TasksGantt" || route.name === "TaskDetail") {
		return "Tasks"
	}
	if (route.name === "Checklists" || route.name === "ChecklistDetail") return "Checklists"
	if (route.name === "ImplementationsHub") return "Implementations"
	if (route.name === "WeeklyMonitoring" || route.name === "WeeklyMonitoringDetail") {
		return "Weekly Implementation Monitoring"
	}
	return "Issues"
})

const pageSubtitle = computed(() => {
	if (route.name === "TasksGantt" || route.name === "TaskDetail") {
		return "Project Management department tasks"
	}
	if (route.name === "Tasks") {
		return "Project Management department tasks overview"
	}
	if (route.name === "Checklists" || route.name === "ChecklistDetail") {
		return "Checklists linked to Project Management issues and tasks"
	}
	if (route.name === "ImplementationsHub") {
		return "Navigate implementation workflows for the Project Management department"
	}
	if (route.name === "WeeklyMonitoring") {
		return "Review active implementations with account managers and update status"
	}
	if (route.name === "WeeklyMonitoringDetail") {
		return route.params.name || "Implementation review"
	}
	if (route.name === "IssuesList" || route.name === "IssueDetail") {
		return "Project Management department issues"
	}
	return "Project Management department issues overview"
})
</script>
