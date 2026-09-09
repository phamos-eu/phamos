<template>
	<!--
		Sort field toggles: first click selects the field, another click cycles asc/desc.
		Arrow is shown on the active field.
		standalone: separate bordered buttons (for one control per column).
	-->
	<div
		:class="
			standalone
				? 'flex items-center gap-2'
				: 'inline-flex overflow-hidden rounded-md border border-outline-gray-2 bg-surface-white'
		"
	>
		<button
			v-for="(option, index) in options"
			:key="option.value"
			type="button"
			class="flex h-7 items-center gap-1 px-2.5 text-xs font-medium transition"
			:class="[
				standalone
					? [
							'rounded-md border border-outline-gray-2 bg-surface-white',
							sortBy === option.value
								? 'bg-surface-gray-2 text-ink-gray-9'
								: 'text-ink-gray-6 hover:bg-surface-gray-2',
						]
					: [
							index < options.length - 1 ? 'border-r border-outline-gray-2' : '',
							sortBy === option.value
								? 'bg-surface-gray-2 text-ink-gray-9'
								: 'text-ink-gray-6 hover:bg-surface-gray-2',
						],
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
	/** Separate buttons instead of a joined control */
	standalone: { type: Boolean, default: false },
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
