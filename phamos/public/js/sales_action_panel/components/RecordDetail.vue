<script setup>
import { computed } from "vue";
import { statusTone } from "../mockData";

const props = defineProps({
	view: String,
	record: Object,
	relatedContacts: Array,
	relatedAddresses: Array,
	relatedQuotations: Array,
});

const emit = defineEmits(["open-related"]);

const fields = computed(() => {
	const r = props.record;
	if (!r) return [];
	const common = [
		{ label: "ID", value: r.name },
		{ label: "Owner", value: r.owner },
		{ label: "Modified", value: r.modified },
	];
	if (props.view === "leads") {
		return [
			{ label: "Organization", value: r.organization },
			{ label: "Email", value: r.email },
			{ label: "Phone", value: r.phone },
			{ label: "Source", value: r.source },
			{ label: "Territory", value: r.territory },
			...common,
		];
	}
	if (props.view === "opportunities") {
		return [
			{ label: "Party", value: r.party },
			{ label: "Type", value: r.opportunity_type },
			{
				label: "Amount",
				value: formatMoney(r.amount, r.currency),
			},
			{ label: "Probability", value: `${r.probability}%` },
			{ label: "Expected Closing", value: r.expected_closing },
			...common,
		];
	}
	if (props.view === "customers") {
		return [
			{ label: "Type", value: r.customer_type },
			{ label: "Email", value: r.email },
			{ label: "Phone", value: r.phone },
			{ label: "Territory", value: r.territory },
			...common,
		];
	}
	if (props.view === "quotations") {
		return [
			{ label: "Party", value: r.party },
			{ label: "Opportunity", value: r.opportunity },
			{ label: "Amount", value: formatMoney(r.amount, r.currency) },
			{ label: "Valid Till", value: r.valid_till },
			...common,
		];
	}
	if (props.view === "contacts") {
		return [
			{ label: "Organization", value: r.organization },
			{ label: "Designation", value: r.designation },
			{ label: "Email", value: r.email },
			{ label: "Phone", value: r.phone },
			...common,
		];
	}
	if (props.view === "addresses") {
		return [
			{ label: "Organization", value: r.organization },
			{ label: "Type", value: r.address_type },
			{ label: "Address", value: r.address_line1 },
			{ label: "City", value: r.city },
			{ label: "PIN", value: r.pincode },
			{ label: "Country", value: r.country },
			...common,
		];
	}
	return common;
});

function formatMoney(amount, currency) {
	if (amount == null) return "—";
	return new Intl.NumberFormat("de-DE", {
		style: "currency",
		currency: currency || "EUR",
		maximumFractionDigits: 0,
	}).format(amount);
}
</script>

<template>
	<div v-if="!record" class="sap-detail sap-detail--empty">
		<div class="sap-detail__empty-inner">
			<svg width="36" height="36" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.4">
				<path d="M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z" />
			</svg>
			<p>Select a record to inspect details, linked contacts, and addresses.</p>
		</div>
	</div>

	<div v-else class="sap-detail">
		<header class="sap-detail__header">
			<div class="sap-detail__header-main">
				<div class="sap-detail__eyebrow">{{ view }}</div>
				<h2 class="sap-detail__title">{{ record.title }}</h2>
				<p v-if="record.notes" class="sap-detail__notes">{{ record.notes }}</p>
			</div>
			<span
				v-if="record.status"
				class="sap-pill"
				:class="`sap-pill--${statusTone(record.status)}`"
			>
				{{ record.status }}
			</span>
		</header>

		<section class="sap-detail__section">
			<h3 class="sap-detail__section-title">Details</h3>
			<div class="sap-detail__grid">
				<div v-for="field in fields" :key="field.label" class="sap-detail__field">
					<div class="sap-detail__label">{{ field.label }}</div>
					<div class="sap-detail__value">{{ field.value || "—" }}</div>
				</div>
			</div>
		</section>

		<section v-if="relatedContacts?.length" class="sap-detail__section">
			<h3 class="sap-detail__section-title">Contacts</h3>
			<div class="sap-detail__links">
				<button
					v-for="c in relatedContacts"
					:key="c.name"
					class="sap-detail__link"
					@click="emit('open-related', { view: 'contacts', name: c.name })"
				>
					<span class="sap-detail__link-title">{{ c.title }}</span>
					<span class="sap-detail__link-sub">{{ c.designation || c.email }}</span>
				</button>
			</div>
		</section>

		<section v-if="relatedAddresses?.length" class="sap-detail__section">
			<h3 class="sap-detail__section-title">Addresses</h3>
			<div class="sap-detail__links">
				<button
					v-for="a in relatedAddresses"
					:key="a.name"
					class="sap-detail__link"
					@click="emit('open-related', { view: 'addresses', name: a.name })"
				>
					<span class="sap-detail__link-title">{{ a.title }}</span>
					<span class="sap-detail__link-sub">
						{{ a.address_line1 }}, {{ a.city }}
					</span>
				</button>
			</div>
		</section>

		<section v-if="relatedQuotations?.length" class="sap-detail__section">
			<h3 class="sap-detail__section-title">Quotations</h3>
			<div class="sap-detail__links">
				<button
					v-for="q in relatedQuotations"
					:key="q.name"
					class="sap-detail__link"
					@click="emit('open-related', { view: 'quotations', name: q.name })"
				>
					<span class="sap-detail__link-title">{{ q.title }}</span>
					<span class="sap-detail__link-sub">{{ formatMoney(q.amount, q.currency) }}</span>
				</button>
			</div>
		</section>

		<section class="sap-detail__section">
			<h3 class="sap-detail__section-title">Activity</h3>
			<div class="sap-detail__timeline">
				<div class="sap-detail__event">
					<span class="sap-detail__event-dot"></span>
					<div>
						<div class="sap-detail__event-title">Record opened in Sales Action Panel</div>
						<div class="sap-detail__event-sub">Click-dummy activity feed</div>
					</div>
				</div>
				<div class="sap-detail__event">
					<span class="sap-detail__event-dot"></span>
					<div>
						<div class="sap-detail__event-title">Last modified {{ record.modified }}</div>
						<div class="sap-detail__event-sub">Owned by {{ record.owner }}</div>
					</div>
				</div>
			</div>
		</section>
	</div>
