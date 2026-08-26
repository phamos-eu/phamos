<template>
	<Dialog
		:options="{
			title: 'Review Accounting Receipt',
			size: '7xl',
			actions: [
				{
					label: 'Cancel',
					variant: 'subtle',
					onClick: () => emit('update:modelValue', false),
				},
				{
					label: saving ? 'Applying…' : 'Proceed',
					variant: 'solid',
					loading: saving,
					onClick: apply,
				},
			],
		}"
		:model-value="modelValue"
		@update:model-value="emit('update:modelValue', $event)"
	>
		<template #body-content>
			<div v-if="loading" class="flex items-center justify-center py-16 text-sm text-gray-500 dark:text-gray-400">
				Resolving extracted values…
			</div>
			<div v-else class="flex min-h-[70vh] gap-4">
				<div class="flex min-w-0 flex-[2] flex-col gap-3 overflow-y-auto pr-2">
					<p class="text-xs font-semibold uppercase tracking-wide text-gray-500 dark:text-gray-400">
						Extracted content
					</p>
					<div v-for="field in visibleFields" :key="field.fieldname" class="space-y-1">
						<label class="block text-xs font-medium text-gray-600 dark:text-gray-400">
							{{ field.label }}
						</label>
						<input
							v-if="isTextInput(field)"
							v-model="formValues[field.fieldname]"
							:type="inputType(field)"
							class="w-full rounded-md border border-gray-300 bg-white px-3 py-2 text-sm dark:border-gray-600 dark:bg-gray-800 dark:text-gray-200"
						/>
						<select
							v-else-if="field.fieldtype === 'Select'"
							v-model="formValues[field.fieldname]"
							class="w-full rounded-md border border-gray-300 bg-white px-3 py-2 text-sm dark:border-gray-600 dark:bg-gray-800 dark:text-gray-200"
						>
							<option value="">—</option>
							<option v-for="opt in selectOptions(field)" :key="opt" :value="opt">{{ opt }}</option>
						</select>
						<label
							v-else-if="field.fieldtype === 'Check'"
							class="flex items-center gap-2 text-sm text-gray-700 dark:text-gray-300"
						>
							<input
								v-model="formValues[field.fieldname]"
								type="checkbox"
								class="rounded border-gray-300 dark:border-gray-600"
							/>
							Yes
						</label>
						<textarea
							v-else
							v-model="formValues[field.fieldname]"
							rows="3"
							class="w-full rounded-md border border-gray-300 bg-white px-3 py-2 text-sm dark:border-gray-600 dark:bg-gray-800 dark:text-gray-200"
						/>
						<p
							v-if="field.fieldtype === 'Link' && missingLinks[field.fieldname]"
							class="text-xs text-amber-600 dark:text-amber-400"
						>
							Extracted “{{ missingLinks[field.fieldname] }}” not found in {{ field.options }}.
							<a :href="deskUrl" class="underline" target="_blank" rel="noopener">Open in Desk</a>
							to create it.
						</p>
					</div>
				</div>
				<div v-if="pdfUrl" class="flex min-w-0 flex-[1] flex-col">
					<p class="mb-2 text-xs font-semibold uppercase tracking-wide text-gray-500 dark:text-gray-400">
						Attached PDF
					</p>
					<iframe
						:src="pdfUrl"
						type="application/pdf"
						class="min-h-[70vh] flex-1 rounded-md border border-gray-200 bg-gray-100 dark:border-gray-700 dark:bg-gray-800"
					/>
				</div>
			</div>
			<p v-if="error" class="mt-3 text-sm text-red-600 dark:text-red-400">{{ error }}</p>
		</template>
	</Dialog>
</template>

<script setup>
import { computed, onMounted, ref, watch } from "vue"
import { call, Dialog, toast } from "frappe-ui"

const RESOLVE_API = "phamos.phamos.doctype.accounting_receipt.data_extract.resolve_link_values"
const APPLY_API = "phamos.phamos.doctype.accounting_receipt.data_extract.apply_extracted_data"

