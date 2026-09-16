<template>
	<div class="rounded-md border border-outline-gray-2">
		<div class="flex flex-wrap items-center gap-2 border-b border-outline-gray-2 px-2.5 py-2">
			<span class="text-[11px] font-semibold uppercase tracking-wide text-ink-gray-6">Calendars</span>
			<button
				v-for="user in users"
				:key="user.name"
				type="button"
				class="rounded-full border px-2 py-0.5 text-xs transition"
				:class="
					shownUsers.has(user.name)
						? 'border-transparent bg-surface-gray-7 text-ink-white'
						: 'border-outline-gray-2 text-ink-gray-6 hover:bg-surface-gray-2'
				"
				:aria-pressed="shownUsers.has(user.name)"
				@click="toggleUser(user.name)"
			>
				{{ user.full_name || user.name }}
			</button>
			<span v-if="!users.length" class="text-xs text-ink-gray-5">No users to show</span>
		</div>

		<div class="max-h-56 overflow-y-auto">
			<button
				v-for="slot in timeSlots"
				:key="slot.starts_on"
				type="button"
				class="flex w-full items-center gap-3 border-b border-outline-gray-1 px-2.5 py-1 text-left text-xs last:border-0"
				:class="
					isProposed(slot.starts_on)
						? 'bg-surface-gray-7 text-ink-white'
						: 'text-ink-gray-7 hover:bg-surface-gray-2'
				"
				@click="emit('propose', slot)"
			>
				<span class="w-12 flex-none tabular-nums">{{ slot.label }}</span>
				<span class="min-w-0 flex-1 truncate">
					{{ isProposed(slot.starts_on) ? "Proposed" : "" }}
				</span>
			</button>
		</div>

		<!-- Be explicit that this is empty because nothing is connected, rather
		     than letting an empty grid read as "everyone is free". -->
		<p class="border-t border-outline-gray-2 px-2.5 py-1.5 text-[11px] text-ink-gray-5">
			{{
				shownUsers.size
					? "No connected calendars yet — busy times aren't shown, so pick a time you know works."
					: "Select a calendar above to preview availability once calendars are connected."
			}}
		</p>
	</div>
</template>

<script setup>
import { computed, ref } from "vue"

const props = defineProps({
	/** Day being planned, as YYYY-MM-DD */
	day: { type: String, default: "" },
	durationMinutes: { type: [String, Number], default: 60 },
	/** Selectable calendars: [{ name, full_name }] */
	users: { type: Array, default: () => [] },
	/** Already-proposed slots, to mark in the grid */
	proposals: { type: Array, default: () => [] },
	startHour: { type: Number, default: 8 },
	endHour: { type: Number, default: 18 },
	stepMinutes: { type: Number, default: 30 },
})

const emit = defineEmits(["propose"])

const shownUsers = ref(new Set())

function toggleUser(name) {
	const next = new Set(shownUsers.value)
	if (next.has(name)) next.delete(name)
	else next.add(name)
	shownUsers.value = next
}

function pad(n) {
	return String(n).padStart(2, "0")
}

/** Naive local 'YYYY-MM-DD HH:mm:ss', the same shape the backend stores. */
function stamp(minutesFromMidnight) {
	const hours = Math.floor(minutesFromMidnight / 60)
	const minutes = minutesFromMidnight % 60
	return `${props.day} ${pad(hours)}:${pad(minutes)}:00`
}

const timeSlots = computed(() => {
	if (!props.day) return []
	const duration = Number(props.durationMinutes) || 60
	const slots = []
	for (let m = props.startHour * 60; m + duration <= props.endHour * 60; m += props.stepMinutes) {
		slots.push({
			starts_on: stamp(m),
			ends_on: stamp(m + duration),
			label: `${pad(Math.floor(m / 60))}:${pad(m % 60)}`,
		})
	}
	return slots
})

function isProposed(startsOn) {
	return props.proposals.some((p) => p.starts_on === startsOn)
}
</script>
