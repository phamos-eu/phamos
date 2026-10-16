<template>
	<div class="flex min-h-0 flex-1 flex-col lg:flex-row">
		<div
			class="flex min-w-0 flex-col gap-4 overflow-y-auto border-b border-outline-gray-2 p-5 lg:w-3/5 lg:flex-none lg:border-b-0 lg:border-r"
		>
			<!-- Header -->
			<div class="flex items-start justify-between gap-3">
				<div class="min-w-0 flex-1">
					<div class="flex items-center gap-2 text-xs font-semibold text-ink-gray-5">
						<span>{{ receipt.name }}</span>
						<span class="rounded bg-surface-gray-2 px-1.5 py-0.5 text-ink-gray-7">{{ receipt.status }}</span>
						<span v-if="receipt.sent_to_datev" class="rounded bg-surface-blue-2 px-1.5 py-0.5 text-ink-blue-3">DATEV</span>
						<span v-if="receipt.is_paid" class="rounded bg-surface-green-2 px-1.5 py-0.5 text-ink-green-3">Paid</span>
						<span class="ml-auto text-[11px] font-normal" :class="saveStateClass">{{ saveStateText }}</span>
					</div>
					<input
						v-model="autosave.draft.title"
						:disabled="readonly"
						class="mt-1 w-full rounded border border-transparent bg-transparent px-1 py-0.5 text-lg font-semibold text-ink-gray-9 hover:border-outline-gray-2 focus:border-outline-gray-3 focus:outline-none"
						@focus="autosave.setFocused('title', true)"
						@blur="autosave.setFocused('title', false)"
					/>
				</div>
				<button type="button" class="rounded-md px-2 py-1 text-sm text-ink-gray-5 hover:bg-surface-gray-2" @click="emit('close')">
					Close
				</button>
			</div>
			<DocSyncBanner :autosave="autosave" />

			<!-- AI reading -->
			<div v-if="receipt.ai?.summary || receipt.ai?.flags?.length" class="rounded-md border border-outline-gray-2 bg-surface-gray-1 px-3 py-2 text-sm">
				<div class="flex items-center justify-between gap-2">
					<span class="font-medium text-ink-gray-8">{{ receipt.ai.summary || "AI reading" }}</span>
					<span
						v-if="receipt.ai.confidence"
						class="rounded px-1.5 py-0.5 text-xs font-medium"
						:class="confidenceClass(receipt.ai.confidence)"
						title="How sure the AI is about number, date, supplier and amount"
					>
						AI {{ Math.round(receipt.ai.confidence) }} %
					</span>
				</div>
				<ul v-if="receipt.ai.flags?.length" class="mt-1 space-y-0.5">
					<li
						v-for="(flag, i) in receipt.ai.flags"
						:key="i"
						:class="flag.severity === 'block' ? 'text-ink-red-4' : flag.severity === 'warn' ? 'text-ink-amber-3' : 'text-ink-gray-6'"
					>
						{{ flag.message }}
					</li>
				</ul>
			</div>
			<div v-if="receipt.has_pdf" class="text-xs" :class="extractStatus === 'failed' ? 'text-ink-red-4' : 'text-ink-gray-5'">
				<template v-if="extractStatus === 'running'">The AI is reading the PDF…</template>
				<template v-else-if="extractStatus === 'done'">
					Read by the AI<span v-if="extractUpdatedCount"> · {{ extractUpdatedCount }} empty field(s) filled</span>
				</template>
				<template v-else-if="extractStatus === 'failed'">{{ extractErrorMessage }}</template>
				<template v-else>Not read by the AI yet.</template>
			</div>

			<!-- Supplier -->
			<section>
				<h3 class="mb-1.5 text-xs font-semibold uppercase tracking-wide text-ink-gray-5">Supplier</h3>
				<FrappeLink
					v-model="autosave.draft.supplier"
					doctype="Supplier"
					placeholder="Pick a supplier"
					:disabled="readonly"
				/>
				<div v-if="!autosave.draft.supplier && suggestions" class="mt-2 space-y-1.5 text-sm">
					<p v-if="suggestions.extracted?.supplier_name" class="text-ink-gray-6">
						The AI read <span class="font-medium text-ink-gray-8">{{ suggestions.extracted.supplier_name }}</span>
						<span v-if="suggestions.extracted.tax_id"> · {{ suggestions.extracted.tax_id }}</span>
					</p>
					<div class="flex flex-wrap items-center gap-1.5">
						<button
							v-for="candidate in suggestions.candidates"
							:key="candidate.supplier"
							type="button"
							class="rounded-full border border-outline-gray-2 px-2 py-0.5 text-xs text-ink-gray-8 hover:bg-surface-gray-2"
							:title="candidate.reasons.join(', ')"
							@click="autosave.draft.supplier = candidate.supplier"
						>
							{{ candidate.supplier_name || candidate.supplier }} · {{ candidate.score }} %
						</button>
						<button
							type="button"
							class="rounded-full bg-surface-gray-7 px-2.5 py-0.5 text-xs font-medium text-ink-white hover:opacity-90 disabled:cursor-not-allowed disabled:opacity-40"
							:disabled="!options.can_create_supplier"
							:title="options.can_create_supplier ? '' : 'Creating suppliers needs the Purchase Master Manager role'"
							@click="showCreateSupplier = true"
						>
							+ Create supplier
						</button>
					</div>
				</div>
			</section>

			<!-- Receipt fields -->
			<section class="grid grid-cols-1 gap-3 text-sm sm:grid-cols-3">
				<label class="field">
					<span>Invoice number</span>
					<input v-model="autosave.draft.supplier_reference" :disabled="readonly" class="input" />
				</label>
				<label class="field">
					<span>Date</span>
					<input v-model="autosave.draft.posting_date" type="date" :disabled="readonly" class="input" />
				</label>
				<label class="field">
					<span>Due date</span>
					<input v-model="autosave.draft.due_date" type="date" :disabled="readonly" class="input" />
				</label>
				<label class="field">
					<span>Total (gross)</span>
					<input v-model.number="autosave.draft.sum" type="number" step="0.01" :disabled="readonly" class="input text-right" />
				</label>
				<label class="field">
					<span>Net</span>
					<input v-model.number="autosave.draft.net_total" type="number" step="0.01" :disabled="readonly" class="input text-right" />
				</label>
				<label class="field">
					<span>Tax</span>
					<input v-model.number="autosave.draft.total_taxes" type="number" step="0.01" :disabled="readonly" class="input text-right" />
				</label>
				<label class="field">
					<span>Currency</span>
					<FrappeLink v-model="autosave.draft.currency" doctype="Currency" :disabled="readonly" />
				</label>
				<label class="field">
					<span>Receipt type</span>
					<select v-model="autosave.draft.receipt_type" :disabled="readonly" class="input">
						<option value="">—</option>
						<option v-for="o in options.receipt_types" :key="o" :value="o">{{ o }}</option>
					</select>
				</label>
				<label class="field">
					<span>Project</span>
					<FrappeLink v-model="autosave.draft.project" doctype="Project" :disabled="readonly" />
				</label>
				<label class="field">
					<span>Cost center</span>
					<FrappeLink v-model="autosave.draft.cost_center" doctype="Cost Center" :disabled="readonly" />
				</label>
				<label class="field">
					<span>Payment reference</span>
					<input v-model="autosave.draft.payment_reference" :disabled="readonly" class="input" />
				</label>
				<label class="field">
					<span>Supplier VAT ID</span>
					<input v-model="autosave.draft.supplier_tax_id" :disabled="readonly" class="input" />
				</label>
				<label class="field sm:col-span-2">
					<span>Supplier IBAN</span>
					<input v-model="autosave.draft.supplier_iban" :disabled="readonly" class="input" />
				</label>
			</section>

			<!-- Items -->
			<section>
				<div class="mb-1.5 flex items-center justify-between">
					<h3 class="text-xs font-semibold uppercase tracking-wide text-ink-gray-5">Items</h3>
					<div class="flex items-center gap-3">
						<button v-if="categoryInfo.can_create" type="button" class="text-xs text-ink-gray-6 hover:text-ink-gray-9" @click="showNewCategory = true">+ New category</button>
						<button v-if="!readonly" type="button" class="text-xs text-ink-gray-6 hover:text-ink-gray-9" @click="addItem">+ Add line</button>
					</div>
				</div>
				<p v-if="!autosave.draft.items.length" class="text-sm text-ink-gray-5">No item lines yet.</p>
				<table v-else class="w-full text-sm">
					<thead>
						<tr class="text-left text-[11px] uppercase tracking-wide text-ink-gray-5">
							<th class="py-1 pr-2">Description · category</th>
							<th class="w-14 py-1 pr-2 text-right">Qty</th>
							<th class="w-20 py-1 pr-2 text-right">Rate</th>
							<th class="w-20 py-1 pr-2 text-right">Amount</th>
							<th class="w-14 py-1 pr-2 text-right">Tax %</th>
							<th class="w-6"></th>
						</tr>
					</thead>
					<tbody>
						<tr v-for="(item, i) in autosave.draft.items" :key="item.name || `new-${i}`" class="border-t border-outline-gray-1">
							<td class="py-1 pr-2 align-top">
								<input :value="item.item_name" :disabled="readonly" class="cell" @change="setItem(i, 'item_name', $event.target.value)" />
								<div class="mt-0.5 flex min-w-0 items-center gap-2">
									<select
										:value="item.item_code || ''"
										:disabled="readonly"
										class="cell h-6 max-w-[14rem] text-xs"
										:class="item.item_code ? '' : 'text-ink-amber-3'"
										@change="setItem(i, 'item_code', $event.target.value)"
									>
										<option value="">— choose category —</option>
										<option v-for="c in categories" :key="c.item_code" :value="c.item_code">{{ c.item_name }}</option>
									</select>
									<span class="truncate text-[11px]" :class="accountLabel(item) ? 'text-ink-gray-5' : 'text-ink-amber-3'" :title="accountLabel(item)">
										{{ accountLabel(item) || "no account" }}
									</span>
								</div>
							</td>
							<td class="py-1 pr-2 align-top">
								<input :value="item.qty" type="number" step="any" :disabled="readonly" class="cell text-right" @change="setItem(i, 'qty', $event.target.value)" />
							</td>
							<td class="py-1 pr-2 align-top">
								<input :value="item.rate" type="number" step="0.01" :disabled="readonly" class="cell text-right" @change="setItem(i, 'rate', $event.target.value)" />
							</td>
							<td class="py-1 pr-2 align-top">
								<input :value="item.amount" type="number" step="0.01" :disabled="readonly" class="cell text-right" @change="setItem(i, 'amount', $event.target.value)" />
							</td>
							<td class="py-1 pr-2 align-top">
								<input :value="item.tax_rate" type="number" step="any" :disabled="readonly" class="cell text-right" @change="setItem(i, 'tax_rate', $event.target.value)" />
							</td>
							<td class="py-1 text-right">
								<button v-if="!readonly" type="button" class="text-ink-gray-4 hover:text-ink-red-4" title="Remove line" @click="removeItem(i)">×</button>
							</td>
						</tr>
					</tbody>
					<tfoot>
						<tr class="border-t border-outline-gray-2 text-ink-gray-6">
							<td class="py-1 pr-2" colspan="3">Lines total</td>
							<td class="py-1 pr-2 text-right tabular-nums" :class="linesMismatch ? 'text-ink-amber-3' : ''" :title="linesMismatch ? 'Differs from the net total' : ''">
								{{ money(linesTotal) }}
							</td>
							<td colspan="2"></td>
						</tr>
					</tfoot>
				</table>
			</section>

			<!-- Purchase Invoice -->
			<section class="flex flex-wrap items-center gap-2 text-sm">
				<h3 class="text-xs font-semibold uppercase tracking-wide text-ink-gray-5">Purchase Invoice</h3>
				<a v-if="receipt.purchase_invoice" :href="`/app/purchase-invoice/${receipt.purchase_invoice}`" target="_blank" class="text-ink-blue-3 underline">
					{{ receipt.purchase_invoice }}
				</a>
				<span v-if="receipt.purchase_invoice_status" class="rounded bg-surface-gray-2 px-1.5 py-0.5 text-xs text-ink-gray-7">{{ receipt.purchase_invoice_status }}</span>
				<template v-if="!receipt.purchase_invoice">
					<button
						type="button"
						class="btn"
						:disabled="readonly || creatingInvoice || !autosave.draft.supplier || !autosave.draft.items.length"
						:title="invoiceHint"
						@click="createInvoice"
					>
						{{ creatingInvoice ? "Creating…" : "Create Purchase Invoice" }}
					</button>
					<span class="text-xs text-ink-gray-5">{{ invoiceHint }}</span>
				</template>
			</section>

			<!-- Note -->
			<section>
				<label class="text-xs font-semibold uppercase tracking-wide text-ink-gray-5" for="receipt-note">Note for the accounting office</label>
				<textarea
					id="receipt-note"
					v-model="noteDraft"
					rows="3"
					placeholder="e.g. Guests: Anna Muster (Kunde X), Wolfram Schmidt · Project PROJ-0042 · Cost center Sales"
					class="input mt-1 w-full"
					@blur="saveNoteIfChanged"
				/>
				<p class="text-xs text-ink-gray-5">Printed on top of the PDF sent to DATEV. Saved when you leave the field.</p>
			</section>

			<!-- Actions -->
			<div class="flex flex-wrap gap-2">
				<button type="button" class="btn" :disabled="!receipt.has_pdf || extractStatus === 'running'" @click="emit('run-extract')">Read PDF with AI</button>
				<button type="button" class="btn" :disabled="!receipt.has_pdf || extractStatus === 'running'" title="Read the PDF again and replace the values on the receipt" @click="emit('rerun-extract')">Read again &amp; replace</button>
				<button type="button" class="btn" :disabled="!receipt.has_pdf || extractStatus === 'running'" @click="emit('review-correct')">Compare with AI</button>
				<button type="button" class="btn" :disabled="!receipt.has_pdf" @click="emit('send-to-datev')">{{ receipt.sent_to_datev ? "Resend to DATEV" : "Send to DATEV" }}</button>
				<button type="button" class="btn" :disabled="!receipt.has_pdf" @click="emit('preview-datev')">Preview DATEV PDF</button>
				<a :href="receipt.desk_url" class="btn">Open in Desk</a>
			</div>
		</div>

		<div class="flex min-h-0 min-w-0 flex-col p-5 lg:w-2/5 lg:flex-none">
			<div
				v-if="!pdfUrl"
				class="flex flex-1 items-center justify-center rounded-md border border-dashed border-outline-gray-3 bg-surface-gray-1 px-4 text-center text-sm text-ink-gray-5"
			>
				No PDF attached — drop one on the board or attach it in Desk.
			</div>
			<iframe v-else :src="pdfUrl" type="application/pdf" class="min-h-[480px] flex-1 rounded-md border border-outline-gray-2 bg-surface-gray-2" />
		</div>

		<NewCategoryDialog v-if="showNewCategory" v-model="showNewCategory" :company="receipt.company" @created="onCategoryCreated" />
		<CreateSupplierDialog
			v-if="showCreateSupplier"
			v-model="showCreateSupplier"
			:receipt-name="receipt.name"
			:prefill="suggestions?.extracted || {}"
			@created="onSupplierCreated"
		/>
	</div>
