<template>
	<Dialog
		:model-value="modelValue"
		:options="{ title: logging ? 'Log the break' : 'Log break time?', size: logging ? 'lg' : 'md' }"
		@update:model-value="emit('update:modelValue', $event)"
	>
		<template #body-content>
			<div v-if="!logging" class="space-y-4" @keydown.enter.prevent="logging = true">
				<p class="text-sm text-ink-gray-7">
					The break lasted {{ breakText }}. Log it as its own timesheet record, for example a call for another
					customer?
				</p>
				<div class="flex justify-end gap-2">
					<Button variant="ghost" :loading="saving" @click="resume(false)">No, just resume</Button>
					<Button variant="solid" @click="logging = true">Yes, log it</Button>
				</div>
			</div>
			<form v-else class="space-y-4" @submit.prevent="resume(true)" @keydown.enter.ctrl.prevent="resume(true)" @keydown.enter.meta.prevent="resume(true)">
				<FormControl v-model="project" type="select" size="sm" label="Project *" :options="projectOptions" />
				<div class="grid grid-cols-2 gap-3">
					<FormControl v-model="activityType" type="select" size="sm" label="Activity type" :options="activityOptions" />
					<FormControl v-model="billable" type="select" size="sm" label="Billable" :options="BILLABLE" />
				</div>
				<FormControl v-model="goal" type="text" size="sm" label="Goal *" />
				<FormControl v-model="result" type="textarea" size="sm" label="What happened? *" />
				<ErrorMessage :message="error" />
				<div class="flex justify-end gap-2">
					<Button variant="ghost" @click="logging = false">Back</Button>
					<Button variant="solid" type="submit" :loading="saving">Log break and resume</Button>
				</div>
			</form>
		</template>
	</Dialog>
</template>

<script setup>
import { computed, ref, watch } from "vue"
import { call } from "frappe-ui"
import { formatMinutes } from "@spa/utils/timerClock.js"
import spaConfig from "@/config"

const props = defineProps({
	modelValue: { type: Boolean, default: false },
	session: { type: Object, default: null },
	breakSeconds: { type: Number, default: 0 },
})
const emit = defineEmits(["update:modelValue", "resumed"])

const API = spaConfig.api
const BILLABLE = ["0", "25", "50", "75", "100"].map((value) => ({ label: `${value} %`, value }))
const logging = ref(false)
const projects = ref([])
const activityTypes = ref([])
const project = ref("")
const activityType = ref("")
const billable = ref("0")
const goal = ref("")
const result = ref("")
const error = ref("")
const saving = ref(false)

const breakText = computed(() => formatMinutes(props.breakSeconds))
const projectOptions = computed(() => [
	{ label: "Pick a project", value: "" },
	...projects.value.map((row) => ({ label: row.project_name || row.name, value: row.name })),
])
const activityOptions = computed(() => activityTypes.value.map((name) => ({ label: name, value: name })))

async function open() {
	logging.value = false
	error.value = ""
	goal.value = ""
	result.value = ""
	billable.value = "0"
	project.value = props.session?.project || ""
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
		if (!project.value) return (error.value = "Please pick a project.")
		if (!goal.value.trim() || !result.value.trim()) return (error.value = "Please fill in the goal and what happened.")
		Object.assign(args, {
			break_project: project.value,
			break_goal: goal.value.trim(),
			break_result: result.value.trim(),
			break_activity_type: activityType.value || null,
			break_percent_billable: billable.value,
		})
	}
	saving.value = true
	try {
		const state = await call(`${API}.resume_timer`, args)
		emit("resumed", state, withBreak)
		emit("update:modelValue", false)
	} catch (e) {
		error.value = e?.messages?.[0] || e?.message || "Could not resume the timer"
	} finally {
		saving.value = false
	}
}

watch(
	() => props.modelValue,
	(value) => value && open()
)
</script>
