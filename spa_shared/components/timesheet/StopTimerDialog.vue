<template>
	<Dialog
		:model-value="modelValue"
		:options="{ title: __('Stop timer'), size: 'lg' }"
		@update:model-value="emit('update:modelValue', $event)"
	>
		<template #body-content>
			<form v-if="session" class="space-y-4" @submit.prevent="submit" @keydown.enter.ctrl.prevent="submit" @keydown.enter.meta.prevent="submit">
				<div class="rounded-md bg-surface-gray-2 px-3 py-2 text-sm">
					<div class="font-medium text-ink-gray-9">{{ session.project_name }}</div>
					<div class="text-ink-gray-6">{{ session.goal }}</div>
				</div>
				<FormControl
					v-model="result"
					type="textarea"
					size="sm"
					:label="__('What did you accomplish?') + ' *'"
					:placeholder="__('Sent to the customer the next day.')"
				/>
				<FormControl v-model="activityType" type="select" size="sm" :label="__('Activity type') + ' *'" :options="activityOptions" />
				<div class="grid grid-cols-2 gap-3">
					<FormControl v-model="valueAdd" type="select" size="sm" :label="__('Value Add (%)')" :options="ratingOptions()" />
					<FormControl v-model="billable" type="select" size="sm" :label="__('Percent Billable')" :options="ratingOptions()" />
				</div>
				<p class="text-xs text-ink-gray-5">{{ __(VALUE_ADD_HELP) }}</p>
				<FormControl v-model="endTime" type="datetime-local" size="sm" :label="__('End')" @input="endEdited = true" />
				<ErrorMessage :message="error" />
				<div class="flex items-center justify-between gap-2">
					<span class="text-xs text-ink-gray-5">{{ __("Ctrl+Enter stops") }}</span>
					<div class="flex gap-2">
						<Button variant="ghost" @click="emit('update:modelValue', false)">{{ __("Cancel") }}</Button>
						<Button variant="solid" type="submit" :loading="saving">{{ __("Stop and submit") }}</Button>
					</div>
				</div>
			</form>
		</template>
	</Dialog>
</template>

<script setup>
import { computed, onBeforeUnmount, ref, watch } from "vue"
import { call } from "frappe-ui"
import { formatForApi, parseDatetimeLocalValue, parseSystemDatetimeToUserDate, toDatetimeLocalValue } from "@spa/utils/datetime.js"
import { __ } from "@spa/utils/i18n.js"
import { billablePreset, ratingOptions, VALUE_ADD_DEFAULT, VALUE_ADD_HELP } from "@spa/utils/timesheetRating.js"
import spaConfig from "@/config"

const props = defineProps({
	modelValue: { type: Boolean, default: false },
	session: { type: Object, default: null },
	defaultActivityType: { type: String, default: "" },
})
const emit = defineEmits(["update:modelValue", "stopped", "limit"])

const API = spaConfig.api
const result = ref("")
const activityType = ref("")
const activityTypes = ref([])
const billable = ref("100")
const valueAdd = ref(VALUE_ADD_DEFAULT)
const endTime = ref("")
const endEdited = ref(false)
const error = ref("")
const saving = ref(false)
let liveTimer = null

const activityOptions = computed(() => [
	{ label: __("Pick an activity type"), value: "" },
	...activityTypes.value.map((name) => ({ label: name, value: name })),
])

function errorText(e, fallback) {
	return e?.messages?.[0] || e?.message || fallback
}

async function open() {
	error.value = ""
	result.value = props.session?.result || ""
	activityType.value = props.session?.activity_type || props.defaultActivityType || ""
	billable.value = billablePreset(props.session?.project_percent_billable)
	valueAdd.value = VALUE_ADD_DEFAULT
	endEdited.value = false
	endTime.value = toDatetimeLocalValue(new Date())
	liveTimer = setInterval(() => {
		if (!endEdited.value) endTime.value = toDatetimeLocalValue(new Date())
	}, 15000)
	try {
		const options = await call(`${API}.get_timer_options`)
		activityTypes.value = options.activity_types || []
		if (!activityType.value) activityType.value = options.default_activity_type || ""
	} catch {
		activityTypes.value = activityType.value ? [activityType.value] : []
	}
}

async function submit() {
	error.value = ""
	if (!result.value.trim()) return (error.value = __("Please describe what you accomplished."))
	if (!activityType.value) return (error.value = __("Please pick an activity type."))
	const args = {
		name: props.session.name,
		result: result.value.trim(),
		activity_type: activityType.value,
		percent_billable: billable.value,
		value_add: valueAdd.value,
	}
	if (endEdited.value) {
		const end = parseDatetimeLocalValue(endTime.value)
		const segmentStart = parseSystemDatetimeToUserDate(String(props.session.open_row_from || ""))
		if (end && segmentStart && end < segmentStart) return (error.value = __("The end cannot be before the current segment started."))
		if (end) args.manual_end_time = formatForApi(end)
	}
	saving.value = true
	try {
		const response = await call(`${API}.stop_timer`, args)
		emit("update:modelValue", false)
		if (response.outcome?.exceeds) emit("limit", response)
		else emit("stopped", response)
	} catch (e) {
		error.value = errorText(e, __("Could not stop the timer"))
	} finally {
		saving.value = false
	}
}

watch(
	() => props.modelValue,
	(value) => {
		clearInterval(liveTimer)
		if (value) open()
	}
)
onBeforeUnmount(() => clearInterval(liveTimer))
</script>
