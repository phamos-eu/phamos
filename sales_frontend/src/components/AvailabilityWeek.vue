<template>
	<div class="flex h-full min-h-0 flex-col">
		<div class="flex flex-wrap items-center gap-2 border-b border-outline-gray-2 px-3 py-2">
			<span class="text-[11px] font-semibold uppercase tracking-wide text-ink-gray-6">Availability</span>
			<div class="ml-auto flex items-center gap-1.5">
				<button
					type="button"
					class="rounded p-1 text-ink-gray-6 hover:bg-surface-gray-2 hover:text-ink-gray-9"
					title="Previous week"
					@click="shiftWeek(-7)"
				>
					<FeatherIcon name="chevron-left" class="h-4 w-4" />
				</button>
				<div class="w-36">
					<DatePicker :model-value="weekStart" placeholder="Week of" @update:model-value="setWeek" />
				</div>
				<button
					type="button"
					class="rounded p-1 text-ink-gray-6 hover:bg-surface-gray-2 hover:text-ink-gray-9"
					title="Next week"
					@click="shiftWeek(7)"
				>
					<FeatherIcon name="chevron-right" class="h-4 w-4" />
				</button>
			</div>
		</div>

		<div class="flex flex-wrap items-center gap-1.5 border-b border-outline-gray-2 px-3 py-2">
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
			<select
				v-model="duration"
				class="ml-auto h-6 rounded border border-outline-gray-2 bg-surface-white px-1 text-xs text-ink-gray-8"
				aria-label="Slot length"
			>
				<option value="30">30 min</option>
				<option value="60">1 h</option>
				<option value="90">1.5 h</option>
				<option value="120">2 h</option>
			</select>
		</div>

		<!-- A week at a time, scrolling sideways — a single day was never enough
		     to find a time that suits both sides. -->
		<div class="min-h-0 flex-1 overflow-x-auto overflow-y-auto">
			<div v-if="loading" class="flex items-center justify-center py-12 text-sm text-ink-gray-5">
				Loading…
			</div>
			<div v-else class="flex min-w-max gap-2 p-2">
				<div v-for="day in days" :key="day.date" class="w-40 flex-none">
					<div
						class="mb-1.5 rounded bg-surface-gray-2 px-2 py-1 text-center text-xs font-medium"
						:class="isToday(day.date) ? 'text-ink-gray-9' : 'text-ink-gray-7'"
					>
						{{ day.weekday }} {{ formatDate(day.date) }}
					</div>

					<div v-for="block in day.busy" :key="block.starts_on" class="mb-1 rounded bg-surface-gray-3 px-1.5 py-1">
						<div class="truncate text-[11px] font-medium text-ink-gray-7" :title="block.subject">
							{{ block.subject }}
						</div>
						<div class="text-[11px] tabular-nums text-ink-gray-5">
							{{ time(block.starts_on) }}–{{ time(block.ends_on) }}
						</div>
					</div>

					<!-- The point of the column: a free time you can put in the mail. -->
					<button
						v-for="slot in day.free"
						:key="slot.starts_on"
						type="button"
						class="mb-1 w-full rounded border border-dashed px-1.5 py-1 text-left text-[11px] tabular-nums transition"
						:class="
							isPicked(slot)
								? 'border-transparent bg-surface-green-3 font-medium text-ink-green-1'
								: 'border-outline-gray-3 text-ink-gray-7 hover:border-outline-gray-4 hover:bg-surface-gray-2'
						"
						@click="emit('toggle', slot)"
					>
						{{ time(slot.starts_on) }}–{{ time(slot.ends_on) }}
					</button>

					<p v-if="!day.busy.length && !day.free.length" class="px-1 text-[11px] text-ink-gray-5">
						Nothing free
					</p>
				</div>
			</div>
		</div>

		<p class="border-t border-outline-gray-2 px-3 py-1.5 text-[11px] text-ink-gray-5">
			From this system's calendar entries{{ mailcowNote }}. Pick slots to offer, then add them to the
			message.
		</p>
	</div>
</template>

<script setup>
import { computed, onMounted, ref, watch } from "vue"
import { call, DatePicker } from "frappe-ui"
import { formatDate } from "@spa/utils/datetime"

const props = defineProps({
	/** Selectable calendars: [{ name, full_name }] */
	users: { type: Array, default: () => [] },
	/** Slots already chosen, so they read as picked */
	picked: { type: Array, default: () => [] },
})

const emit = defineEmits(["toggle"])

const weekStart = ref(mondayOf(new Date()))
const duration = ref("60")
const days = ref([])
const loading = ref(false)
const shownUsers = ref(new Set())
const mailcowNote = ref("")

function pad(n) {
	return String(n).padStart(2, "0")
}

/** Weeks start on Monday here, so the view lines up with a working week. */
function mondayOf(date) {
	const d = new Date(date)
	const offset = (d.getDay() + 6) % 7
	d.setDate(d.getDate() - offset)
	return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}`
}

function time(value) {
	return String(value || "").slice(11, 16)
}

function isToday(date) {
	const now = new Date()
	return date === `${now.getFullYear()}-${pad(now.getMonth() + 1)}-${pad(now.getDate())}`
}

const pickedKeys = computed(() => new Set(props.picked.map((s) => s.starts_on)))

function isPicked(slot) {
	return pickedKeys.value.has(slot.starts_on)
}

function setWeek(value) {
	if (!value) return
	weekStart.value = mondayOf(value)
}

function shiftWeek(offsetDays) {
	const d = new Date(weekStart.value)
	d.setDate(d.getDate() + offsetDays)
	weekStart.value = mondayOf(d)
}

function toggleUser(name) {
	const next = new Set(shownUsers.value)
	if (next.has(name)) next.delete(name)
	else next.add(name)
	shownUsers.value = next
}

async function load() {
	loading.value = true
	try {
		const data = await call("phamos.api.sales_leads.get_week_availability", {
			start: weekStart.value,
			days: 7,
			users: JSON.stringify([...shownUsers.value]),
			duration_minutes: duration.value,
		})
		days.value = data.days || []
	} catch (e) {
		days.value = []
	} finally {
		loading.value = false
	}
}

watch([weekStart, duration, shownUsers], load)
onMounted(load)
</script>
