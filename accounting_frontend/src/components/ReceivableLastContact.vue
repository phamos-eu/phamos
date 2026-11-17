<template>
	<div class="min-w-0 text-xs">
		<template v-if="last">
			<div class="text-ink-gray-8">{{ formatDate(last.date) }}</div>
			<div class="truncate" :class="last.kind === 'dunning' ? 'text-ink-red-4' : 'text-ink-gray-5'">{{ lastContactKind(last) }}</div>
		</template>
		<span v-else class="text-ink-gray-4">Never</span>
	</div>
</template>

<script setup>
import { formatDate } from "@spa/utils/datetime.js"
import { lastContactKind } from "../receivableColumns"

defineProps({
	// {date, kind: "email" | "dunning", level} from get_receivables, or null.
	last: { type: Object, default: null },
})
</script>
