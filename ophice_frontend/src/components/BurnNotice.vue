<template>
	<!-- Burn notice (#2057): a parted encounter chat burns when the countdown ends, unless both save it. -->
	<div
		class="flex w-80 items-center gap-3 rounded-xl border border-outline-gray-2 bg-surface-white px-3 py-2.5 text-ink-gray-9 shadow-xl"
		role="status"
		data-testid="burn-notice"
	>
		<UserAvatar :name="notice.with" :label="notice.full_name" :image="notice.user_image" size="sm" />
		<div class="min-w-0 flex-1">
			<template v-if="notice.state === 'saved'">
				<p class="text-sm font-medium">{{ __("Kept") }}</p>
				<p class="truncate text-xs text-ink-gray-6">{{ __("Moved to your Raven chat with {0}.", [firstName]) }}</p>
			</template>
			<template v-else-if="notice.state === 'burned'">
				<p class="text-sm font-medium">{{ __("Burned") }} 🔥</p>
				<p class="truncate text-xs text-ink-gray-6">{{ __("The chat with {0} is gone.", [firstName]) }}</p>
			</template>
			<template v-else>
				<p class="truncate text-sm font-medium">
					{{ __("Chat with {0} burns in {1}", [firstName, clock]) }}
				</p>
				<p class="truncate text-xs text-ink-gray-6">{{ status }}</p>
				<div class="mt-1.5 h-1 overflow-hidden rounded-full bg-surface-gray-3">
					<div class="h-full rounded-full bg-surface-red-5 transition-[width] duration-200 ease-linear" :style="{ width: `${share * 100}%` }" />
				</div>
			</template>
		</div>
		<Button
			v-if="!notice.state"
			:variant="notice.saved_by_me ? 'subtle' : 'solid'"
			:disabled="notice.saved_by_me || saving"
			:label="notice.saved_by_me ? __('Saved') : __('Save')"
			@click="$emit('save')"
		/>
	</div>
</template>

<script setup>
import { computed } from "vue"
import { Button } from "frappe-ui"
import UserAvatar from "@spa/components/UserAvatar.vue"
import { __ } from "@spa/utils/i18n.js"

const props = defineProps({
	/** { with, full_name, user_image, deadline (ms), total (s), saved_by_me, saved_by_peer, state } */
	notice: { type: Object, required: true },
	/** Date.now(), ticking while notices run */
	now: { type: Number, required: true },
	saving: { type: Boolean, default: false },
})
defineEmits(["save"])

const firstName = computed(() => (props.notice.full_name || "").split(" ")[0] || props.notice.full_name)
const left = computed(() => Math.max(0, Math.ceil((props.notice.deadline - props.now) / 1000)))
const clock = computed(() => `${Math.floor(left.value / 60)}:${String(left.value % 60).padStart(2, "0")}`)
const share = computed(() => Math.min(1, left.value / (props.notice.total || 60)))
const status = computed(() => {
	const { saved_by_me: me, saved_by_peer: peer } = props.notice
	if (me && !peer) return __("You want to keep it. Waiting for {0}.", [firstName.value])
	if (peer && !me) return __("{0} wants to keep it. Save to keep it.", [firstName.value])
	return __("Kept only if you both save it.")
})
</script>
