<template>
	<Dialog
		:model-value="modelValue"
		:options="{ title: 'Shut down the day', size: '2xl' }"
		@update:model-value="emit('update:modelValue', $event)"
	>
		<template #body-content>
			<div class="space-y-5">
				<section>
					<h3 class="mb-1 text-sm font-semibold text-ink-gray-9">Done today</h3>
					<p v-if="!done.length" class="text-sm text-ink-gray-5">Nothing from the plan. Some days are like that.</p>
					<ul class="space-y-0.5 text-sm text-ink-gray-7">
						<li v-for="item in done" :key="item.todo" class="flex gap-2">
							<FeatherIcon name="check" class="mt-0.5 h-4 w-4 flex-none text-ink-green-3" />{{ item.summary }}
						</li>
					</ul>
				</section>

				<section v-if="open.length">
					<h3 class="mb-1 text-sm font-semibold text-ink-gray-9">Still open: when is the next step?</h3>
					<ul class="space-y-3">
						<li v-for="item in open" :key="item.todo" class="rounded-md border border-outline-gray-2 p-3">
							<div class="mb-2 text-sm text-ink-gray-9">{{ item.summary }}</div>
							<div class="flex flex-wrap items-center gap-2">
								<TabButtons v-model="choices[item.todo].action" :buttons="ACTIONS" />
								<FormControl
									v-if="choices[item.todo].action === 'plan'"
									v-model="choices[item.todo].date"
									type="date"
									size="sm"
									:min="plan.today"
									aria-label="New date"
								/>
								<FormControl
									v-if="choices[item.todo].action === 'drop'"
									v-model="choices[item.todo].reason"
									type="select"
									size="sm"
									:options="DROP_REASONS"
									aria-label="Why drop it"
								/>
							</div>
						</li>
					</ul>
				</section>

				<FormControl
					v-model="reflection"
					type="text"
					size="sm"
					label="One line about today (optional, only for you)"
					placeholder="What went well, what got in the way?"
				/>
				<ErrorMessage :message="error" />
				<div class="flex justify-end gap-2">
					<Button variant="ghost" @click="emit('update:modelValue', false)">Not yet</Button>
					<Button variant="solid" :loading="saving" :disabled="!complete" @click="submit">Done for the day</Button>
				</div>
			</div>
		</template>
	</Dialog>
</template>

<script setup>
import { computed, reactive, ref, watch } from "vue"
import { call, TabButtons } from "frappe-ui"
import spaConfig from "@/config"

const props = defineProps({
	modelValue: { type: Boolean, default: false },
	plan: { type: Object, required: true },
})
const emit = defineEmits(["update:modelValue", "done"])

const ACTIONS = [
	{ label: "Tomorrow", value: "tomorrow" },
	{ label: "Later this week", value: "later_this_week" },
	{ label: "Pick a date", value: "plan" },
	{ label: "Drop", value: "drop" },
	{ label: "Keep open", value: "keep" },
]
const DROP_REASONS = ["Not needed any more", "Done elsewhere", "Out of date", "Other"]

const choices = reactive({})
const reflection = ref("")
const error = ref("")
const saving = ref(false)

const done = computed(() => props.plan.items.filter((i) => i.outcome === "Done"))
const open = computed(() => props.plan.items.filter((i) => i.outcome === "Open"))
const complete = computed(() =>
	open.value.every((item) => {
		const choice = choices[item.todo]
		return choice && choice.action && (choice.action !== "plan" || choice.date)
	})
)

function reset() {
	for (const key of Object.keys(choices)) delete choices[key]
	for (const item of open.value) {
		choices[item.todo] = { action: "tomorrow", date: "", reason: DROP_REASONS[0] }
	}
	reflection.value = ""
	error.value = ""
}

async function submit() {
	saving.value = true
	error.value = ""
	try {
		const decisions = open.value.map((item) => ({ todo: item.todo, ...choices[item.todo] }))
		const result = await call(`${spaConfig.api}.shutdown_day`, {
			decisions,
			reflection: reflection.value,
			date: props.plan.date,
		})
		emit("done", result)
		emit("update:modelValue", false)
	} catch (e) {
		error.value = e?.messages?.[0] || e?.message || "Could not shut down the day"
	} finally {
		saving.value = false
	}
}

watch(
	() => props.modelValue,
	(value) => {
		if (value) reset()
	}
)
</script>
