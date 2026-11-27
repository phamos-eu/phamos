<template>
	<!--
		A meeting chat waiting for me while I'm elsewhere on the map (#2066): its room emptied and the
		grace time runs, or a Keep/Burn vote misses my vote.
	-->
	<div
		class="flex w-80 items-center gap-3 rounded-xl border border-outline-gray-2 bg-surface-white px-3 py-2.5 text-ink-gray-9 shadow-xl"
		role="status"
		data-testid="batch-notice"
	>
		<FeatherIcon :name="voting ? 'users' : 'clock'" class="h-5 w-5 flex-shrink-0 text-ink-gray-6" />
		<div class="min-w-0 flex-1">
			<p class="truncate text-sm font-medium">{{ __("Chat of {0}", [notice.area_title]) }}</p>
			<p class="text-xs text-ink-gray-6">{{ line }}</p>
		</div>
		<div class="flex flex-shrink-0 flex-col gap-1">
			<Button
				v-if="!voting && !kept"
				size="sm"
				variant="solid"
				:loading="busy === 'Keep'"
				@click="$emit('vote', 'Keep')"
			>
				{{ __("Save") }}
			</Button>
			<template v-if="voting">
				<Button size="sm" variant="solid" :loading="busy === 'Keep'" @click="$emit('vote', 'Keep')">{{ __("Keep") }}</Button>
				<Button size="sm" variant="subtle" theme="red" :loading="busy === 'Burn'" @click="$emit('vote', 'Burn')">
					{{ __("Burn") }}
				</Button>
			</template>
			<Button v-if="kept && !voting" size="sm" variant="ghost" @click="$emit('dismiss')">{{ __("OK") }}</Button>
		</div>
	</div>
</template>

<script setup>
import { computed } from "vue"
import { Button, FeatherIcon } from "frappe-ui"
import { __ } from "@spa/utils/i18n.js"
import { relativeTime } from "../utils/ophiceTime.js"

const props = defineProps({
	/** a row of get_batch_notices, plus `loadedAt` (ms) to anchor its "seconds from now" */
	notice: { type: Object, required: true },
	now: { type: Number, required: true },
	busy: { type: String, default: "" },
})
defineEmits(["vote", "dismiss"])

const voting = computed(() => !!props.notice.vote_until && !props.notice.my_vote)
const kept = computed(() => props.notice.mode === "Saved" || props.notice.saved)

function at(seconds) {
	return new Date(props.notice.loadedAt + (seconds || 0) * 1000)
}

const line = computed(() => {
	const current = new Date(props.now)
	if (voting.value) {
		return __("{0} keep, {1} burn. Your vote? Decided {2} at the latest; a tie keeps it.", [
			props.notice.keep_votes,
			props.notice.burn_votes,
			relativeTime(at(props.notice.vote_in), current),
		])
	}
	if (kept.value) return __("The room is empty. The chat will be kept.")
	return __("The room is empty. Deleted {0} unless someone saves it.", [relativeTime(at(props.notice.grace_in), current)])
})
</script>
