<template>
	<CockpitShell :title="pageTitle" :subtitle="pageSubtitle">
		<template #sidebar>
			<CockpitSidebar label="Human Resources" storage-key="human-resources-spa-sidebar-collapsed" :items="visibleNavItems" />
		</template>
	</CockpitShell>
</template>

<script setup>
import { computed } from "vue"
import { useRoute } from "vue-router"
import CockpitShell from "@spa/components/CockpitShell.vue"
import CockpitSidebar from "@spa/components/CockpitSidebar.vue"
import { useContractAccess } from "./contracts/useContractAccess.js"

const route = useRoute()
const { access } = useContractAccess()

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
		name: "ChecklistsHome",
		label: "Checklists",
		icon: "list",
		match: ["ChecklistsHome"],
		children: [
			{
				name: "Checklists",
				label: "Checklists",
				icon: "list",
				match: ["Checklists", "ChecklistDetail"],
			},
		],
	},
]

// Contracts hold salary, so the section only appears for users who may read them (HR Manager).
const CONTRACT_ROUTES = ["Contracts", "ContractsList", "ContractDetail"]
const contractsNavItem = {
	name: "Contracts",
	label: "Contracts",
	icon: "file-text",
	match: ["Contracts"],
	children: [
		{ name: "ContractsList", label: "List", icon: "list", match: ["ContractsList", "ContractDetail"] },
	],
}
const visibleNavItems = computed(() => (access.value.can_read ? [...navItems, contractsNavItem] : navItems))

const pageTitle = computed(() => {
	if (route.name === "Tasks" || route.name === "TasksGantt" || route.name === "TaskDetail") {
		return "Tasks"
	}
	if (["ChecklistsHome", "Checklists", "ChecklistDetail"].includes(route.name)) return "Checklists"
	if (CONTRACT_ROUTES.includes(route.name)) return "Employment Contracts"
	return "Issues"
})

const pageSubtitle = computed(() => {
	if (route.name === "TasksGantt" || route.name === "TaskDetail") {
		return "HR department tasks"
	}
	if (route.name === "Tasks") {
		return "HR department tasks overview"
	}
	if (route.name === "ChecklistsHome") {
		return "HR checklist activity and workload"
	}
	if (route.name === "Checklists" || route.name === "ChecklistDetail") {
		return "Checklists linked to HR issues and tasks"
	}
	if (route.name === "Contracts") {
		return "Working time and pay agreed with employees and externals"
	}
	if (route.name === "ContractsList" || route.name === "ContractDetail") {
		return "Contracts per employee; a change is a new contract"
	}
	if (route.name === "IssuesList" || route.name === "IssueDetail") {
		return "HR department issues"
	}
	return "HR department issues overview"
})
</script>
