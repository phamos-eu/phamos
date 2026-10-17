<template>
	<Badge
		class="whitespace-nowrap"
		:label="status"
		:theme="CONTRACT_STATUS_THEMES[status] || 'gray'"
		size="sm"
		variant="subtle"
	/>
</template>

<script setup>
import { Badge } from "frappe-ui"
import { CONTRACT_STATUS_THEMES } from "./contractFormat.js"

defineProps({ status: { type: String, required: true } })
</script>