</template>

<script setup>
import { computed, ref, watch } from "vue"
import { call, toast } from "frappe-ui"
import DocSyncBanner from "@spa/components/DocSyncBanner.vue"
import FrappeLink from "@spa/components/FrappeLink.vue"
import { useAutosaveDoc } from "@spa/composables/useAutosaveDoc.js"
import CreateSupplierDialog from "./CreateSupplierDialog.vue"
import NewCategoryDialog from "./NewCategoryDialog.vue"

const API = "phamos.api.accounting_receipts"

const props = defineProps({
	receipt: { type: Object, required: true },
	extractStatus: { type: String, default: "idle" },
	extractUpdatedCount: { type: Number, default: 0 },
	extractErrorMessage: { type: String, default: "" },
})

const emit = defineEmits([
	"close",
	"updated",
	"review-correct",
	"run-extract",
	"rerun-extract",
	"send-to-datev",
	"save-note",
	"preview-datev",
])

const readonly = computed(() => props.receipt?.status === "Cancelled")

const autosave = useAutosaveDoc({
	doc: () => props.receipt,
	fields: {
		title: { kind: "text", trim: true, required: true, label: "Title" },
		supplier: { kind: "select", immediate: true, label: "Supplier" },
		supplier_reference: { kind: "text", trim: true, label: "Invoice number" },
		posting_date: { kind: "date", immediate: true, label: "Date" },
		due_date: { kind: "date", immediate: true, label: "Due date" },
		sum: { kind: "number", label: "Total" },
		net_total: { kind: "number", label: "Net" },
		total_taxes: { kind: "number", label: "Tax" },
		currency: { kind: "select", immediate: true, label: "Currency" },
		receipt_type: { kind: "select", immediate: true, label: "Receipt type" },
		project: { kind: "select", immediate: true, label: "Project" },
		cost_center: { kind: "select", immediate: true, label: "Cost center" },
		payment_reference: { kind: "text", trim: true, label: "Payment reference" },
		supplier_tax_id: { kind: "text", trim: true, label: "Supplier VAT ID" },
		supplier_iban: { kind: "text", trim: true, label: "Supplier IBAN" },
		items: { kind: "json", label: "Items" },
	},
	request: (name, payload, modified) => ({
		method: `${API}.update_receipt`,
		args: { name, ...payload, modified },
	}),
	fetch: (name) => call("phamos.api.accounting_spa.get_receipt", { name }),
	readonly: () => readonly.value,
	onSaved: (receipt) => emit("updated", receipt),
	onError: (message) => toast({ title: message, icon: "x-circle", iconClasses: "text-ink-red-4" }),
})

