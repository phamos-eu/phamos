<template>
	<Dialog :model-value="modelValue" :options="{ title: __('A timer is still running'), size: 'sm' }" @update:model-value="close">
		<template #body-content>
			<div class="space-y-4">
				<p class="text-sm text-ink-gray-7">
					{{ __("{0} · {1}. Stop it before you check out, so it does not run on overnight?", [session?.project_name, clock]) }}
				</p>
				<div class="flex flex-col gap-2">
					<Button variant="solid" @click="choose('stop')">{{ __("Stop timer and check out") }}</Button>
					<Button @click="choose('anyway')">{{ __("Check out anyway") }}</Button>
					<Button variant="ghost" @click="close(false)">{{ __("Cancel") }}</Button>
				</div>
			</div>
		</template>
	</Dialog>
</template>

<script setup>
import { computed } from "vue"
import { formatClock, liveElapsed } from "@spa/utils/timerClock.js"
import { timer } from "@spa/timerStore.js"
import { __ } from "@spa/utils/i18n.js"

defineProps({ modelValue: { type: Boolean, default: false } })
const emit = defineEmits(["update:modelValue", "choose"])

const session = computed(() => timer.state?.session)
const clock = computed(() => formatClock(liveElapsed(session.value, (Date.now() - timer.loadedAt) / 1000)))

function choose(choice) {
	emit("choose", choice)
	emit("update:modelValue", false)
}

function close(value) {
	if (!value) {
		emit("choose", "cancel")
		emit("update:modelValue", false)
	}
}
</script>
