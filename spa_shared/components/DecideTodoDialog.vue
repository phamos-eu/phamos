<template>
	<Dialog
		:options="{ title: dialogTitle, size: 'xl' }"
		:model-value="modelValue"
		@update:model-value="emit('update:modelValue', $event)"
	>
		<template #body-content>
			<div v-if="current" class="space-y-4">
				<div class="rounded-md bg-surface-gray-2 px-3 py-2">
					<div class="text-sm font-medium text-ink-gray-9">{{ current.summary || "(no description)" }}</div>
					<div class="mt-1 text-xs text-ink-gray-6">{{ facts }}</div>
				</div>

				<div role="radiogroup" aria-label="Decision" class="space-y-2">
					<button
						v-for="option in OPTIONS"
						:key="option.value"
						type="button"
						role="radio"
						:aria-checked="choice === option.value"
						class="flex w-full items-start gap-3 rounded-md border px-3 py-2 text-left transition"
						:class="
							choice === option.value
								? 'border-outline-gray-4 bg-surface-gray-2'
								: 'border-outline-gray-2 hover:bg-surface-gray-1'
						"
						@click="choice = option.value"
					>
						<FeatherIcon :name="option.icon" class="mt-0.5 h-4 w-4 flex-none text-ink-gray-6" />
						<span class="min-w-0">
							<span class="block text-sm font-medium text-ink-gray-9">{{ option.label }}</span>
							<span class="block text-xs text-ink-gray-5">{{ option.hint }}</span>
						</span>
					</button>
				</div>

				<FormControl
					v-if="choice === 'plan'"
					v-model="planDate"
					label="New due date"
					type="date"
					size="sm"
					:min="today"
				/>
				<div v-if="choice === 'drop'" class="space-y-2">
					<FormControl v-model="dropReason" label="Why drop it?" type="select" size="sm" :options="DROP_REASONS" />
					<FormControl
						v-if="dropReason === 'Other'"
						v-model="dropOther"
						type="text"
						size="sm"
						placeholder="A few words for later"
					/>
					<p class="text-xs text-ink-gray-5">
						Dropping is a decision, not a failure. The ToDo is cancelled and stays visible in Desk.
					</p>
				</div>

				<ErrorMessage :message="error" />

				<div class="flex items-center justify-between gap-3 pt-1">
					<span class="text-xs text-ink-gray-5">{{ progressLabel }}</span>
					<div class="flex gap-2">
						<Button v-if="queueMode" variant="ghost" @click="next">Skip</Button>
						<Button variant="solid" :disabled="!canApply" :loading="saving" @click="apply">
							{{ applyLabel }}
						</Button>
					</div>
				</div>
			</div>
			<div v-else class="space-y-3 text-sm text-ink-gray-7">
				<p>All decided. Nothing left in this queue.</p>
				<Button variant="solid" @click="emit('update:modelValue', false)">Close</Button>
			</div>
		</template>
	</Dialog>
</template>

<script setup>
import { computed, ref, watch } from "vue"
import { call, toast } from "frappe-ui"
import { formatDate, todayIsoInUserTz } from "@spa/utils/datetime.js"
import { ageLabel } from "@spa/utils/dashboardFormat.js"
import spaConfig from "@/config"

const props = defineProps({
	modelValue: { type: Boolean, default: false },
	// One ToDo row, or several for "Decide all" (rows from the list or the dashboard).
	todos: { type: Array, default: () => [] },
})

const emit = defineEmits(["update:modelValue", "decided"])

const API = spaConfig.api
const DROP_REASONS = ["Not needed any more", "Done elsewhere", "Out of date", "Other"]
const OPTIONS = [
	{ value: "today", label: "Do it today", icon: "sun", hint: "Due today, so it is on top of the list." },
	{ value: "later_this_week", label: "Later this week", icon: "calendar", hint: "Due on Friday (or next Tuesday from Friday on)." },
	{ value: "plan", label: "Pick a date", icon: "clock", hint: "A concrete day instead of \"someday\"." },
	{ value: "drop", label: "Drop it", icon: "x-circle", hint: "Not worth doing any more. Counts as decided, not as done." },
]

const index = ref(0)
const choice = ref("today")
const planDate = ref("")
const dropReason = ref(DROP_REASONS[0])
const dropOther = ref("")
const saving = ref(false)
const error = ref("")
const today = computed(() => todayIsoInUserTz())

const queueMode = computed(() => props.todos.length > 1)
const current = computed(() => props.todos[index.value] || null)
const dialogTitle = computed(() => (queueMode.value ? "Decide on stale ToDos" : "Decide on this ToDo"))
const progressLabel = computed(() => (queueMode.value ? `${index.value + 1} of ${props.todos.length}` : ""))
const applyLabel = computed(() => (queueMode.value && index.value < props.todos.length - 1 ? "Apply and next" : "Apply"))

const facts = computed(() => {
	const todo = current.value
	if (!todo) return ""
	const parts = []
	if (todo.age_days != null) parts.push(`${ageLabel(todo.age_days)} old`)
	else if (todo.creation) parts.push(`created ${formatDate(String(todo.creation).slice(0, 10))}`)
	if (todo.date) parts.push(`${todo.overdue ? "overdue since" : "due"} ${formatDate(todo.date)}`)
	if (todo.reschedule_count) parts.push(`postponed ${todo.reschedule_count}×`)
	if (todo.first_due_date && todo.first_due_date !== todo.date) parts.push(`first due ${formatDate(todo.first_due_date)}`)
	return parts.join(" · ")
})

const canApply = computed(() => {
	if (choice.value === "plan") return Boolean(planDate.value)
	if (choice.value === "drop") return dropReason.value !== "Other" || Boolean(dropOther.value.trim())
	return true
})

function reset() {
	choice.value = "today"
	planDate.value = ""
	dropReason.value = DROP_REASONS[0]
	dropOther.value = ""
	error.value = ""
}

watch(
	() => props.modelValue,
	(open) => {
		if (!open) return
		index.value = 0
		reset()
	}
)

function next() {
	index.value += 1
	reset()
}

async function apply() {
	if (!current.value || !canApply.value) return
	saving.value = true
	error.value = ""
	try {
		const result = await call(`${API}.decide_todo`, {
			name: current.value.name,
			action: choice.value,
			date: choice.value === "plan" ? planDate.value : null,
			reason: choice.value === "drop" ? (dropReason.value === "Other" ? dropOther.value.trim() : dropReason.value) : null,
		})
		emit("decided", { todo: result, action: choice.value })
		if (!queueMode.value) {
			toast({ title: choice.value === "drop" ? "Dropped" : "Decided", icon: "check-circle", iconClasses: "text-ink-green-3" })
			emit("update:modelValue", false)
			return
		}
		next()
	} catch (e) {
		error.value = e?.messages?.[0] || e?.message || "Could not apply the decision"
	} finally {
		saving.value = false
	}
}
</script>
