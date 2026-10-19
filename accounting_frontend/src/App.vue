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
const canReadAiSkills = ref(false)

const aiNavItem = {
	name: "AiAccountant",
	label: "AI Accountant",
	icon: "cpu",
	match: ["AiAccountant"],
}

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
	{
		name: "Receipts",
		label: "Receipts",
		icon: "file-text",
		match: ["Receipts", "ReceiptDetail"],
		children: [
			{ name: "Receipts", label: "Queue", icon: "inbox", match: ["Receipts", "ReceiptDetail"] },
			{ name: "ReceiptsAll", label: "All receipts", icon: "list", match: ["ReceiptsAll"] },
		],
	},
]

// With statistics access, Receipts opens on the statistics overview (like Issues opens on
// its overview); its existing sub-pages (or the list) and the payment calendar sit below.
const paymentsCalendarNavItem = {
	name: "PaymentsCalendar",
	label: "Payment calendar",
	icon: "calendar",
	match: ["PaymentsCalendar"],
}

function withStatistics(receiptsItem) {
	const children = receiptsItem.children?.length
		? receiptsItem.children
		: [{ name: receiptsItem.name, label: "List", icon: "list", match: receiptsItem.match }]
	return {
		...receiptsItem,
		name: "ReceiptStatistics",
		match: ["ReceiptStatistics"],
		children: [...children, paymentsCalendarNavItem],
	}
}

const misNavItem = {
	name: "MisList",
	label: "Monthly Implementation Summary",
	icon: "calendar",
	match: ["MisList", "MisDetail"],
}

const navItems = computed(() => [
	...baseNavItems.map((item) => (item.name === "Receipts" && canReadStatistics.value ? withStatistics(item) : item)),
	...(canReadAiSkills.value ? [aiNavItem] : []),
	...(canReadMis.value ? [misNavItem] : []),
])

const pageTitle = computed(() => {
	if (route.name === "Tasks" || route.name === "TasksGantt" || route.name === "TaskDetail") {
		return "Tasks"
	}
	if (route.name === "Checklists" || route.name === "ChecklistDetail") return "Checklists"
	if (route.name === "Receipts" || route.name === "ReceiptDetail") return "Receipts"
	if (route.name === "PaymentsCalendar") return "Payment calendar"
	if (route.name === "ReceiptStatistics") return "Receipts"
	if (route.name === "ReceiptsAll") return "All receipts"
	if (route.name === "AiAccountant") return "AI Accountant"
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
		return "What needs to happen next: decide, send to DATEV, wait for payment"
	}
	if (route.name === "PaymentsCalendar") {
		return "Approved receipts and open Payment Requests by due date"
	}
	if (route.name === "ReceiptStatistics") {
		return "Receipts, booked expense, peaks and what is still to pay"
	}
	if (route.name === "ReceiptsAll") return "Search and filter every receipt"
	if (route.name === "AiAccountant") return "What the AI does with receipts, how it is set up, and what its runs did"
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
		canReadAiSkills.value = Boolean(settings?.can_read_ai_skills)
	} catch {
		canReadMis.value = false
		canReadStatistics.value = false
	}
})
</script>
