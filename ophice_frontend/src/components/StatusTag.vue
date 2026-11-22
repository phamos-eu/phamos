<template>
	<!-- A chip's status (#2053), floating above it: "Be right back" or "Away" with the return time. -->
	<div
		class="status-tag pointer-events-none absolute z-10 max-w-56 rounded-lg px-2 py-1 text-xs leading-snug shadow-md"
		:class="status.kind === 'away' ? 'status-tag--away' : 'status-tag--brb'"
		data-testid="status-tag"
	>
		<div class="flex items-center gap-1 font-semibold">
			<FeatherIcon :name="status.kind === 'away' ? 'moon' : 'coffee'" class="h-3 w-3 flex-shrink-0" />
			<span class="truncate">{{ status.kind === "away" ? __("Away") : __("Be right back") }}</span>
		</div>
		<div v-if="status.note" class="line-clamp-2 break-words">{{ status.note }}</div>
		<template v-if="back">
			<div class="font-medium" :class="{ 'opacity-80': back.overdue }">
				{{ back.overdue ? __("Was due back at {0}", [back.time]) : __("Back at {0}", [back.time]) }}
				<span class="opacity-80">· {{ back.relative }}</span>
			</div>
			<div v-if="back.theirs" class="opacity-80">
				{{ __("{0} local time in {1}", [back.theirs.time, back.theirs.place]) }}
			</div>
		</template>
	</div>
</template>

<script setup>
import { computed } from "vue"
import { FeatherIcon } from "frappe-ui"
import { __ } from "@spa/utils/i18n.js"
import { clockTime, relativeTime, theirClock } from "../utils/ophiceTime.js"

const props = defineProps({
	/** { kind: "brb" | "away", note, until (UTC ISO), tz } */
	status: { type: Object, required: true },
	/** Date.now(), ticking, for "in 20 minutes" */
	now: { type: Number, required: true },
})

const back = computed(() => {
	if (!props.status.until) return null
	const until = new Date(props.status.until)
	if (Number.isNaN(until.getTime())) return null
	const now = new Date(props.now)
	return {
		time: clockTime(until, now),
		relative: relativeTime(until, now),
		overdue: until < now,
		theirs: theirClock(until, props.status.tz, now),
	}
})
</script>

<style scoped>
/* Readable on any map: solid colours, a dark edge, and a small tail pointing at the chip. */
.status-tag {
	color: #fff;
	border: 1px solid rgba(0, 0, 0, 0.35);
}
.status-tag--brb {
	background: rgb(180, 83, 9);
}
.status-tag--away {
	background: rgb(71, 85, 105);
}
.status-tag::after {
	content: "";
	position: absolute;
	left: var(--tail, 50%);
	bottom: -5px;
	width: 8px;
	height: 8px;
	transform: translateX(-50%) rotate(45deg);
	background: inherit;
	border-right: 1px solid rgba(0, 0, 0, 0.35);
	border-bottom: 1px solid rgba(0, 0, 0, 0.35);
}
</style>
