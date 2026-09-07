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
	{ name: "Issues", label: "Issues", icon: "inbox", match: ["Issues", "IssueDetail"] },
	{ name: "Tasks", label: "Tasks", icon: "check-square", match: ["Tasks", "TaskDetail"] },
	{ name: "Receipts", label: "Receipts", icon: "file-text", match: ["Receipts", "ReceiptDetail"] },
]

const pageTitle = computed(() => {
	if (route.name === "Tasks" || route.name === "TaskDetail") return "Tasks"
	if (route.name === "Receipts" || route.name === "ReceiptDetail") return "Receipts"
	return "Issues"
})

const pageSubtitle = computed(() => {
	if (route.name === "Tasks" || route.name === "TaskDetail") {
		return "Accounting department tasks"
	}
	if (route.name === "Receipts" || route.name === "ReceiptDetail") {
		return "Accounting receipts — review, decide payment, send to DATEV"
	}
	return "Accounting department issues"
})
</script>
