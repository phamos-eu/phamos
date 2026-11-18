<template>
	<!-- Where an Issue stands: Reported → In GitLab → In Progress → Testing → Done (#1671). -->
	<ol class="flex items-center gap-1" :aria-label="__('Stage: {0}', [__(stage)])">
		<li v-for="(name, index) in stages" :key="name" class="flex items-center gap-1">
			<span
				class="h-2 w-2 flex-shrink-0 rounded-full"
				:class="index < current ? 'bg-surface-gray-7' : index === current ? 'ring-2 ring-outline-gray-4 bg-surface-gray-7' : 'bg-surface-gray-3'"
				:title="__(name)"
			/>
			<span v-if="!compact && index === current" class="whitespace-nowrap text-xs font-medium text-ink-gray-8">{{ __(name) }}</span>
			<span v-if="index < stages.length - 1" class="h-px w-3 bg-outline-gray-2" aria-hidden="true" />
		</li>
		<li v-if="compact" class="ml-1 whitespace-nowrap text-xs text-ink-gray-7">{{ __(stage) }}</li>
	</ol>
</template>

<script setup>
import { computed } from "vue"
import { __ } from "@spa/utils/i18n.js"

const props = defineProps({
	stage: { type: String, required: true },
	stages: { type: Array, default: () => ["Reported", "In GitLab", "In Progress", "Testing", "Done"] },
	compact: { type: Boolean, default: false },
})

const current = computed(() => Math.max(0, props.stages.indexOf(props.stage)))
</script>
