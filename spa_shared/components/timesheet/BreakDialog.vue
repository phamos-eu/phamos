<template>
	<Dialog
		:model-value="modelValue"
		:options="{ title: logging ? __('Track the break') : __('Track this break?'), size: logging ? 'lg' : 'md' }"
		@update:model-value="emit('update:modelValue', $event)"
	>
		<template #body-content>
			<div v-if="!logging" class="space-y-4" @keydown.enter.prevent="logging = true">
				<p class="text-sm text-ink-gray-7">
					{{ question }}
				</p>
				<p class="text-xs text-ink-gray-5">{{ __("If not, the goal and estimate of the break are dropped.") }}</p>
				<div class="flex justify-end gap-2">
					<Button variant="ghost" :loading="saving" @click="resume(false)">{{ __("No, drop it and resume") }}</Button>
					<Button variant="solid" @click="logging = true">{{ __("Yes, track it") }}</Button>
				</div>
			</div>
			<form v-else class="space-y-4" @submit.prevent="resume(true)" @keydown.enter.ctrl.prevent="resume(true)" @keydown.enter.meta.prevent="resume(true)">
				<FormControl v-model="project" type="select" size="sm" :label="__('Project') + ' *'" :options="projectOptions" />
				<FormControl v-model="activityType" type="select" size="sm" :label="__('Activity type')" :options="activityOptions" />
				<div class="grid grid-cols-2 gap-3">
					<FormControl v-model="valueAdd" type="select" size="sm" :label="__('Value Add (%)')" :options="ratingOptions()" />
					<FormControl v-model="billable" type="select" size="sm" :label="__('Percent Billable')" :options="ratingOptions()" />
				</div>
				<p class="text-xs text-ink-gray-5">{{ __(VALUE_ADD_HELP) }}</p>
				<FormControl v-model="goal" type="text" size="sm" :label="__('Goal') + ' *'" />
				<FormControl v-model="result" type="textarea" size="sm" :label="__('What happened?') + ' *'" />
				<ErrorMessage :message="error" />
				<div class="flex justify-end gap-2">
					<Button variant="ghost" @click="logging = false">{{ __("Back") }}</Button>
					<Button variant="solid" type="submit" :loading="saving">{{ __("Log break and resume") }}</Button>
				</div>
			</form>
		</template>
	</Dialog>
</template>

<script setup>
import { computed, ref, watch } from "vue"
import { call } from "frappe-ui"
import { __ } from "@spa/utils/i18n.js"
import { formatMinutes } from "@spa/utils/timerClock.js"
import { billablePreset, ratingOptions, VALUE_ADD_DEFAULT, VALUE_ADD_HELP } from "@spa/utils/timesheetRating.js"
import spaConfig from "@/config"

const props = defineProps({
	modelValue: { type: Boolean, default: false },
	session: { type: Object, default: null },
	breakSeconds: { type: Number, default: 0 },
})
const emit = defineEmits(["update:modelValue", "resumed"])

const API = spaConfig.api
const logging = ref(false)
const projects = ref([])
const activityTypes = ref([])
const project = ref("")
const activityType = ref("")
const billable = ref("100")
const valueAdd = ref(VALUE_ADD_DEFAULT)
const goal = ref("")
const result = ref("")
const error = ref("")
const saving = ref(false)

const breakText = computed(() => formatMinutes(props.breakSeconds))
const estimateText = computed(() => formatMinutes(props.session?.break_expected || 0))
const question = computed(() => {
	const goal = props.session?.break_goal || __("Break")
	return props.session?.break_expected
		? __("“{0}” took {1} of the {2} you estimated. Track it as its own timesheet record?", [goal, breakText.value, estimateText.value])
		: __("“{0}” took {1}. Track it as its own timesheet record?", [goal, breakText.value])
})
const projectOptions = computed(() => [
	{ label: __("Pick a project"), value: "" },
	...projects.value.map((row) => ({ label: row.project_name || row.name, value: row.name })),
])
const activityOptions = computed(() => activityTypes.value.map((name) => ({ label: name, value: name })))

async function open() {
	logging.value = false
	error.value = ""
	goal.value = props.session?.break_goal || ""
	result.value = ""
	valueAdd.value = VALUE_ADD_DEFAULT
	project.value = props.session?.project || ""
	billable.value = billablePreset(props.session?.project_percent_billable)
	try {
		const options = await call(`${API}.get_timer_options`)
		const seen = new Set()
		projects.value = [
			{ name: props.session.project, project_name: props.session.project_name },
			...(options.my_projects || []),
			...(options.recent_projects || []),
		].filter((row) => row.name && !seen.has(row.name) && seen.add(row.name))
		activityTypes.value = options.activity_types || []
		activityType.value = options.default_activity_type || activityTypes.value[0] || ""
	} catch {
		projects.value = [{ name: props.session.project, project_name: props.session.project_name }]
	}
}

async function resume(withBreak) {
	error.value = ""
	const args = { name: props.session.name }
	if (withBreak) {
		if (!project.value) return (error.value = __("Please pick a project."))
		if (!goal.value.trim() || !result.value.trim()) return (error.value = __("Please fill in the goal and what happened."))
		Object.assign(args, {
			track_break: 1,
			break_project: project.value,
			break_goal: goal.value.trim(),
			break_result: result.value.trim(),
			break_activity_type: activityType.value || null,
			break_percent_billable: billable.value,
			break_value_add: valueAdd.value,
		})
	}
	saving.value = true
	try {
		const state = await call(`${API}.resume_timer`, args)
		emit("resumed", state, withBreak)
		emit("update:modelValue", false)
	} catch (e) {
		error.value = e?.messages?.[0] || e?.message || __("Could not resume the timer")
	} finally {
		saving.value = false
	}
}

// Percent Billable follows the picked project's preset (100 when it has none).
watch(project, async (name, previous) => {
	if (!name || !previous || name === previous) return
	try {
		const info = await call(`${API}.get_timer_project_info`, { project: name })
		if (project.value === name) billable.value = billablePreset(info?.percent_billable)
	} catch {
		billable.value = billablePreset(null)
	}
})

watch(
	() => props.modelValue,
	(value) => value && open()
)
</script>
