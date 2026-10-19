<template>
	<Dialog
		:model-value="modelValue"
		:options="{ title: __('Implementation time limit reached'), size: 'md' }"
		@update:model-value="emit('update:modelValue', $event)"
	>
		<template #body-content>
			<div v-if="session" class="space-y-4">
				<p class="text-sm text-ink-gray-7">
					{{
						__(
							"This session needs {0} billable, but only {1} of {2} are left for this implementation. The record is saved and waits for your decision.",
							[hours(limit.requested_hours), hours(limit.remaining_hours), hours(limit.limit_hours)]
						)
					}}
				</p>
				<ErrorMessage :message="error" />
				<div class="flex flex-col gap-2">
					<Button variant="solid" :loading="busy === 'continue'" @click="act('continue')">
						{{ __("Continue with the available hours") }}
					</Button>
					<Button :loading="busy === 'notify'" @click="act('notify')">{{ __("Notify the account manager") }}</Button>
					<Button variant="ghost" @click="emit('update:modelValue', false)">{{ __("Decide later") }}</Button>
				</div>
				<p class="text-xs text-ink-gray-5">
					{{
						__(
							"Continue keeps your times and lowers the billable share so it fits. Notify sends the account manager an email and leaves the record as it is."
						)
					}}
				</p>
			</div>
		</template>
	</Dialog>
</template>

<script setup>
import { computed, ref } from "vue"
import { call } from "frappe-ui"
import { __ } from "@spa/utils/i18n.js"
import spaConfig from "@/config"

const props = defineProps({
	modelValue: { type: Boolean, default: false },
	session: { type: Object, default: null },
})
const emit = defineEmits(["update:modelValue", "done"])

const API = spaConfig.api
const busy = ref("")
const error = ref("")
const limit = computed(() => props.session?.limit || {})

function hours(value) {
	const number = Number(value || 0)
	return __("{0} h", [Math.round(number * 100) / 100])
}

async function act(kind) {
	busy.value = kind
	error.value = ""
	try {
		const method = kind === "continue" ? "continue_timer_with_available_hours" : "notify_timer_account_manager"
		const state = await call(`${API}.${method}`, { name: props.session.name })
		emit("done", state, kind)
		emit("update:modelValue", false)
	} catch (e) {
		error.value = e?.messages?.[0] || e?.message || __("That did not work")
	} finally {
		busy.value = ""
	}
}
</script>
