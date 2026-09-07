<template>
	<!--
		Sort field toggles: first click selects the field, another click cycles asc/desc.
		Arrow is shown on the active field.
	-->
	<div
		class="inline-flex overflow-hidden rounded-md border border-gray-300 bg-white dark:border-gray-600 dark:bg-gray-800"
	>
		<button
			v-for="(option, index) in options"
			:key="option.value"
			type="button"
			class="flex h-7 items-center gap-1 px-2.5 text-xs font-medium transition"
			:class="[
				index < options.length - 1 ? 'border-r border-gray-300 dark:border-gray-600' : '',
				sortBy === option.value
					? 'bg-gray-100 text-gray-900 dark:bg-gray-700 dark:text-gray-100'
					: 'text-gray-600 hover:bg-gray-50 dark:text-gray-300 dark:hover:bg-gray-700',
			]"
			:title="
				sortBy === option.value
					? sortOrder === 'desc'
						? 'Descending — click to sort ascending'
						: 'Ascending — click to sort descending'
					: `Sort by ${option.label}`
			"
			@click="onSelect(option.value)"
		>
			<span>{{ option.label }}</span>
			<FeatherIcon
				v-if="sortBy === option.value"
				:name="sortOrder === 'desc' ? 'arrow-down' : 'arrow-up'"
				class="h-3.5 w-3.5"
			/>
		</button>
	</div>
</template>

<script setup>
const props = defineProps({
	/** Current sort field value (e.g. modified, creation) */
	sortBy: { type: String, required: true },
	/** asc | desc */
	sortOrder: { type: String, required: true },
	/** [{ label, value }] */
	options: { type: Array, default: () => [] },
})

const emit = defineEmits(["update:sortBy", "update:sortOrder", "change"])

function onSelect(value) {
	if (value === props.sortBy) {
		const next = props.sortOrder === "desc" ? "asc" : "desc"
		emit("update:sortOrder", next)
		emit("change", { sortBy: props.sortBy, sortOrder: next })
		return
	}
	emit("update:sortBy", value)
	emit("change", { sortBy: value, sortOrder: props.sortOrder })
}
</script>
