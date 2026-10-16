<template>
	<Dialog
		:options="{
			title: 'Compare with the AI reading',
			size: '7xl',
			actions: [
				{ label: 'Keep my values', variant: 'subtle', onClick: () => emit('update:modelValue', false) },
				{
					label: saving ? 'Applying…' : `Take over ${selectedCount} value${selectedCount === 1 ? '' : 's'}`,
					variant: 'solid',
					loading: saving,
					disabled: !selectedCount,
					onClick: apply,
				},
			],
		}"
		:model-value="modelValue"
		@update:model-value="emit('update:modelValue', $event)"
	>
		<template #body-content>
			<div class="flex min-h-[65vh] gap-4">
				<div class="flex min-w-0 flex-[3] flex-col gap-3 overflow-y-auto pr-2">
					<p v-if="loading" class="py-10 text-center text-sm text-ink-gray-5">Loading the AI reading…</p>
					<p v-else-if="!run" class="py-10 text-center text-sm text-ink-gray-5">
						The AI has not read this receipt yet. Use "Read PDF with AI" first.
					</p>
					<p v-else-if="!rows.length && !items" class="py-10 text-center text-sm text-ink-gray-5">
						The receipt already matches everything the AI read.
					</p>
					<template v-else>
						<p class="text-sm text-ink-gray-6">
							Only fields where the AI read something else are listed. Your values stay unless you tick a row.
						</p>
						<table class="w-full text-sm">
							<thead>
								<tr class="text-left text-xs uppercase tracking-wide text-ink-gray-5">
									<th class="w-8 py-1"></th>
									<th class="py-1 pr-4">Field</th>
									<th class="py-1 pr-4">Now</th>
									<th class="py-1 pr-4">AI read</th>
								</tr>
							</thead>
							<tbody>
								<tr v-for="row in rows" :key="row.fieldname" class="border-t border-outline-gray-1 align-top">
									<td class="py-2">
										<input
											v-if="row.state !== 'missing_link'"
											v-model="selected[row.fieldname]"
											type="checkbox"
											class="rounded"
										/>
									</td>
									<td class="py-2 pr-4 font-medium text-ink-gray-8">{{ row.label }}</td>
									<td class="py-2 pr-4 text-ink-gray-6">{{ display(row.current) }}</td>
									<td class="py-2 text-ink-gray-9">
										{{ display(row.extracted) }}
										<span v-if="row.state === 'missing_link'" class="block text-xs text-ink-amber-3">
											Not in the system yet — create the supplier in Desk, then pick it.
										</span>
									</td>
								</tr>
								<tr v-if="items" class="border-t border-outline-gray-1 align-top">
									<td class="py-2"><input v-model="takeItems" type="checkbox" class="rounded" /></td>
									<td class="py-2 pr-4 font-medium text-ink-gray-8">Item lines</td>
									<td class="py-2 pr-4 text-ink-gray-6">{{ items.current_count }} line(s)</td>
									<td class="py-2 text-ink-gray-9">
										<div v-for="(item, i) in items.extracted" :key="i">
											{{ item.qty }} × {{ item.item_name }} — {{ display(item.amount) }}
										</div>
									</td>
								</tr>
							</tbody>
						</table>
					</template>
					<p v-if="error" class="text-sm text-ink-red-4">{{ error }}</p>
				</div>
				<div v-if="pdfUrl" class="flex min-w-0 flex-[2] flex-col">
					<iframe :src="pdfUrl" type="application/pdf" class="min-h-[65vh] flex-1 rounded-md border border-outline-gray-2" />
				</div>
			</div>
		</template>
	</Dialog>
</template>

<script setup>
import { computed, ref, watch } from "vue"
import { call, Dialog } from "frappe-ui"

const API = "phamos.api.accounting_receipts"

const props = defineProps({
	modelValue: { type: Boolean, default: false },
	receiptName: { type: String, required: true },
	attachmentUrl: { type: String, default: "" },
})
const emit = defineEmits(["update:modelValue", "applied"])

const loading = ref(false)
const saving = ref(false)
const error = ref("")
const run = ref(null)
const rows = ref([])
const items = ref(null)
const selected = ref({})
const takeItems = ref(false)

const pdfUrl = computed(() => (props.attachmentUrl.toLowerCase().endsWith(".pdf") ? props.attachmentUrl : ""))
const selectedCount = computed(
	() => Object.values(selected.value).filter(Boolean).length + (takeItems.value ? 1 : 0)
)

function display(value) {
	if (value == null || value === "") return "—"
	if (typeof value === "number") return value.toLocaleString(undefined, { maximumFractionDigits: 2 })
	return String(value)
}

async function load() {
	loading.value = true
	error.value = ""
	try {
		const res = await call(`${API}.get_extraction_diff`, { name: props.receiptName })
		run.value = res.run
		rows.value = res.rows || []
		items.value = res.items
		// Empty fields are pre-ticked; fields you already filled are not.
		selected.value = Object.fromEntries(rows.value.map((r) => [r.fieldname, r.state === "new"]))
		takeItems.value = Boolean(res.items && !res.items.current_count)
	} catch (e) {
		error.value = e?.messages?.[0] || e?.message || "Could not load the AI reading"
	} finally {
		loading.value = false
	}
}

async function apply() {
	saving.value = true
	error.value = ""
	try {
		const fields = Object.keys(selected.value).filter((k) => selected.value[k])
		await call(`${API}.apply_extraction`, { name: props.receiptName, fields, include_items: takeItems.value ? 1 : 0 })
		emit("applied")
		emit("update:modelValue", false)
	} catch (e) {
		error.value = e?.messages?.[0] || e?.message || "Could not apply the values"
	} finally {
		saving.value = false
	}
}

watch(
	() => [props.modelValue, props.receiptName],
	([open]) => {
		if (open) load()
	},
	{ immediate: true }
)
</script>
