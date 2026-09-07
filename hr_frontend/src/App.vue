<template>
	<CockpitShell :title="pageTitle" :subtitle="pageSubtitle">
		<template #sidebar>
			<CockpitSidebar label="HR" storage-key="hr-spa-sidebar-collapsed" :items="navItems" />
		</template>
	</CockpitShell>
</template>

<script setup>
import { computed } from "vue"
import { useRoute } from "vue-router"
import CockpitShell from "@spa/components/CockpitShell.vue"
import CockpitSidebar from "@spa/components/CockpitSidebar.vue"

const route = useRoute()

const navItems = [
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

const pageTitle = computed(() => {
	if (route.name === "Tasks" || route.name === "TasksGantt" || route.name === "TaskDetail") {
		return "Tasks"
	}
	if (route.name === "Checklists" || route.name === "ChecklistDetail") return "Checklists"
	return "Issues"
})

const pageSubtitle = computed(() => {
	if (route.name === "TasksGantt" || route.name === "TaskDetail") {
		return "HR department tasks"
	}
	if (route.name === "Tasks") {
		return "HR department tasks overview"
	}
	if (route.name === "Checklists" || route.name === "ChecklistDetail") {
		return "Checklists linked to HR issues and tasks"
	}
	if (route.name === "IssuesList" || route.name === "IssueDetail") {
		return "HR department issues"
	}
	return "HR department issues overview"
})
</script>
