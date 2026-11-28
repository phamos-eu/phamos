<template>
	<div :class="[CUSTOMER_COLS, 'border-b border-outline-gray-1 px-4 py-2.5 text-sm', expanded ? 'bg-surface-gray-1' : '']">
		<button
			type="button"
			class="flex h-6 w-6 items-center justify-center rounded text-ink-gray-6 hover:bg-surface-gray-2"
			:aria-expanded="expanded"
			:title="expanded ? 'Hide invoices' : 'Show invoices'"
			@click="emit('toggle')"
		>
			<FeatherIcon :name="expanded ? 'chevron-down' : 'chevron-right'" class="h-4 w-4" />
		</button>
		<button type="button" class="min-w-0 text-left" @click="emit('toggle')">
			<div class="truncate font-medium text-ink-gray-9" :title="customer.customer_name">{{ customer.customer_name }}</div>
			<div class="truncate text-xs text-ink-gray-5">
				<template v-if="customer.customer_name !== customer.customer">{{ customer.customer }} · </template>{{ pluralize(customer.invoice_count, "invoice", "invoices") }}
			</div>
		</button>
		<ReceivableContact :contact="customer.contact" />
		<div class="text-right">
			<div class="tabular-nums font-semibold text-ink-gray-9">{{ money(customer.outstanding) }}</div>
			<div v-if="customer.credits" class="text-xs tabular-nums text-ink-blue-3" title="Unallocated payments and credit notes, already deducted">
				{{ money(customer.credits) }} credit
			</div>
		</div>
		<div class="text-right tabular-nums" :class="customer.overdue ? 'font-medium text-ink-red-4' : 'text-ink-gray-4'">
			{{ customer.overdue ? money(customer.overdue) : "—" }}
		</div>
		<div class="text-right tabular-nums" :class="customer.not_due ? 'text-ink-gray-8' : 'text-ink-gray-4'">
			{{ customer.not_due ? money(customer.not_due) : "—" }}
		</div>
		<div class="text-right tabular-nums" :class="customer.oldest_days_overdue ? 'text-ink-red-4' : 'text-ink-gray-4'">
			{{ customer.oldest_days_overdue ? `${customer.oldest_days_overdue} d` : "—" }}
		</div>
		<div class="flex h-2.5 overflow-hidden rounded-full bg-surface-gray-2" :title="agingTitle">
			<div
				v-for="segment in segments"
				:key="segment.key"
				class="h-full"
				:style="{ width: `${segment.share}%`, background: BUCKET_COLORS[segment.key] }"
			/>
		</div>
		<ReceivableLastContact :last="customer.last_contact" />
		<a
			:href="deskUrl"
			class="flex justify-center text-ink-gray-5 hover:text-ink-gray-9"
			:title="`Open customer ${customer.customer} in Desk`"
			@click.prevent="openDesk(deskUrl)"
		>
			<FeatherIcon name="external-link" class="h-4 w-4" />
		</a>
	</div>
	<div v-if="expanded" class="col-span-10 border-b border-outline-gray-2 bg-surface-gray-1 pb-2 pl-10 pr-2">
		<div class="flex flex-wrap gap-x-4 gap-y-1 py-2 text-xs text-ink-gray-6">
			<span v-for="key in BUCKET_ORDER" :key="key" :class="customer.buckets[key] ? 'text-ink-gray-8' : 'text-ink-gray-4'">
				<span class="mr-1 inline-block h-2 w-2 rounded-full" :style="{ background: BUCKET_COLORS[key] }" />
				{{ BUCKET_SHORT[key] }}: <span class="tabular-nums">{{ money(customer.buckets[key]) }}</span>
			</span>
		</div>
		<div :class="[NESTED_INVOICE_GRID, 'rounded-md border border-outline-gray-2 bg-surface-white']">
			<ReceivableInvoiceRow v-for="item in invoices" :key="item.voucher_no" :item="item" :currency="currency" nested />
			<p v-if="!invoices.length" class="col-span-7 px-4 py-3 text-xs text-ink-gray-5">No invoice matches the filters.</p>
		</div>
	</div>
</template>

<script setup>
import { computed } from "vue"
import { FeatherIcon } from "frappe-ui"
import { openDesk } from "@spa/utils/appWindow.js"
import { pluralize } from "@spa/utils/dashboardFormat.js"
import { deskRecordUrl } from "@spa/utils/deskUrl.js"
import { BUCKET_COLORS, BUCKET_ORDER, BUCKET_SHORT, CUSTOMER_COLS, NESTED_INVOICE_GRID, formatMoney } from "../receivableColumns"
import ReceivableContact from "./ReceivableContact.vue"
import ReceivableInvoiceRow from "./ReceivableInvoiceRow.vue"
import ReceivableLastContact from "./ReceivableLastContact.vue"

const props = defineProps({
	customer: { type: Object, required: true },
	// This customer's items that pass the current filters.
	invoices: { type: Array, default: () => [] },
	currency: { type: String, default: "EUR" },
	expanded: { type: Boolean, default: false },
})

const emit = defineEmits(["toggle"])

const deskUrl = computed(() => deskRecordUrl("Customer", props.customer.customer))

function money(value) {
	return formatMoney(value, props.currency)
}

const segments = computed(() => {
	const amounts = BUCKET_ORDER.map((key) => ({ key, amount: Math.max(0, Number(props.customer.buckets[key]) || 0) }))
	const total = amounts.reduce((sum, a) => sum + a.amount, 0)
	if (!total) return []
	return amounts.filter((a) => a.amount).map((a) => ({ ...a, share: (a.amount / total) * 100 }))
})

const agingTitle = computed(() =>
	BUCKET_ORDER.filter((key) => props.customer.buckets[key])
		.map((key) => `${BUCKET_SHORT[key]}: ${money(props.customer.buckets[key])}`)
		.join("\n")
)
</script>
