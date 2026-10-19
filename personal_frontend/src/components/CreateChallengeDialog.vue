<template>
	<Dialog
		:model-value="modelValue"
		:options="{ title: __('Set yourself a target'), size: 'lg' }"
		@update:model-value="emit('update:modelValue', $event)"
	>
		<template #body-content>
			<div class="space-y-4">
				<p class="text-sm text-ink-gray-6">
					{{ __("Private to you. Weekends, holidays and leave do not count. Jokers cover a day that slips.") }}
				</p>
				<FormControl v-model="kind" type="select" size="sm" :label="__('What counts')" :options="kindOptions" />
				<div v-if="kind === 'Planned and spontaneous'">
					<div class="grid grid-cols-2 gap-3">
						<FormControl v-model="targetPlanned" type="number" size="sm" :label="__('Planned a day')" :min="0" :max="10" />
						<FormControl v-model="targetSpontaneous" type="number" size="sm" :label="__('Spontaneous a day')" :min="0" :max="10" />
					</div>
					<p class="mt-1 text-xs text-ink-gray-5">
						{{ __("Planned: on your My Day plan when you start the day. Spontaneous: everything else you close.") }}
					</p>
					<p class="mt-1 text-xs text-ink-gray-5">{{ suggestionLine }}</p>
				</div>
				<div v-else>
					<FormControl
						v-model="target"
						type="number"
						size="sm"
						:label="kind === 'Important per day' ? __('Important ToDos a day') : __('ToDos closed a day')"
						:min="1"
						:max="suggestion?.max_target || 10"
					/>
					<p class="mt-1 text-xs text-ink-gray-5">{{ suggestionLine }}</p>
				</div>
				<div>
					<label class="mb-1.5 block text-xs text-ink-gray-5">{{ __("For how many working days") }}</label>
					<TabButtons v-model="length" :buttons="lengthButtons" />
				</div>
				<div>
					<label class="mb-1.5 block text-xs text-ink-gray-5">{{ __("Start") }}</label>
					<TabButtons v-model="start" :buttons="startButtons" />
					<p class="mt-1 text-xs text-ink-gray-5">{{ __("A Monday is a good fresh start.") }}</p>
				</div>
				<p class="text-xs text-ink-gray-5">
					{{
						kind === "Planned and spontaneous"
							? __("Quick wins (closed within 15 minutes of creating them) count as spontaneous, at most two a day. Dropped ToDos do not count.")
							: __("Quick wins closed within 15 minutes of creating them and dropped ToDos do not count.")
					}}
				</p>
				<ErrorMessage :message="error" />
				<div class="flex justify-end gap-2">
					<Button variant="ghost" @click="emit('update:modelValue', false)">{{ __("Cancel") }}</Button>
					<Button variant="solid" :loading="saving" :disabled="!validTarget" @click="create">{{ __("Start the challenge") }}</Button>
				</div>
			</div>
		</template>
	</Dialog>
</template>

<script setup>
import { computed, ref, watch } from "vue"
import { call, TabButtons } from "frappe-ui"
import { suggestionText } from "@spa/utils/challengeProgress.js"
import { formatDate } from "@spa/utils/datetime.js"
import { __ } from "@spa/utils/i18n.js"
import spaConfig from "@/config"

const props = defineProps({ modelValue: { type: Boolean, default: false } })
const emit = defineEmits(["update:modelValue", "created"])

const API = spaConfig.api
const KIND_OPTIONS = [
	{ label: "Closed ToDos", value: "Closes per day" },
	{ label: "Closed important ToDos", value: "Important per day" },
	{ label: "Planned and spontaneous closes", value: "Planned and spontaneous" },
]
const LENGTH_BUTTONS = [
	{ label: "5 days", value: "5" },
	{ label: "10 days", value: "10" },
	{ label: "20 days", value: "20" },
]

// Labels translated at render time; values stay English (they go to the API).
const kindOptions = computed(() => KIND_OPTIONS.map((o) => ({ ...o, label: __(o.label) })))
const lengthButtons = computed(() => LENGTH_BUTTONS.map((b) => ({ ...b, label: __(b.label) })))

const kind = ref("Closes per day")
const target = ref(2)
const targetPlanned = ref(2)
const targetSpontaneous = ref(1)
const length = ref("10")
const start = ref("monday")
const suggestion = ref(null)
const error = ref("")
const saving = ref(false)

const validTarget = computed(() => {
	const max = suggestion.value?.max_target || 10
	if (kind.value === "Planned and spontaneous") {
		const sum = Number(targetPlanned.value) + Number(targetSpontaneous.value)
		return Number(targetPlanned.value) >= 0 && Number(targetSpontaneous.value) >= 0 && sum >= 1 && sum <= max
	}
	return Number(target.value) >= 1 && Number(target.value) <= max
})
const suggestionLine = computed(() => suggestionText(suggestion.value))
const startButtons = computed(() => {
	const buttons = [{ label: __("Monday {0}", [formatDate(suggestion.value?.next_monday)]), value: "monday" }]
	if (suggestion.value?.today_is_working_day) buttons.unshift({ label: __("Today"), value: "today" })
	return buttons
})

async function loadSuggestion() {
	error.value = ""
	try {
		suggestion.value = await call(`${API}.suggest_challenge`, { kind: kind.value })
		target.value = suggestion.value.suggested
		targetPlanned.value = suggestion.value.suggested_planned
		targetSpontaneous.value = suggestion.value.suggested_spontaneous
	} catch (e) {
		error.value = e?.messages?.[0] || e?.message || __("Could not load your history")
	}
}

async function create() {
	saving.value = true
	error.value = ""
	try {
		const created = await call(`${API}.create_challenge`, {
			kind: kind.value,
			target_per_day: Number(target.value),
			target_planned: Number(targetPlanned.value),
			target_spontaneous: Number(targetSpontaneous.value),
			working_days: Number(length.value),
			start_date: start.value === "today" ? suggestion.value.today : suggestion.value.next_monday,
		})
		emit("created", created)
		emit("update:modelValue", false)
	} catch (e) {
		error.value = e?.messages?.[0] || e?.message || __("Could not start the challenge")
	} finally {
		saving.value = false
	}
}

watch(
	() => props.modelValue,
	(open) => {
		if (open) loadSuggestion()
	}
)
watch(kind, () => props.modelValue && loadSuggestion())
</script>
