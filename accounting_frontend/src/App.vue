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
import { computed, onMounted, ref } from "vue"
import { useRoute } from "vue-router"
import { call } from "frappe-ui"
import CockpitShell from "@spa/components/CockpitShell.vue"
import CockpitSidebar from "@spa/components/CockpitSidebar.vue"
import spaConfig from "./config"

const route = useRoute()
const canReadMis = ref(false)
const canReadStatistics = ref(false)

const baseNavItems = [
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

const misNavItem = {
	name: "MisList",
	label: "Monthly Implementation Summary",
	icon: "calendar",
	match: ["MisList", "MisDetail"],
}

const statisticsNavItems = [
	{ name: "PaymentsCalendar", label: "Payment calendar", icon: "calendar", match: ["PaymentsCalendar"] },
	{ name: "ReceiptStatistics", label: "Statistics", icon: "bar-chart", match: ["ReceiptStatistics"] },
]

const navItems = computed(() => [
	...baseNavItems,
	...(canReadStatistics.value ? statisticsNavItems : []),
	...(canReadMis.value ? [misNavItem] : []),
])

const pageTitle = computed(() => {
	if (route.name === "Tasks" || route.name === "TasksGantt" || route.name === "TaskDetail") {
		return "Tasks"
	}
	if (route.name === "Checklists" || route.name === "ChecklistDetail") return "Checklists"
	if (route.name === "Receipts" || route.name === "ReceiptDetail") return "Receipts"
	if (route.name === "PaymentsCalendar") return "Payment calendar"
	if (route.name === "ReceiptStatistics") return "Statistics"
	if (route.name === "MisList" || route.name === "MisDetail") {
		return "Monthly Implementation Summary"
	}
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
	if (route.name === "PaymentsCalendar") {
		return "Approved receipts and open Payment Requests by due date"
	}
	if (route.name === "ReceiptStatistics") {
		return "Receipts, booked expense, peaks and what is still to pay"
	}
	if (route.name === "MisList" || route.name === "MisDetail") {
		return "Monthly Implementation Summary records"
	}
	if (route.name === "IssuesList" || route.name === "IssueDetail") {
		return "Accounting department issues"
	}
	return "Accounting department issues overview"
})

onMounted(async () => {
	try {
		const settings = await call(`${spaConfig.api}.${spaConfig.settingsMethod}`)
		canReadMis.value = Boolean(settings?.can_read_monthly_implementation_summary)
		canReadStatistics.value = Boolean(settings?.can_read_statistics)
	} catch {
		canReadMis.value = false
		canReadStatistics.value = false
	}
})
</script>