const saveStateText = computed(() => {
	if (autosave.status === "saving") return "Saving…"
	if (autosave.status === "pending") return "Unsaved changes"
	if (autosave.status === "error") return autosave.error || "Not saved"
	if (autosave.status === "saved") return "Saved"
	return ""
})
const saveStateClass = computed(() => (autosave.status === "error" ? "text-ink-red-4" : "text-ink-gray-5"))

// --- options and supplier suggestions -------------------------------------------------
const options = ref({ receipt_types: [], can_create_supplier: 0 })
call(`${API}.get_receipt_form_options`).then((res) => (options.value = res || options.value))

const suggestions = ref(null)
const showCreateSupplier = ref(false)

async function loadSuggestions() {
	suggestions.value = null
	if (!props.receipt?.name || props.receipt.supplier) return
	try {
		suggestions.value = await call(`${API}.get_supplier_suggestions`, { name: props.receipt.name })
	} catch (e) {
		suggestions.value = { extracted: {}, candidates: [] }
	}
}
watch(() => [props.receipt?.name, props.receipt?.supplier, props.receipt?.ai?.run], loadSuggestions, { immediate: true })

function onSupplierCreated(receipt) {
	toast({ title: `Supplier ${receipt.supplier_name || receipt.supplier} created`, icon: "check-circle", iconClasses: "text-ink-green-3" })
	emit("updated", receipt)
}

