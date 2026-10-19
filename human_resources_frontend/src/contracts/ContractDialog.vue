<template>
	<Dialog
		:model-value="modelValue"
		:options="{
			title: dialogTitle,
			size: '2xl',
			actions: [
				{ label: 'Cancel', variant: 'subtle', onClick: close },
				{ label: 'Save as draft', variant: 'outline', loading: saving === 'draft', onClick: () => save(false) },
				{ label: 'Submit', variant: 'solid', loading: saving === 'submit', onClick: () => save(true) },
			],
		}"
		@update:model-value="emit('update:modelValue', $event)"
	>
		<template #body-content>
			<!-- Enter in any field submits, like Ctrl+S in Desk. -->
			<form ref="formEl" class="space-y-4" @submit.prevent="save(true)">
				<p v-if="mode === 'change'" class="text-sm text-ink-gray-6">
					Set the date the change takes effect and adjust what differs. Submitting closes
					{{ source?.name }} the day before.
				</p>

				<div v-if="mode === 'new'">
					<label class="mb-1.5 block text-xs text-ink-gray-5">
						Employee <span class="text-ink-red-3">*</span>
					</label>
					<FrappeLink
						doctype="Employee"
						v-model="form.employee"
						:filters="{ status: 'Active' }"
						placeholder="Select employee"
					/>
					<p v-if="existingHint" class="mt-1.5 text-xs text-ink-gray-6">{{ existingHint }}</p>
				</div>
				<div v-else class="text-sm">
					<span class="text-ink-gray-5">Employee</span>
					<span class="ml-2 font-medium text-ink-gray-9">{{ source?.employee_name || form.employee }}</span>
				</div>

				<div class="grid grid-cols-1 gap-3 sm:grid-cols-3">
					<FormControl
						ref="effectiveFromEl"
						v-model="form.effective_from"
						label="Effective from"
						type="date"
						size="sm"
						required
					/>
					<FormControl v-model="form.valid_until" label="Valid until (optional)" type="date" size="sm" />
					<FormControl
						v-model="form.contract_type"
						label="Contract type"
						type="select"
						size="sm"
						:options="['Employed', 'External']"
					/>
				</div>

				<div class="grid grid-cols-1 gap-3 sm:grid-cols-3">
					<FormControl v-model="form.fte_percentage" label="FTE %" type="number" size="sm" min="1" max="100" required />
					<FormControl
						v-model="form.full_time_hours_per_week"
						label="Full-time hours / week"
						type="number"
						size="sm"
					/>
					<FormControl
						v-if="form.contract_type === 'External'"
						v-model="form.monthly_amount"
						label="Agreed monthly amount"
						type="number"
						size="sm"
						required
					/>
					<FormControl
						v-else
						v-model="form.yearly_gross_full_time"
						label="Yearly gross (100 %)"
						type="number"
						size="sm"
						required
					/>
				</div>

				<div class="grid grid-cols-1 gap-3 sm:grid-cols-3">
					<div>
						<label class="mb-1.5 block text-xs text-ink-gray-5">Currency</label>
						<FrappeLink doctype="Currency" v-model="form.currency" placeholder="Currency" />
					</div>
					<FormControl
						v-if="foreignCurrency"
						v-model="form.conversion_rate"
						:label="`Planning rate: 1 ${form.currency} in ${form.company_currency}`"
						type="number"
						size="sm"
						step="any"
						required
					/>
					<p v-if="foreignCurrency" class="self-end pb-1.5 text-xs text-ink-gray-5">
						Fixed for this contract, so forecasts don't move with daily rates.
					</p>
				</div>

				<div class="rounded-md bg-surface-gray-2 px-3 py-2 text-sm text-ink-gray-8 tabular-nums">
					{{ formatHours(weeklyHours) }} per week · {{ formatMoney(monthlyGross, form.currency) }} per month
					<span v-if="foreignCurrency">
						≈ {{ formatMoney(monthlyGross * Number(form.conversion_rate || 0), form.company_currency) }}
					</span>
				</div>

				<div class="grid grid-cols-1 gap-3 sm:grid-cols-2">
					<div>
						<label class="mb-1.5 block text-xs text-ink-gray-5">Expense account (optional)</label>
						<FrappeLink
							doctype="Account"
							v-model="form.expense_account"
							:filters="{ company: form.company, root_type: 'Expense', is_group: 0 }"
							:disabled="!form.company"
							placeholder="Select account"
						/>
					</div>
					<FormControl v-model="form.notes" label="Notes" type="textarea" size="sm" :rows="2" />
				</div>

				<ErrorMessage :message="error" />
				<button type="submit" class="hidden" tabindex="-1" />
			</form>
		</template>
	</Dialog>
</template>

<script setup>
import { computed, nextTick, reactive, ref, watch } from "vue"
import { call, toast } from "frappe-ui"
import FrappeLink from "@spa/components/FrappeLink.vue"
import { CONTRACTS_API, errorMessage, firstOfNextMonth, formatHours, formatMoney } from "@spa/contracts/contractFormat.js"

const props = defineProps({
	modelValue: { type: Boolean, default: false },
	/** "new" | "change" (new contract from `source`) | "edit" (draft `source`) */
	mode: { type: String, default: "new" },
	source: { type: Object, default: null },
	employee: { type: String, default: "" },
})