</template>

<style scoped>
.sap-detail {
	height: 100%;
	overflow-y: auto;
	background: var(--bg-color);
}
.sap-detail--empty {
	display: flex;
	align-items: center;
	justify-content: center;
}
.sap-detail__empty-inner {
	text-align: center;
	color: var(--text-muted);
	max-width: 260px;
	padding: 24px;
}
.sap-detail__empty-inner p {
	margin: 12px 0 0;
	font-size: 13px;
	line-height: 1.45;
}
.sap-detail__header {
	display: flex;
	justify-content: space-between;
	gap: 16px;
	padding: 20px 22px 16px;
	border-bottom: 1px solid var(--border-color);
	background: var(--card-bg);
}
.sap-detail__eyebrow {
	font-size: 10.5px;
	font-weight: 700;
	text-transform: uppercase;
	letter-spacing: 0.08em;
	color: var(--text-muted);
	margin-bottom: 4px;
}
.sap-detail__title {
	margin: 0;
	font-size: 20px;
	font-weight: 700;
	letter-spacing: -0.03em;
	color: var(--text-color);
	line-height: 1.25;
}
.sap-detail__notes {
	margin: 8px 0 0;
	font-size: 13px;
	color: var(--text-muted);
	line-height: 1.45;
	max-width: 560px;
}
.sap-detail__section {
	padding: 18px 22px;
	border-bottom: 1px solid var(--border-color);
}
.sap-detail__section-title {
	margin: 0 0 12px;
	font-size: 11px;
	font-weight: 700;
	text-transform: uppercase;
	letter-spacing: 0.08em;
	color: var(--text-muted);
}
.sap-detail__grid {
	display: grid;
	grid-template-columns: repeat(2, minmax(0, 1fr));
	gap: 14px 18px;
}
.sap-detail__label {
	font-size: 11px;
	color: var(--text-muted);
	margin-bottom: 3px;
}
.sap-detail__value {
	font-size: 13.5px;
	font-weight: 500;
	color: var(--text-color);
	word-break: break-word;
}
.sap-detail__links {
	display: flex;
	flex-direction: column;
	gap: 6px;
}
.sap-detail__link {
	display: flex;
	flex-direction: column;
	align-items: flex-start;
	gap: 2px;
	width: 100%;
	text-align: left;
	padding: 10px 12px;
	border: 1px solid var(--border-color);
	border-radius: 8px;
	background: var(--card-bg);
	cursor: pointer;
	transition: border-color 0.12s, background 0.12s;
}
.sap-detail__link:hover {
	border-color: var(--primary);
	background: var(--blue-50, #eff6ff);
}
.sap-detail__link-title {
	font-size: 13px;
	font-weight: 600;
	color: var(--text-color);
}
.sap-detail__link-sub {
	font-size: 12px;
	color: var(--text-muted);
}
.sap-detail__timeline {
	display: flex;
	flex-direction: column;
	gap: 14px;
}
.sap-detail__event {
	display: flex;
	gap: 10px;
	align-items: flex-start;
}
.sap-detail__event-dot {
	width: 8px;
	height: 8px;
	margin-top: 5px;
	border-radius: 50%;
	background: var(--primary);
	flex-shrink: 0;
}
.sap-detail__event-title {
	font-size: 13px;
	font-weight: 500;
	color: var(--text-color);
}
.sap-detail__event-sub {
	font-size: 12px;
	color: var(--text-muted);
	margin-top: 2px;
}
.sap-pill {
	font-size: 10.5px;
	font-weight: 700;
	padding: 3px 8px;
	border-radius: 999px;
	height: fit-content;
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
@media (max-width: 900px) {
	.sap-detail__grid {
		grid-template-columns: 1fr;
	}
}
</style>
