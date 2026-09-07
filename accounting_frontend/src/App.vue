<template>
	<CockpitShell :title="pageTitle" :subtitle="pageSubtitle">
		<template #sidebar>
			<CockpitSidebar
				label="Accounting"
				storage-key="accounting-spa-sidebar-collapsed"
				:items="navItems"
			/>
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
	{ name: "Receipts", label: "Receipts", icon: "file-text", match: ["Receipts", "ReceiptDetail"] },
]

const pageTitle = computed(() => {
	if (route.name === "Tasks" || route.name === "TasksGantt" || route.name === "TaskDetail") {
		return "Tasks"
	}
	if (route.name === "Checklists" || route.name === "ChecklistDetail") return "Checklists"
	if (route.name === "Receipts" || route.name === "ReceiptDetail") return "Receipts"
	return "Issues"
})

const pageSubtitle = computed(() => {
	if (route.name === "TasksGantt" || route.name === "TaskDetail") {
		return "Accounting department tasks"
	}
	if (route.name === "Tasks") {
		return "Accounting department tasks overview"
	}
	if (route.name === "Checklists" || route.name === "ChecklistDetail") {
		return "Checklists linked to Accounting issues and tasks"
	}
	if (route.name === "Receipts" || route.name === "ReceiptDetail") {
		return "Accounting receipts — review, decide payment, send to DATEV"
	}
	if (route.name === "IssuesList" || route.name === "IssueDetail") {
		return "Accounting department issues"
	}
	return "Accounting department issues overview"
})
</script>
