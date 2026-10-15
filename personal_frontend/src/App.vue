<template>
	<CockpitShell :title="pageTitle">
		<template #sidebar>
			<CockpitSidebar label="Personal Cockpit" storage-key="personal-cockpit-sidebar-collapsed" :items="navItems" />
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
		name: "Todos",
		label: "ToDos",
		icon: "check-circle",
		match: ["Todos"],
		children: [
			{ name: "TodosList", label: "List", icon: "list", match: ["TodosList", "TodoDetail"] },
			{ name: "TodosMatrix", label: "Matrix", icon: "grid", match: ["TodosMatrix"] },
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

const pageTitle = computed(() => {
	if (["Todos", "TodosList", "TodoDetail", "TodosMatrix"].includes(route.name)) return "My ToDos"
	if (["Tasks", "TasksGantt", "TaskDetail"].includes(route.name)) return "My Tasks"
	if (["ChecklistsHome", "Checklists", "ChecklistDetail"].includes(route.name)) return "My Checklists"
	return "My Issues"
})
</script>
