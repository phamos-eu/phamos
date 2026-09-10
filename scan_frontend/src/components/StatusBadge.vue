<template>
	<span class="scan-status-chip" :class="statusClass(status)">
		<span
			v-if="status === 'Processing'"
			class="inline-block h-1.5 w-1.5 rounded-full bg-blue-600 animate-pulse"
		/>
		{{ status || "Draft" }}
	</span>
</template>

<script setup>
import { statusClass } from "@/utils/upload"

defineProps({
	status: { type: String, default: "Draft" },
})
</script>