// --- categories and Purchase Invoice ---------------------------------------------------
const categoryInfo = ref({ categories: [], can_create: 0 })
const categories = computed(() => categoryInfo.value.categories || [])
const showNewCategory = ref(false)
const creatingInvoice = ref(false)

async function loadCategories() {
	try {
		categoryInfo.value = await call(`${API}.get_expense_categories`, { company: props.receipt?.company })
	} catch (e) {
		categoryInfo.value = { categories: [], can_create: 0 }
	}
}
loadCategories()

function accountLabel(item) {
	const category = categories.value.find((c) => c.item_code === item.item_code)
	if (item.expense_account && (!category || category.expense_account !== item.expense_account)) return item.expense_account
	if (category?.account_number) return `${category.account_number} ${category.account_name}`
	return item.expense_account || ""
}

const invoiceHint = computed(() => {
	if (!autosave.draft.supplier) return "Set the supplier first."
	if (!autosave.draft.items.length) return "Add item lines first."
	if (autosave.draft.items.some((row) => !accountLabel(row))) return "Every line needs a category."
	return ""
})

async function onCategoryCreated() {
	await loadCategories()
}

async function createInvoice() {
	creatingInvoice.value = true
	try {
		await autosave.flush()
		const res = await call(`${API}.make_purchase_invoice`, { name: props.receipt.name })
		toast({ title: `Purchase Invoice ${res.purchase_invoice} created (draft)`, icon: "check-circle", iconClasses: "text-ink-green-3" })
		for (const warning of res.warnings || []) toast({ title: warning, icon: "alert-triangle", iconClasses: "text-ink-amber-3" })
		emit("updated", res.receipt)
	} catch (e) {
		toast({ title: e?.messages?.[0] || e?.message || "Could not create the Purchase Invoice", icon: "x-circle", iconClasses: "text-ink-red-4" })
	} finally {
		creatingInvoice.value = false
	}
}

