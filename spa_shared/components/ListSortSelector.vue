<template>
	<!--
		Sort field toggles: first click selects the field, another click cycles asc/desc.
		Arrow is shown on the active field. A `oneWay` option sorts descending only; another click
		emits "clear" so the parent returns to its default sort (#1796).
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
				sortBy !== option.value
					? `Sort by ${option.label}`
					: option.oneWay
						? `Sorted by ${option.label} — click to stop sorting by it`
						: sortOrder === 'desc'
							? 'Descending — click to sort ascending'
							: 'Ascending — click to sort descending'
			"
			@click="onSelect(option)"
		>
			<span>{{ option.label }}</span>
			<!-- A oneWay option has no direction to show: the active background says it sorts. -->
			<FeatherIcon
				v-if="sortBy === option.value && !option.oneWay"
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
	/** [{ label, value, oneWay? }] */
	options: { type: Array, default: () => [] },
	/** Separate buttons instead of a joined control */
	standalone: { type: Boolean, default: false },
})

const emit = defineEmits(["update:sortBy", "update:sortOrder", "change", "clear"])

function onSelect({ value, oneWay }) {
	if (oneWay) {
		if (value === props.sortBy) {
			emit("clear")
			return
		}
		emit("update:sortBy", value)
		emit("update:sortOrder", "desc")
		emit("change", { sortBy: value, sortOrder: "desc" })
		return
	}
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
