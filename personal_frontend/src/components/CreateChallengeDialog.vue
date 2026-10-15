<template>
	<Dialog
		:model-value="modelValue"
		:options="{ title: 'Set yourself a target', size: 'lg' }"
		@update:model-value="emit('update:modelValue', $event)"
	>
		<template #body-content>
			<div class="space-y-4">
				<p class="text-sm text-ink-gray-6">
					Private to you. Weekends, holidays and leave do not count. Jokers cover a day that slips.
				</p>
				<FormControl v-model="kind" type="select" size="sm" label="What counts" :options="KIND_OPTIONS" />
				<div>
					<FormControl
						v-model="target"
						type="number"
						size="sm"
						:label="kind === 'Important per day' ? 'Important ToDos a day' : 'ToDos closed a day'"
						:min="1"
						:max="suggestion?.max_target || 10"
					/>
					<p class="mt-1 text-xs text-ink-gray-5">{{ suggestionLine }}</p>
				</div>
				<div>
					<label class="mb-1.5 block text-xs text-ink-gray-5">For how many working days</label>
					<TabButtons v-model="length" :buttons="LENGTH_BUTTONS" />
				</div>
				<div>
					<label class="mb-1.5 block text-xs text-ink-gray-5">Start</label>
					<TabButtons v-model="start" :buttons="startButtons" />
					<p class="mt-1 text-xs text-ink-gray-5">A Monday is a good fresh start.</p>
				</div>
				<p class="text-xs text-ink-gray-5">
					Quick wins closed within 15 minutes of creating them and dropped ToDos do not count.
				</p>
				<ErrorMessage :message="error" />
				<div class="flex justify-end gap-2">
					<Button variant="ghost" @click="emit('update:modelValue', false)">Cancel</Button>
					<Button variant="solid" :loading="saving" :disabled="!validTarget" @click="create">Start the challenge</Button>
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
import spaConfig from "@/config"

const props = defineProps({ modelValue: { type: Boolean, default: false } })
const emit = defineEmits(["update:modelValue", "created"])

const API = spaConfig.api
const KIND_OPTIONS = [
	{ label: "Closed ToDos", value: "Closes per day" },
	{ label: "Closed important ToDos", value: "Important per day" },
]
const LENGTH_BUTTONS = [
	{ label: "5 days", value: "5" },
	{ label: "10 days", value: "10" },
	{ label: "20 days", value: "20" },
]

const kind = ref("Closes per day")
const target = ref(2)
const length = ref("10")
const start = ref("monday")
const suggestion = ref(null)
const error = ref("")
const saving = ref(false)

const validTarget = computed(() => Number(target.value) >= 1 && Number(target.value) <= (suggestion.value?.max_target || 10))
const suggestionLine = computed(() => suggestionText(suggestion.value))
const startButtons = computed(() => {
	const buttons = [{ label: `Monday ${formatDate(suggestion.value?.next_monday)}`, value: "monday" }]
	if (suggestion.value?.today_is_working_day) buttons.unshift({ label: "Today", value: "today" })
	return buttons
})

async function loadSuggestion() {
	error.value = ""
	try {
		suggestion.value = await call(`${API}.suggest_challenge`, { kind: kind.value })
		target.value = suggestion.value.suggested
	} catch (e) {
		error.value = e?.messages?.[0] || e?.message || "Could not load your history"
	}
}

async function create() {
	saving.value = true
	error.value = ""
	try {
		const created = await call(`${API}.create_challenge`, {
			kind: kind.value,
			target_per_day: Number(target.value),
			working_days: Number(length.value),
			start_date: start.value === "today" ? suggestion.value.today : suggestion.value.next_monday,
		})
		emit("created", created)
		emit("update:modelValue", false)
	} catch (e) {
		error.value = e?.messages?.[0] || e?.message || "Could not start the challenge"
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
