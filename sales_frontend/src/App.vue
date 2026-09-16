<template>
	<CockpitShell :title="pageTitle" :subtitle="pageSubtitle">
		<template #sidebar>
			<CockpitSidebar label="Sales" storage-key="sales-spa-sidebar-collapsed" :items="navItems" />
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
		name: "Today",
		label: "Today",
		icon: "sun",
		match: ["Today"],
	},
	{
		name: "Leads",
		label: "Leads",
		icon: "users",
		match: ["Leads"],
		children: [
			{
				name: "LeadsFollowUps",
				label: "Follow Ups",
				icon: "phone-call",
				match: ["LeadsFollowUps", "LeadDetail"],
			},
		],
	},
	{
		name: "Demos",
		label: "Demos",
		icon: "monitor",
		match: ["Demos"],
		children: [
			{ name: "DemosList", label: "Demos", icon: "list", match: ["DemosList", "DemoDetail"] },
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

const pageTitle = computed(() => {
	if (route.name === "Today") return "Today"
	if (route.name === "Leads" || route.name === "LeadsFollowUps" || route.name === "LeadDetail") {
		return "Leads"
	}
	if (route.name === "Demos" || route.name === "DemosList" || route.name === "DemoDetail") {
		return "Demos"
	}
	if (route.name === "Tasks" || route.name === "TasksGantt" || route.name === "TaskDetail") {
		return "Tasks"
	}
	if (route.name === "Checklists" || route.name === "ChecklistDetail") return "Checklists"
	return "Issues"
})

const pageSubtitle = computed(() => {
	if (route.name === "Today") return "What needs attention today"
	if (route.name === "Demos" || route.name === "DemosList" || route.name === "DemoDetail") {
		return "Demos planned with leads"
	}
	if (route.name === "Leads") return "Lead pipeline overview"
	if (route.name === "LeadsFollowUps" || route.name === "LeadDetail") {
		return "All leads, sorted for follow-up"
	}
	if (route.name === "TasksGantt" || route.name === "TaskDetail") {
		return "Sales department tasks"
	}
	if (route.name === "Tasks") {
		return "Sales department tasks overview"
	}
	if (route.name === "Checklists" || route.name === "ChecklistDetail") {
		return "Checklists linked to Sales issues and tasks"
	}
	if (route.name === "IssuesList" || route.name === "IssueDetail") {
		return "Sales department issues"
	}
	return "Sales department issues overview"
})
</script>