const HIDDEN_FIELDS = new Set(["sent_to_datev", "uploaded_by", "company", "payment_date"])
const SKIP_LINK_OPTIONS = new Set(["Project", "Cost Center"])

const props = defineProps({
	modelValue: { type: Boolean, default: false },
	receiptName: { type: String, required: true },
	fields: { type: Array, default: () => [] },
	extracted: { type: Object, default: () => ({}) },
	attachmentUrl: { type: String, default: "" },
})

const emit = defineEmits(["update:modelValue", "applied"])

const loading = ref(false)
const saving = ref(false)
const error = ref("")
const formValues = ref({})
const missingLinks = ref({})

const deskUrl = computed(() => `/app/accounting-receipt/${props.receiptName}`)

const pdfUrl = computed(() => {
	const url = (props.attachmentUrl || "").trim()
	if (!url || !url.toLowerCase().endsWith(".pdf")) return ""
	return url.startsWith("http") ? url : `${window.location.origin}${url}`
})

const visibleFields = computed(() =>
	(props.fields || []).filter((f) => {
		if (HIDDEN_FIELDS.has(f.fieldname)) return false
		if (f.fieldtype === "Link" && SKIP_LINK_OPTIONS.has(f.options)) return false
		return true
	})
)

function isTextInput(field) {
	return ["Data", "Date", "Float", "Currency", "Int", "Link"].includes(field.fieldtype)
}

function inputType(field) {
	if (field.fieldtype === "Date") return "date"
	if (["Float", "Currency", "Int"].includes(field.fieldtype)) return "number"
	return "text"
}

function selectOptions(field) {
	return (field.options || "")
		.split("\n")
		.map((o) => o.trim())
		.filter(Boolean)
}

function initialValue(field, resolvedName) {
	if (field.fieldtype === "Check") {
		const v = resolvedName ?? field.value
		return v === 1 || v === true || v === "1"
	}
	if (resolvedName != null && resolvedName !== "") return resolvedName
	return field.value != null ? field.value : ""
}

async function initForm() {
	loading.value = true
	error.value = ""
	missingLinks.value = {}
	try {
		const linkList = visibleFields.value
			.filter((f) => f.fieldtype === "Link" && f.options && f.value)
			.map((f) => ({ fieldname: f.fieldname, doctype: f.options, value: f.value }))

		let resolved = {}
		if (linkList.length) {
			resolved = await call(RESOLVE_API, { link_list: linkList })
		}

		const values = {}
		const missing = {}
		for (const field of visibleFields.value) {
			if (field.fieldtype === "Link" && field.options && field.value) {
				const name = resolved[field.fieldname]
				if (name) {
					values[field.fieldname] = name
				} else {
					values[field.fieldname] = ""
					missing[field.fieldname] = field.value
				}
			} else {
				values[field.fieldname] = initialValue(field)
			}
		}
		formValues.value = values
		missingLinks.value = missing
	} catch (e) {
		error.value = e?.messages?.[0] || e?.message || "Could not prepare review form"
	} finally {
		loading.value = false
	}
}

async function apply() {
	saving.value = true
	error.value = ""
	try {
		const payload = { ...formValues.value }
		for (const field of visibleFields.value) {
			if (field.fieldtype === "Check") {
				payload[field.fieldname] = payload[field.fieldname] ? 1 : 0
			}
		}
		const result = await call(APPLY_API, {
			accounting_receipt_name: props.receiptName,
			extracted_data: payload,
		})
		const updated = result?.updated || []
		toast.success(updated.length ? `Updated: ${updated.join(", ")}` : "Data applied.")
		emit("applied")
		emit("update:modelValue", false)
	} catch (e) {
		error.value = e?.messages?.[0] || e?.message || "Could not apply extracted data"
	} finally {
		saving.value = false
	}
}

watch(
	() => props.modelValue,
	(open) => {
		if (open) initForm()
	}
)

onMounted(() => {
	if (props.modelValue) initForm()
})
</script>
