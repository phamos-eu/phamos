<template>
	<div
		class="flex flex-nowrap items-center justify-center gap-2"
		role="group"
		aria-label="Filter by linked DocType"
	>
		<button
			v-for="doctype in doctypes"
			:key="doctype"
			type="button"
			class="flex h-7 shrink-0 items-center gap-1 rounded-md border px-2 text-xs font-medium transition"
			:class="
				isSelected(doctype)
					? 'border-outline-gray-3 bg-surface-gray-7 text-ink-white'
					: 'border-outline-gray-2 text-ink-gray-6 opacity-70 hover:opacity-100'
			"
			:aria-pressed="isSelected(doctype)"
			:title="`Show only checklists on a ${doctype}`"
			@click="toggle(doctype)"
		>
			<FeatherIcon :name="doctype === 'Issue' ? 'inbox' : 'check-square'" class="h-3.5 w-3.5" />
			{{ doctype }}
		</button>
	</div>
</template>

<script setup>
import { computed } from "vue"

const props = defineProps({
	/** Currently selected parent DocTypes (empty = all) */
	modelValue: { type: Array, default: () => [] },
	doctypes: { type: Array, default: () => ["Issue", "Task"] },
})

const emit = defineEmits(["update:modelValue"])

const selected = computed(() => new Set(props.modelValue || []))

function isSelected(doctype) {
	return selected.value.has(doctype)
}

function toggle(doctype) {
	const next = new Set(selected.value)
	if (next.has(doctype)) next.delete(doctype)
	else next.add(doctype)
	emit("update:modelValue", [...next])
}
</script>
