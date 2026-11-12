<template>
	<CockpitShell :title="pageTitle" :subtitle="pageSubtitle">
		<template #sidebar>
			<CockpitSidebar :label="__('Sales')" storage-key="sales-spa-sidebar-collapsed" :items="navItems" />
		</template>
	</CockpitShell>
</template>

<script setup>
import { computed } from "vue"
import { useRoute } from "vue-router"
import CockpitShell from "@spa/components/CockpitShell.vue"
import CockpitSidebar from "@spa/components/CockpitSidebar.vue"
import { __ } from "@spa/utils/i18n.js"

const route = useRoute()

const LEAD_ROUTES = ["Leads", "LeadsOverview", "LeadsFollowUps", "LeadDetail"]

const NAV_ITEMS = [
	{
		name: "Leads",
		label: "Leads",
		icon: "users",
		match: ["Leads"],
		children: [
			{ name: "LeadsOverview", label: "Overview", icon: "bar-chart-2", match: ["LeadsOverview"] },
			{
				name: "LeadsFollowUps",
				label: "Follow Ups",
				icon: "phone-call",
				match: ["LeadsFollowUps", "LeadDetail"],
			},
		],
	},
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

function translateItem(item) {
	const translated = { ...item, label: __(item.label) }
	if (item.children) translated.children = item.children.map(translateItem)
	return translated
}

const navItems = NAV_ITEMS.map(translateItem)

const pageTitle = computed(() => {
	if (LEAD_ROUTES.includes(route.name)) return __("Leads")
	if (route.name === "Tasks" || route.name === "TasksGantt" || route.name === "TaskDetail") {
		return __("Tasks")
	}
	if (route.name === "Checklists" || route.name === "ChecklistDetail") return __("Checklists")
	return __("Issues")
})

const pageSubtitle = computed(() => {
	if (route.name === "LeadsOverview") return __("How many new leads, compared with what")
	if (LEAD_ROUTES.includes(route.name)) return __("All leads, sorted for follow-up")
	if (route.name === "TasksGantt" || route.name === "TaskDetail") {
		return __("Sales department tasks")
	}
	if (route.name === "Tasks") {
		return __("Sales department tasks overview")
	}
	if (route.name === "Checklists" || route.name === "ChecklistDetail") {
		return __("Checklists linked to Sales issues and tasks")
	}
	if (route.name === "IssuesList" || route.name === "IssueDetail") {
		return __("Sales department issues")
	}
	return __("Sales department issues overview")
})
</script>