const emit = defineEmits(["update:modelValue", "saved"])

const TERM_FIELDS = [
	"employee",
	"company",
	"currency",
	"company_currency",
	"conversion_rate",
	"contract_type",
	"fte_percentage",
	"full_time_hours_per_week",
	"yearly_gross_full_time",
	"monthly_amount",
	"expense_account",
	"notes",
]

const form = reactive({})
const saving = ref("")
const error = ref("")
const existingHint = ref("")
const formEl = ref(null)
// True while the form is being filled from props, so the currency watcher doesn't replace a stored rate.
let resetting = false

const dialogTitle = computed(
	() => ({ new: "New employment contract", change: "Record change", edit: "Edit draft contract" })[props.mode]
)

const weeklyHours = computed(
	() => (Number(form.fte_percentage || 0) * Number(form.full_time_hours_per_week || 0)) / 100
)
const foreignCurrency = computed(
	() => Boolean(form.currency && form.company_currency && form.currency !== form.company_currency)
)

// Default planning rate from Currency Exchange: replaced when the currency changes,
// filled for a new date only while empty, so a typed rate is kept.
async function loadPlanningRate(replace) {
	if (!form.company || !form.currency) return
	if (!replace && Number(form.conversion_rate)) return
	try {
		const result = await call(
			"phamos.phamos.doctype.employment_contract.employment_contract.get_planning_exchange_rate",
			{ currency: form.currency, company: form.company, on_date: form.effective_from || null }
		)
		form.company_currency = result.company_currency
		form.conversion_rate = result.rate || ""
	} catch (e) {
		error.value = errorMessage(e, "Could not load the exchange rate")
	}
}

watch(
	() => form.currency,
	(currency, previous) => {
		if (props.modelValue && !resetting && currency !== previous) loadPlanningRate(true)
	}
)
watch(
	() => form.effective_from,
	() => {
		if (props.modelValue && !resetting && foreignCurrency.value) loadPlanningRate(false)
	}
)

const monthlyGross = computed(() =>
	form.contract_type === "External"
		? Number(form.monthly_amount || 0)
		: (Number(form.yearly_gross_full_time || 0) * Number(form.fte_percentage || 0)) / 100 / 12
)

function reset() {
	resetting = true
	for (const key of Object.keys(form)) delete form[key]
	Object.assign(form, {
		employee: props.employee || "",
		company: "",
		currency: "",
		company_currency: "",
		conversion_rate: "",
		contract_type: "Employed",
		effective_from: "",
		valid_until: "",
		fte_percentage: 100,
		full_time_hours_per_week: 40,
		yearly_gross_full_time: "",
		monthly_amount: "",
		expense_account: "",
		notes: "",
	})
	const src = props.source
	if (src && props.mode !== "new") {
		for (const key of TERM_FIELDS) form[key] = src[key] ?? form[key]
		if (props.mode === "edit") {
			form.effective_from = src.effective_from || ""
			form.valid_until = src.valid_until || ""
		} else {
			// A change starts after the current contract; next month is the usual case.
			const next = firstOfNextMonth()
			form.effective_from = next > src.effective_from ? next : ""
			form.notes = ""
			// A new contract takes the planning rate of its own start date.
			if (form.currency !== form.company_currency) form.conversion_rate = ""
		}
	}
	error.value = ""
	existingHint.value = ""
}

watch(
	() => props.modelValue,
	async (open) => {
		if (!open) return
		reset()
		await nextTick()
		resetting = false
		const selector = props.mode === "new" ? "button, input" : 'input[type="date"]'
		formEl.value?.querySelector(selector)?.focus()
		if (form.employee && props.mode === "new") await loadEmployeeDefaults(form.employee)
		if (foreignCurrency.value && !Number(form.conversion_rate)) await loadPlanningRate(false)
	}
)

watch(
	() => form.employee,
	(employee, previous) => {
		if (props.mode === "new" && !resetting && employee && employee !== previous) loadEmployeeDefaults(employee)
	}
)

async function loadEmployeeDefaults(employee) {
	try {
		const defaults = await call(`${CONTRACTS_API}.get_employee_defaults`, { employee })
		form.company = defaults.company || ""
		form.currency = defaults.currency || ""
		form.company_currency = defaults.currency || ""
		existingHint.value = defaults.latest
			? `Already has contract ${defaults.latest.name}. Use "Record change" on it to change hours or pay.`
			: ""
	} catch (e) {
		error.value = errorMessage(e, "Could not load employee")
	}
}

function close() {
	emit("update:modelValue", false)
}

async function save(submit) {
	if (saving.value) return
	saving.value = submit ? "submit" : "draft"
	error.value = ""
	try {
		const values = { ...form }
		if (!values.valid_until) values.valid_until = null
		if (!values.expense_account) values.expense_account = null
		const contract = await call(`${CONTRACTS_API}.save_contract`, {
			values,
			name: props.mode === "edit" ? props.source?.name : null,
			submit: submit ? 1 : 0,
		})
		toast.success(submit ? `Contract ${contract.name} submitted` : `Draft ${contract.name} saved`)
		emit("saved", contract)
		close()
	} catch (e) {
		error.value = errorMessage(e, "Could not save the contract")
	} finally {
		saving.value = ""
	}
}
</script>
