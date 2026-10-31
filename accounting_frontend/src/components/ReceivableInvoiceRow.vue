<template>
	<div :class="[nested ? NESTED_INVOICE_COLS : INVOICE_COLS, 'border-b border-outline-gray-1 px-4 py-2 text-sm']">
		<div class="min-w-0">
			<a
				:href="deskUrl"
				class="block truncate font-medium text-ink-gray-9 hover:underline"
				:title="`Open ${item.voucher_type} ${item.voucher_no} in Desk`"
				@click.prevent="openDesk(deskUrl)"
			>
				{{ item.voucher_no }}
			</a>
			<div class="flex min-w-0 items-center gap-1.5 truncate text-xs text-ink-gray-5">
				<Badge v-if="item.kind === 'credit'" theme="blue" size="sm" variant="subtle" :label="creditLabel" />
				<span v-else-if="item.status">{{ item.status }}</span>
				<span v-if="item.po_no" class="truncate" :title="`PO ${item.po_no}`">· PO {{ item.po_no }}</span>
			</div>
		</div>
		<div v-if="!nested" class="min-w-0">
			<div class="truncate text-ink-gray-8" :title="item.customer_name">{{ item.customer_name }}</div>
			<div v-if="item.customer_name !== item.customer" class="truncate text-xs text-ink-gray-5">{{ item.customer }}</div>
		</div>
		<ReceivableContact :contact="item.contact" />
		<div class="min-w-0">
			<div class="text-ink-gray-8">{{ item.due_date ? formatDate(item.due_date) : "—" }}</div>
			<div class="truncate text-xs" :class="item.days_overdue > 0 ? 'text-ink-red-4' : 'text-ink-gray-5'">{{ dueText(item) }}</div>
		</div>
		<div class="text-right">
			<div class="tabular-nums font-medium" :class="item.kind === 'credit' ? 'text-ink-blue-3' : 'text-ink-gray-9'">
				{{ money(item.outstanding) }}
			</div>
			<div v-if="item.document_currency" class="text-xs tabular-nums text-ink-gray-5">
				{{ formatMoney(item.document_outstanding, item.document_currency) }}
			</div>
		</div>
		<div>
			<Badge v-if="item.bucket" :theme="BUCKET_BADGE[item.bucket]" size="sm" variant="subtle" :label="BUCKET_SHORT[item.bucket]" />
		</div>
		<ReceivableLastContact :last="item.last_contact" />
		<a
			:href="deskUrl"
			class="flex justify-center text-ink-gray-5 hover:text-ink-gray-9"
			:title="`Open ${item.voucher_no} in Desk`"
			@click.prevent="openDesk(deskUrl)"
		>
			<FeatherIcon name="external-link" class="h-4 w-4" />
		</a>
	</div>
</template>

<script setup>
import { computed } from "vue"
import { Badge, FeatherIcon } from "frappe-ui"
import { openDesk } from "@spa/utils/appWindow.js"
import { formatDate } from "@spa/utils/datetime.js"
import { deskRecordUrl } from "@spa/utils/deskUrl.js"
import { BUCKET_BADGE, BUCKET_SHORT, INVOICE_COLS, NESTED_INVOICE_COLS, dueText } from "../receivableColumns"
import { formatMoney } from "../statsFormat"
import ReceivableContact from "./ReceivableContact.vue"
import ReceivableLastContact from "./ReceivableLastContact.vue"

const props = defineProps({
	item: { type: Object, required: true },
	currency: { type: String, default: "EUR" },
	// Shown under its customer: no Customer column.
	nested: { type: Boolean, default: false },
})

const deskUrl = computed(() => deskRecordUrl(props.item.voucher_type, props.item.voucher_no))
const creditLabel = computed(() => (props.item.voucher_type === "Sales Invoice" ? "Credit note" : props.item.voucher_type))

function money(value) {
	return formatMoney(value, props.currency)
}
</script>
