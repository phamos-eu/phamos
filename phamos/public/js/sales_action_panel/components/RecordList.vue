<script setup>
import { computed, ref } from "vue";
import { statusTone, VIEWS } from "../mockData";

const props = defineProps({
	view: String,
	records: Array,
	selectedName: String,
});

const emit = defineEmits(["select"]);

const search = ref("");

const viewLabel = computed(() => VIEWS.find((v) => v.key === props.view)?.label || props.view);

const filtered = computed(() => {
	const q = search.value.trim().toLowerCase();
	if (!q) return props.records;
	return props.records.filter((r) =>
		[r.title, r.name, r.organization, r.party, r.email, r.status, r.owner]
			.filter(Boolean)
			.some((v) => String(v).toLowerCase().includes(q))
	);
});

function subtitle(r) {
	if (props.view === "leads") return r.organization || r.email;
	if (props.view === "opportunities") return r.party;
	if (props.view === "customers") return r.territory;
	if (props.view === "quotations") return r.party;
	if (props.view === "contacts") return r.organization || r.email;
	if (props.view === "addresses") return `${r.city || ""}, ${r.country || ""}`.replace(/^, /, "");
	return r.notes || "";
}

function amountLabel(r) {
	if (r.amount == null) return null;
	return new Intl.NumberFormat("de-DE", {
		style: "currency",
		currency: r.currency || "EUR",
		maximumFractionDigits: 0,
	}).format(r.amount);
}
</script>

<template>
	<div class="sap-list">
		<div class="sap-list__head">
			<div class="sap-list__title-row">
				<h2 class="sap-list__title">{{ viewLabel }}</h2>
				<span class="sap-list__count">{{ filtered.length }}</span>
			</div>
			<div class="sap-list__search">
				<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
					<circle cx="11" cy="11" r="7" />
					<path d="M21 21l-4.3-4.3" />
				</svg>
				<input v-model="search" type="search" :placeholder="`Search ${viewLabel.toLowerCase()}…`" />
			</div>
		</div>

		<div class="sap-list__body">
			<button
				v-for="record in filtered"
				:key="record.name"
				class="sap-list__item"
				:class="{ 'sap-list__item--active': selectedName === record.name }"
				@click="emit('select', record.name)"
			>
				<div class="sap-list__item-top">
					<span class="sap-list__item-title">{{ record.title }}</span>
					<span
						v-if="record.status"
						class="sap-pill"
						:class="`sap-pill--${statusTone(record.status)}`"
					>
						{{ record.status }}
					</span>
				</div>
				<div class="sap-list__item-sub">{{ subtitle(record) }}</div>
				<div class="sap-list__item-meta">
					<span>{{ record.owner }}</span>
					<span v-if="amountLabel(record)" class="sap-list__amount">{{ amountLabel(record) }}</span>
					<span v-else>{{ record.modified }}</span>
				</div>
			</button>

			<p v-if="!filtered.length" class="sap-list__empty">No records match your search.</p>
		</div>
	</div>
</template>

<style scoped>
.sap-list {
	display: flex;
	flex-direction: column;
	height: 100%;
	background: var(--card-bg);
}
.sap-list__head {
	padding: 14px 14px 10px;
	border-bottom: 1px solid var(--border-color);
	flex-shrink: 0;
}
.sap-list__title-row {
	display: flex;
	align-items: center;
	gap: 8px;
	margin-bottom: 10px;
}
.sap-list__title {
	margin: 0;
	font-size: 15px;
	font-weight: 700;
	color: var(--text-color);
	letter-spacing: -0.02em;
}
.sap-list__count {
	font-size: 11px;
	font-weight: 600;
	background: var(--control-bg);
	color: var(--text-muted);
	border-radius: 10px;
	padding: 1px 7px;
}
.sap-list__search {
	display: flex;
	align-items: center;
	gap: 8px;
	padding: 8px 10px;
	border: 1px solid var(--border-color);
	border-radius: 8px;
	background: var(--bg-color);
	color: var(--text-muted);
}
.sap-list__search input {
	border: none;
	outline: none;
	background: transparent;
	width: 100%;
	font-size: 13px;
	color: var(--text-color);
	font-family: inherit;
}
.sap-list__body {
	flex: 1;
	overflow-y: auto;
	padding: 6px;
}
.sap-list__item {
	display: block;
	width: 100%;
	text-align: left;
	border: 1px solid transparent;
	background: transparent;
	border-radius: 8px;
	padding: 10px 12px;
	cursor: pointer;
	margin-bottom: 2px;
	transition: background 0.1s, border-color 0.1s;
}
.sap-list__item:hover {
	background: var(--control-bg);
}
.sap-list__item--active {
	background: var(--blue-50, #eff6ff);
	border-color: var(--blue-200, #bfdbfe);
}
.sap-list__item-top {
	display: flex;
	align-items: flex-start;
	justify-content: space-between;
	gap: 8px;
}
.sap-list__item-title {
	font-size: 13px;
	font-weight: 600;
	color: var(--text-color);
	line-height: 1.3;
}
.sap-list__item-sub {
	margin-top: 3px;
	font-size: 12px;
	color: var(--text-muted);
	white-space: nowrap;
	overflow: hidden;
	text-overflow: ellipsis;
}
.sap-list__item-meta {
	margin-top: 6px;
	display: flex;
	justify-content: space-between;
	gap: 8px;
	font-size: 11px;
	color: var(--text-muted);
}
.sap-list__amount {
	font-weight: 600;
	color: var(--text-color);
}
.sap-list__empty {
	padding: 28px 12px;
	text-align: center;
	color: var(--text-muted);
	font-size: 13px;
}
.sap-pill {
	font-size: 10.5px;
	font-weight: 700;
	padding: 2px 7px;
	border-radius: 999px;
	flex-shrink: 0;
	text-transform: uppercase;
	letter-spacing: 0.03em;
}
.sap-pill--blue {
	background: #dbeafe;
	color: #1d4ed8;
}
.sap-pill--cyan {
	background: #cffafe;
	color: #0e7490;
}
.sap-pill--purple {
	background: #ede9fe;
	color: #6d28d9;
}
.sap-pill--orange {
	background: #ffedd5;
	color: #c2410c;
}
.sap-pill--amber {
	background: #fef3c7;
	color: #b45309;
}
.sap-pill--green {
	background: #dcfce7;
	color: #15803d;
}
.sap-pill--gray {
	background: var(--control-bg);
	color: var(--text-muted);
}
</style>
