<template>
	<!-- Left column of the Roadmap (#2034): one label per row, at the row's height from
	     rowHeights. The parent keeps it sticky while the chart scrolls sideways. -->
	<div class="roadmap-row-list" role="rowgroup">
		<div
			v-for="(row, idx) in rows"
			:key="row.name"
			class="roadmap-row-list__row"
			role="rowheader"
			:style="{ height: `${layout[idx]?.height || 0}px` }"
			:title="row.label || row.name"
		>
			<span class="truncate">{{ row.label || row.name }}</span>
			<span v-if="row.sublabel" class="roadmap-row-list__sub truncate">{{ row.sublabel }}</span>
		</div>
	</div>
</template>

<script setup>
defineProps({
	/** [{ name, label, sublabel? }] */
	rows: { type: Array, default: () => [] },
	/** rowHeights(rows), in the same order */
	layout: { type: Array, default: () => [] },
})
</script>

<style scoped>
.roadmap-row-list__row {
	display: flex;
	flex-direction: column;
	justify-content: center;
	min-width: 0;
	padding: 0 8px;
	border-bottom: 1px solid var(--outline-gray-1);
	color: var(--ink-gray-8);
	font-size: 12px;
	line-height: 1.25;
}

.roadmap-row-list__sub {
	color: var(--ink-gray-5);
	font-size: 10px;
}
</style>
