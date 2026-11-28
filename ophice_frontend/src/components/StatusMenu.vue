<template>
	<!--
		My status (#2053): available, be right back, or away until a time. From my own chip, my
		timesheet timer comes first (#2101, the `top` slot).
	-->
	<div
		class="w-80 space-y-3 rounded-xl border border-outline-gray-2 bg-surface-white p-3 text-sm text-ink-gray-9 shadow-xl"
		role="dialog"
		:aria-label="__('My status')"
		data-testid="status-menu"
		@keydown.esc.stop.prevent="$emit('close')"
	>
		<template v-if="$slots.top">
			<slot name="top" />
			<div class="border-t border-outline-gray-1" />
		</template>
		<div ref="root" class="space-y-3">
			<div v-if="$slots.top" class="text-xs font-medium text-ink-gray-5">{{ __("Availability") }}</div>
			<div class="flex gap-1 rounded-lg bg-surface-gray-2 p-1">
				<button
					v-for="option in options"
					:key="option.kind"
					type="button"
					class="flex flex-1 items-center justify-center gap-1 rounded-md px-2 py-1 text-xs"
					:class="kind === option.kind ? 'bg-surface-white font-medium text-ink-gray-9 shadow-sm' : 'text-ink-gray-6 hover:text-ink-gray-8'"
					:data-testid="`status-${option.kind || 'available'}`"
					@click="kind = option.kind"
				>
					<FeatherIcon :name="option.icon" class="h-3.5 w-3.5" />
					{{ option.label }}
				</button>
			</div>
			<form v-if="kind" class="space-y-3" @submit.prevent="save">
				<FormControl
					v-model="note"
					:label="__('Note')"
					:placeholder="kind === 'away' ? __('Doctor\'s appointment') : __('Getting a coffee')"
					:maxlength="140"
					autofocus
				/>
				<div v-if="kind === 'away'" class="space-y-1.5">
					<label class="block text-xs text-ink-gray-6" for="ophice-back-at">{{ __("Back at") }}</label>
					<input
						id="ophice-back-at"
						v-model="backAt"
						type="datetime-local"
						:min="minInput"
						class="form-input w-full rounded border-outline-gray-2 bg-surface-gray-2 text-sm text-ink-gray-9"
						data-testid="status-back-at"
					/>
					<div class="flex flex-wrap gap-1">
						<button
							v-for="quick in quicks"
							:key="quick.label"
							type="button"
							class="rounded-full bg-surface-gray-2 px-2 py-0.5 text-xs text-ink-gray-7 hover:bg-surface-gray-3"
							@click="backAt = toLocalInput(quick.at())"
						>
							{{ quick.label }}
						</button>
					</div>
					<p class="text-xs text-ink-gray-5">
						{{ __("Your time zone: {0}. Everyone sees the time on their own clock.", [zone || "?"]) }}
					</p>
				</div>
				<p v-else class="text-xs text-ink-gray-5">{{ __("Shown above your chip until you move again.") }}</p>
				<button type="submit" class="hidden" />
			</form>
			<p v-if="error" class="text-xs text-ink-red-4">{{ error }}</p>
			<div class="flex justify-end gap-2">
				<Button variant="ghost" @click="$emit('close')">{{ __("Cancel") }}</Button>
				<Button variant="solid" :loading="busy" data-testid="status-save" @click="save">{{ __("Set status") }}</Button>
			</div>
		</div>
	</div>
</template>

<script setup>
import { computed, nextTick, onMounted, ref, watch } from "vue"
import { Button, FeatherIcon, FormControl } from "frappe-ui"
import { __ } from "@spa/utils/i18n.js"
import { fromLocalInput, myZone, toLocalInput, tomorrowAt } from "../utils/ophiceTime.js"

const props = defineProps({
	/** My current status or null */
	status: { type: Object, default: null },
	/** async ({ kind, note, until, tz }) => void; throws with a readable message */
	onSave: { type: Function, required: true },
})
const emit = defineEmits(["close"])

const options = [
	{ kind: "", icon: "check-circle", label: __("Available") },
	{ kind: "brb", icon: "coffee", label: __("Be right back") },
	{ kind: "away", icon: "moon", label: __("Away") },
]
const zone = myZone()
const inMinutes = (minutes) => () => {
	const d = new Date(Date.now() + minutes * 60000)
	// Whole quarter hours read better.
	d.setMinutes(Math.ceil(d.getMinutes() / 15) * 15, 0, 0)
	return d
}
const quicks = [
	{ label: __("30 min"), at: inMinutes(30) },
	{ label: __("1 hour"), at: inMinutes(60) },
	{ label: __("2 hours"), at: inMinutes(120) },
	{ label: __("Tomorrow 9:00"), at: () => tomorrowAt(9) },
]

const kind = ref(props.status?.kind || "")
const note = ref(props.status?.note || "")
const backAt = ref(toLocalInput(props.status?.until ? new Date(props.status.until) : inMinutes(60)()))
const minInput = computed(() => toLocalInput(new Date()))
const busy = ref(false)
const error = ref("")

// The note gets the keyboard, so typing never walks the chip around.
const root = ref(null)
function focusFirst() {
	nextTick(() => (root.value?.querySelector("input") || root.value?.querySelector("button"))?.focus())
}
watch(kind, focusFirst)
onMounted(focusFirst)

async function save() {
	error.value = ""
	let until = ""
	if (kind.value === "away") {
		// The input is on the viewer's clock (their Frappe time zone); toISOString() makes it UTC.
		const date = fromLocalInput(backAt.value)
		if (!date || Number.isNaN(date.getTime())) {
			error.value = __("Please say when you will be back.")
			return
		}
		until = date.toISOString()
	}
	busy.value = true
	try {
		await props.onSave({ kind: kind.value, note: kind.value ? note.value : "", until, tz: zone })
		emit("close")
	} catch (e) {
		error.value = e?.message || __("The status could not be set.")
	} finally {
		busy.value = false
	}
}
</script>