// --- items ----------------------------------------------------------------------------
function setItem(index, field, raw) {
	const numeric = ["qty", "rate", "amount", "tax_rate"].includes(field)
	const value = numeric ? (raw === "" ? null : Number(raw)) : raw
	autosave.draft.items = autosave.draft.items.map((row, i) => {
		if (i !== index) return row
		const next = { ...row, [field]: value }
		// A new category brings its own expense account (set by the server).
		if (field === "item_code") next.expense_account = null
		if (field === "qty" || field === "rate") next.amount = round2(Number(next.qty || 0) * Number(next.rate || 0))
		return next
	})
}

function addItem() {
	autosave.draft.items = [...autosave.draft.items, { item_name: "New line", qty: 1, rate: 0, amount: 0 }]
}

function removeItem(index) {
	autosave.draft.items = autosave.draft.items.filter((_, i) => i !== index)
}

const linesTotal = computed(() => round2(autosave.draft.items.reduce((sum, row) => sum + Number(row.amount || 0), 0)))
const linesMismatch = computed(() => {
	const net = Number(autosave.draft.net_total || 0)
	return net > 0 && autosave.draft.items.length > 0 && Math.abs(net - linesTotal.value) > 0.02
})

function round2(n) {
	return Math.round(n * 100) / 100
}

