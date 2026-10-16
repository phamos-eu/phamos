<template>
	<Dialog :model-value="modelValue" :options="{ title: 'A timer is still running', size: 'sm' }" @update:model-value="close">
		<template #body-content>
			<div class="space-y-4">
				<p class="text-sm text-ink-gray-7">
					{{ session?.project_name }} · {{ clock }}. Stop it before you check out, so it does not run on overnight?
				</p>
				<div class="flex flex-col gap-2">
					<Button variant="solid" @click="choose('stop')">Stop timer and check out</Button>
					<Button @click="choose('anyway')">Check out anyway</Button>
					<Button variant="ghost" @click="close(false)">Cancel</Button>
				</div>
			</div>
		</template>
	</Dialog>
</template>

<script setup>
import { computed } from "vue"
import { formatClock, liveElapsed } from "@spa/utils/timerClock.js"
import { timer } from "@spa/timerStore.js"

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
