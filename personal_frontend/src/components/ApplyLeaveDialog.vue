<template>
	<Dialog
		:model-value="modelValue"
		:options="{ title: leave ? __('Edit leave') : __('Apply for leave'), size: 'lg' }"
		@update:model-value="emit('update:modelValue', $event)"
	>
		<template #body-content>
			<div class="space-y-4">
				<p v-if="options && !options.leave_approver" class="rounded-md bg-surface-amber-1 px-3 py-2 text-sm text-ink-amber-3">
					{{ __("No leave approver is set on your employee record. Ask HR to add one.") }}
				</p>
				<p v-else-if="options?.leave_approver" class="text-sm text-ink-gray-6">
					{{ __("Goes to {0} for approval.", [options.leave_approver_name || options.leave_approver]) }}
				</p>
				<FormControl
					v-model="form.leave_type"
					type="select"
					size="sm"
					:label="__('Leave type')"
					:options="leaveTypeOptions"
				/>
				<div class="grid grid-cols-2 gap-3">
					<FormControl v-model="form.from_date" type="date" size="sm" :label="__('From')" />
					<FormControl v-model="form.to_date" type="date" size="sm" :label="__('To')" />
				</div>
				<div class="flex flex-wrap items-end gap-3">
					<FormControl v-model="form.half_day" type="checkbox" size="sm" :label="__('Half day')" />
					<FormControl
						v-if="form.half_day && form.from_date && form.from_date !== form.to_date"
						v-model="form.half_day_date"
						type="date"
						size="sm"
						:label="__('Which day')"
						:min="form.from_date"
						:max="form.to_date"
					/>
				</div>
				<FormControl
					v-if="options?.has_cover_field !== false"
					v-model="form.cover_employee"
					type="select"
					size="sm"
					:label="__('Covered by')"
					:options="coverOptions"
				/>
				<FormControl v-model="form.description" type="textarea" size="sm" :label="__('Reason')" :rows="3" />
				<ErrorMessage :message="error" />
				<div class="flex justify-end gap-2">
					<Button variant="ghost" @click="emit('update:modelValue', false)">{{ __("Cancel") }}</Button>
					<Button variant="solid" :loading="saving" :disabled="!options" @click="save">
						{{ leave ? __("Save") : __("Apply") }}
					</Button>
				</div>
			</div>
		</template>
	</Dialog>
</template>

<script setup>
// Apply for leave, or edit my own Open leave (#1714). HRMS validates balance, overlap and block
// days on save; its message is shown here unchanged.
import { computed, reactive, ref, watch } from "vue"
import { call } from "frappe-ui"
import { formatLeaveDays, leaveFormError, leavePayload } from "@spa/utils/leaveFormat.js"
import { __ } from "@spa/utils/i18n.js"
import spaConfig from "@/config"

const props = defineProps({
	modelValue: { type: Boolean, default: false },
	// a leave row from get_my_leave to edit; null applies for new leave
	leave: { type: Object, default: null },
})
const emit = defineEmits(["update:modelValue", "saved"])

const API = spaConfig.api
const options = ref(null)
const saving = ref(false)
const error = ref("")
const form = reactive(emptyForm())

function todayIso() {
	const d = new Date()
	const pad = (n) => String(n).padStart(2, "0")
	return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}`
}

function emptyForm() {
	const today = todayIso()
	return {
		leave_type: "",
		from_date: today,
		to_date: today,
		half_day: false,
		half_day_date: "",
		description: "",
		cover_employee: "",
	}
}

function fillForm() {
	const leave = props.leave
	Object.assign(
		form,
		leave
			? {
					leave_type: leave.leave_type,
					from_date: leave.from_date,
					to_date: leave.to_date,
					half_day: Boolean(leave.half_day),
					half_day_date: leave.half_day_date || "",
					description: leave.description || "",
					cover_employee: leave.cover_employee || "",
				}
			: emptyForm()
	)
}

const leaveTypeOptions = computed(() => {
	const types = options.value?.leave_types || []
	return [
		{ label: __("Choose…"), value: "" },
		...types.map((t) => ({
			value: t.value,
			label: t.without_pay
				? __("{0} (without pay)", [__(t.value)])
				: __("{0} ({1} days left)", [__(t.value), formatLeaveDays(t.remaining)]),
		})),
	]
})

const coverOptions = computed(() => [
	{ label: __("Nobody"), value: "" },
	...(options.value?.cover_employees || []),
])

async function loadOptions() {
	try {
		options.value = await call(`${API}.get_leave_form_options`, { from_date: form.from_date || null })
		const types = options.value.leave_types || []
		// an edited leave keeps its type even if HRMS no longer offers it on that date
		if (props.leave && form.leave_type && !types.some((t) => t.value === form.leave_type)) {
			types.push({ value: form.leave_type, remaining: null, without_pay: true })
		}
	} catch (e) {
		error.value = e?.messages?.[0] || e?.message || __("Could not load the leave types")
	}
}

watch(
	() => props.modelValue,
	(open) => {
		if (!open) return
		error.value = ""
		fillForm()
		loadOptions()
	},
	{ immediate: true }
)

// a later start can open a new allocation period: reload the remaining days
watch(
	() => form.from_date,
	(value, previous) => {
		if (!props.modelValue || !value || value === previous) return
		if (form.to_date && form.to_date < value) form.to_date = value
		loadOptions()
	}
)

async function save() {
	const problem = leaveFormError(form)
	if (problem) {
		error.value = __(problem)
		return
	}
	saving.value = true
	error.value = ""
	try {
		const payload = leavePayload(form)
		const doc = props.leave
			? await call(`${API}.update_leave`, { name: props.leave.name, modified: props.leave.modified, ...payload })
			: await call(`${API}.apply_leave`, payload)
		emit("saved", doc)
		emit("update:modelValue", false)
	} catch (e) {
		error.value = e?.messages?.[0] || e?.message || __("Could not save the leave")
	} finally {
		saving.value = false
	}
}
</script>