// --- note -----------------------------------------------------------------------------
const noteDraft = ref("")
watch(
	() => [props.receipt?.name, props.receipt?.note_text],
	() => {
		noteDraft.value = props.receipt?.note_text || ""
	},
	{ immediate: true }
)

function saveNoteIfChanged() {
	if ((noteDraft.value || "").trim() === (props.receipt?.note_text || "").trim()) return
	emit("save-note", noteDraft.value)
}

// --- display --------------------------------------------------------------------------
const pdfUrl = computed(() => {
	const url = (props.receipt?.attachment || "").trim()
	if (!url || !url.toLowerCase().endsWith(".pdf")) return ""
	return url.startsWith("http") ? url : `${window.location.origin}${url}`
})

function confidenceClass(value) {
	if (value >= 90) return "bg-surface-green-2 text-ink-green-3"
	if (value >= 60) return "bg-surface-amber-2 text-ink-amber-3"
	return "bg-surface-red-2 text-ink-red-4"
}

function money(value) {
	if (value == null || value === "") return "—"
	const n = Number(value)
	const formatted = Number.isFinite(n) ? n.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 }) : String(value)
	const currency = autosave.draft.currency || props.receipt?.currency
	return currency ? `${formatted} ${currency}` : formatted
}

defineExpose({ flush: () => autosave.flush() })
</script>

<style scoped>
.field {
	@apply flex flex-col gap-1;
}
.field > span {
	@apply text-xs text-ink-gray-5;
}
.input {
	@apply h-8 rounded-md border border-outline-gray-2 bg-surface-white px-2 text-sm text-ink-gray-9 disabled:opacity-60;
}
textarea.input {
	@apply h-auto py-1.5;
}
.cell {
	@apply h-7 w-full rounded border border-transparent bg-transparent px-1 text-sm text-ink-gray-9 hover:border-outline-gray-2 focus:border-outline-gray-3 focus:outline-none disabled:opacity-60;
}
.btn {
	@apply inline-flex items-center justify-center rounded-md border border-outline-gray-2 px-3 py-1.5 text-sm font-medium text-ink-gray-8 hover:bg-surface-gray-2 disabled:cursor-not-allowed disabled:opacity-50;
}
</style>
