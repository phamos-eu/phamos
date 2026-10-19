<template>
	<Dialog
		:model-value="modelValue"
		:options="{ title: __('Pause for a break'), size: 'md' }"
		@update:model-value="emit('update:modelValue', $event)"
	>
		<template #body-content>
			<form class="space-y-4" @submit.prevent="submit" @keydown.enter.ctrl.prevent="submit" @keydown.enter.meta.prevent="submit">
				<div ref="goalHost">
					<FormControl v-model="goal" type="text" size="sm" :label="__('What is the break for?') + ' *'" :placeholder="__('Lunch, a call, coffee with the team…')" />
				</div>
				<FormControl v-model="minutes" type="number" size="sm" :label="__('Estimated minutes') + ' *'" :min="1" :step="5" />
				<p class="text-xs text-ink-gray-5">{{ __("When you resume you decide whether the break is tracked as its own record.") }}</p>
				<ErrorMessage :message="error" />
				<div class="flex justify-end gap-2">
					<Button variant="ghost" @click="emit('update:modelValue', false)">{{ __("Keep working") }}</Button>
					<Button variant="solid" type="submit" :loading="saving">{{ __("Pause") }}</Button>
				</div>
			</form>
		</template>
	</Dialog>
</template>

<script setup>
import { nextTick, ref, watch } from "vue"
import { call } from "frappe-ui"
import { MIN_BREAK_MINUTES, minutesToSeconds } from "@spa/utils/timerClock.js"
import { __ } from "@spa/utils/i18n.js"
import spaConfig from "@/config"

const props = defineProps({
	modelValue: { type: Boolean, default: false },
	session: { type: Object, default: null },
})
const emit = defineEmits(["update:modelValue", "paused"])

const goalHost = ref(null)
const goal = ref("")
const minutes = ref(15)
const error = ref("")
const saving = ref(false)

async function submit() {
	error.value = ""
	const expected = minutesToSeconds(minutes.value, MIN_BREAK_MINUTES)
	if (!goal.value.trim()) return (error.value = __("Please say what the break is for."))
	if (!expected) return (error.value = __("Please estimate the break in minutes."))
	saving.value = true
	try {
		const state = await call(`${spaConfig.api}.pause_timer`, {
			name: props.session.name,
			break_goal: goal.value.trim(),
			break_expected_seconds: expected,
		})
		emit("paused", state)
		emit("update:modelValue", false)
	} catch (e) {
		error.value = e?.messages?.[0] || e?.message || __("Could not pause the timer")
	} finally {
		saving.value = false
	}
}

watch(
	() => props.modelValue,
	(open) => {
		if (!open) return
		goal.value = ""
		minutes.value = 15
		error.value = ""
		// Let the dialog mount and trap focus first.
		nextTick(() => setTimeout(() => goalHost.value?.querySelector("input")?.focus(), 50))
	}
)
</script>
