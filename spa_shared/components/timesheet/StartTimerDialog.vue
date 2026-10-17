<template>
	<Dialog
		:model-value="modelValue"
		:options="{ title: __('Start timer'), size: 'lg' }"
		@update:model-value="emit('update:modelValue', $event)"
	>
		<template #body-content>
			<form class="space-y-4" @submit.prevent="submit" @keydown.enter.ctrl.prevent="submit" @keydown.enter.meta.prevent="submit">
				<div>
					<label class="mb-1.5 block text-xs text-ink-gray-5">{{ __("Project") }} <span class="text-ink-red-3">*</span></label>
					<div
						v-if="project"
						class="flex items-center justify-between rounded border border-outline-gray-2 bg-surface-gray-1 px-2.5 py-1.5 text-sm"
					>
						<span class="truncate text-ink-gray-9">{{ project.project_name || project.name }}</span>
						<button type="button" class="text-xs text-ink-gray-5 hover:underline" @click="clearProject">{{ __("Change") }}</button>
					</div>
					<template v-else>
						<FormControl v-model="search" type="text" size="sm" :placeholder="__('Search all open projects…')" />
						<div class="mt-2 max-h-56 space-y-3 overflow-y-auto">
							<div v-for="group in groups" :key="group.label">
								<div class="mb-1 text-xs font-medium uppercase tracking-wide text-ink-gray-5">{{ __(group.label) }}</div>
								<ul class="space-y-0.5">
									<li v-for="row in group.rows" :key="row.name">
										<button
											type="button"
											class="flex w-full items-center justify-between rounded px-2 py-1 text-left text-sm hover:bg-surface-gray-2"
											@click="pick(row)"
										>
											<span class="truncate text-ink-gray-9">{{ row.project_name || row.name }}</span>
											<span class="ml-2 truncate text-xs text-ink-gray-5">{{ row.customer }}</span>
										</button>
									</li>
								</ul>
							</div>
							<p v-if="!groups.length" class="text-sm text-ink-gray-5">{{ loading ? __("Loading projects…") : __("No open project found.") }}</p>
						</div>
					</template>
				</div>

				<FormControl
					v-if="project && info && info.task_rule !== 'Task is hidden'"
					v-model="task"
					type="select"
					size="sm"
					:label="info.task_rule === 'Task is mandatory' ? __('Task') + ' *' : __('Task')"
					:options="taskOptions"
				/>

				<div class="grid grid-cols-2 gap-3">
					<FormControl v-model="minutes" type="number" size="sm" :label="__('Expected minutes')" :step="15" :min="15" />
					<FormControl v-model="startTime" type="datetime-local" size="sm" :label="__('Start')" @input="startEdited = true" />
				</div>
				<FormControl
					v-model="goal"
					type="textarea"
					size="sm"
					:label="__('Goal') + ' *'"
					:placeholder="__('What will you accomplish? Shared with the customer the next day.')"
				/>
				<ErrorMessage :message="error" />
				<div class="flex items-center justify-between gap-2">
					<span class="text-xs text-ink-gray-5">{{ __("Ctrl+Enter starts") }}</span>
					<div class="flex gap-2">
						<Button variant="ghost" @click="emit('update:modelValue', false)">{{ __("Cancel") }}</Button>
						<Button variant="solid" type="submit" :loading="saving">{{ __("Start timer") }}</Button>
					</div>
				</div>
			</form>
		</template>
	</Dialog>
</template>

<script setup>
import { computed, onBeforeUnmount, ref, watch } from "vue"
import { call } from "frappe-ui"
import { formatForApi, parseDatetimeLocalValue, toDatetimeLocalValue } from "@spa/utils/datetime.js"
import { __ } from "@spa/utils/i18n.js"
import { minutesToSeconds } from "@spa/utils/timerClock.js"
import spaConfig from "@/config"

const props = defineProps({ modelValue: { type: Boolean, default: false } })
const emit = defineEmits(["update:modelValue", "started"])

const API = spaConfig.api
const options = ref({ my_projects: [], recent_projects: [] })
const results = ref([])
const search = ref("")
const loading = ref(false)
const project = ref(null)
const info = ref(null)
const task = ref("")
const minutes = ref(60)
const goal = ref("")
const startTime = ref(toDatetimeLocalValue(new Date()))
const startEdited = ref(false)
const error = ref("")
const saving = ref(false)
let liveTimer = null
let searchTimer = null

const groups = computed(() => {
	if (search.value.trim().length >= 2) return results.value.length ? [{ label: "Open projects", rows: results.value }] : []
	const mine = options.value.my_projects || []
	const mineNames = new Set(mine.map((row) => row.name))
	const recent = (options.value.recent_projects || []).filter((row) => !mineNames.has(row.name))
	return [
		{ label: "My projects", rows: mine },
		{ label: "Recent", rows: recent },
	].filter((group) => group.rows.length)
})
const taskOptions = computed(() => [
	{ label: info.value?.task_rule === "Task is mandatory" ? __("Pick a task") : __("No task"), value: "" },
	...(info.value?.tasks || []).map((row) => ({ label: row.subject || row.name, value: row.name })),
])

function errorText(e, fallback) {
	return e?.messages?.[0] || e?.message || fallback
}

async function open() {
	error.value = ""
	project.value = null
	info.value = null
	task.value = ""
	minutes.value = 60
	goal.value = ""
	search.value = ""
	startEdited.value = false
	startTime.value = toDatetimeLocalValue(new Date())
	liveTimer = setInterval(() => {
		if (!startEdited.value) startTime.value = toDatetimeLocalValue(new Date())
	}, 15000)
	loading.value = true
	try {
		options.value = await call(`${API}.get_timer_options`)
	} catch (e) {
		error.value = errorText(e, __("Could not load your projects"))
	} finally {
		loading.value = false
	}
}

async function pick(row) {
	project.value = row
	try {
		info.value = await call(`${API}.get_timer_project_info`, { project: row.name })
	} catch (e) {
		error.value = errorText(e, __("Could not load the project"))
	}
}

function clearProject() {
	project.value = null
	info.value = null
	task.value = ""
}

async function submit() {
	error.value = ""
	const expected = minutesToSeconds(minutes.value)
	if (!project.value) return (error.value = __("Please pick a project."))
	if (info.value?.task_rule === "Task is mandatory" && !task.value) return (error.value = __("This project needs a task."))
	if (!expected) return (error.value = __("Minimum expected time is 15 minutes."))
	if (!goal.value.trim()) return (error.value = __("Please describe the goal."))
	const args = { project: project.value.name, expected_seconds: expected, goal: goal.value.trim(), task: task.value || null }
	if (startEdited.value) {
		const start = parseDatetimeLocalValue(startTime.value)
		if (start) args.manual_start_time = formatForApi(start)
	}
	saving.value = true
	try {
		const state = await call(`${API}.start_timer`, args)
		emit("started", state)
		emit("update:modelValue", false)
	} catch (e) {
		error.value = errorText(e, __("Could not start the timer"))
	} finally {
		saving.value = false
	}
}

watch(search, (value) => {
	clearTimeout(searchTimer)
	if (value.trim().length < 2) return (results.value = [])
	searchTimer = setTimeout(async () => {
		try {
			results.value = await call(`${API}.search_timer_projects`, { txt: value.trim() })
		} catch {
			results.value = []
		}
	}, 250)
})

watch(
	() => props.modelValue,
	(value) => {
		clearInterval(liveTimer)
		if (value) open()
	}
)
onBeforeUnmount(() => clearInterval(liveTimer))
</script>
