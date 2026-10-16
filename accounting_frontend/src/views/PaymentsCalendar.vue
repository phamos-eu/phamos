<template>
	<div class="h-full min-h-0 overflow-y-auto bg-surface-gray-1 p-5">
		<div class="mx-auto flex max-w-7xl flex-col gap-4">
			<div class="flex flex-wrap items-center justify-between gap-3">
				<div class="flex flex-wrap items-center gap-2">
					<Button variant="subtle" icon="chevron-left" label="Previous month" @click="shiftMonth(-1)" />
					<Button variant="subtle" icon="chevron-right" label="Next month" @click="shiftMonth(1)" />
					<Button variant="subtle" label="Today" @click="goToday" />
					<h2 class="ml-2 text-lg font-semibold text-ink-gray-9">{{ monthTitle(month) }}</h2>
				</div>
				<div class="flex flex-wrap items-center gap-3">
					<span v-if="data" class="text-sm text-ink-gray-6">
						{{ pluralize(data.totals.count, "payment", "payments") }} · {{ money(data.totals.amount) }}
					</span>
					<div class="inline-flex rounded-md bg-surface-gray-2 p-0.5 text-sm">
						<button
							v-for="option in VIEWS"
							:key="option"
							type="button"
							class="rounded px-3 py-1"
							:class="view === option ? 'bg-surface-white font-medium text-ink-gray-9 shadow-sm' : 'text-ink-gray-6'"
							@click="view = option"
						>
							{{ option }}
						</button>
					</div>
				</div>
			</div>

			<div v-if="error" class="rounded-lg border border-outline-gray-2 bg-surface-red-1 p-4 text-sm text-ink-red-4">
				{{ error }}
			</div>

			<section
				v-if="data?.overdue.count"
				class="rounded-lg border border-outline-red-2 bg-surface-red-1 p-4"
			>
				<div class="mb-2 text-sm font-semibold text-ink-red-4">
					{{ data.overdue.count }} overdue · {{ money(data.overdue.amount) }}
				</div>
				<div class="flex flex-wrap gap-2">
					<button
						v-for="item in data.overdue.items"
						:key="`${item.kind}-${item.name}`"
						type="button"
						class="inline-flex max-w-full items-center gap-2 rounded-md border border-outline-red-2 bg-surface-white px-2 py-1 text-xs hover:bg-surface-gray-1"
						:title="itemTitle(item)"
						@click="openItem(item)"
					>
						<span class="min-w-0 truncate font-medium text-ink-gray-8">{{ item.title }}</span>
						<span class="shrink-0 tabular-nums text-ink-gray-7">{{ money(item.amount) }}</span>
						<span class="shrink-0 text-ink-red-4">{{ item.days_overdue }} d</span>
					</button>
				</div>
			</section>

			<div v-if="loading && !data" class="flex min-h-64 items-center justify-center text-sm text-ink-gray-5">
				Loading payments…
			</div>

			<section
				v-else-if="data && view === 'Month'"
				class="overflow-hidden rounded-lg border border-outline-gray-2 bg-surface-white"
				:class="loading ? 'opacity-60' : ''"
			>
				<div class="grid grid-cols-7 border-b border-outline-gray-2 bg-surface-gray-1 text-xs font-medium text-ink-gray-6">
					<div v-for="name in WEEKDAYS" :key="name" class="px-2 py-1.5">{{ name }}</div>
				</div>
				<div class="grid grid-cols-7">
					<div
						v-for="day in gridDays"
						:key="day.key"
						class="min-h-28 min-w-0 border-b border-r border-outline-gray-1 p-1.5"
						:class="[day.inMonth ? '' : 'bg-surface-gray-1', day.key === todayKey ? 'ring-2 ring-inset ring-outline-gray-4' : '']"
					>
						<div class="mb-1 flex items-baseline justify-between gap-1 text-xs">
							<span :class="day.inMonth ? 'text-ink-gray-7' : 'text-ink-gray-4'">{{ day.date.getDate() }}</span>
							<span v-if="data.totals_by_day[day.key]" class="truncate font-semibold tabular-nums text-ink-gray-9">
								{{ money(data.totals_by_day[day.key].amount, true) }}
							</span>
						</div>
						<button
							v-for="item in (itemsByDay[day.key] || []).slice(0, MAX_PER_DAY)"
							:key="`${item.kind}-${item.name}`"
							type="button"
							class="mb-0.5 flex w-full min-w-0 items-center justify-between gap-1 rounded px-1 py-0.5 text-left text-[11px] hover:bg-surface-gray-2"
							:class="item.days_overdue ? 'bg-surface-red-1 text-ink-red-4' : item.kind === 'payment_request' ? 'bg-surface-amber-1 text-ink-gray-8' : 'bg-surface-blue-1 text-ink-gray-8'"
							:title="itemTitle(item)"
							@click="openItem(item)"
						>
							<span class="truncate">{{ item.title }}</span>
							<span class="shrink-0 tabular-nums">{{ money(item.amount, true) }}</span>
						</button>
						<button
							v-if="(itemsByDay[day.key] || []).length > MAX_PER_DAY"
							type="button"
							class="text-[11px] text-ink-gray-5 hover:underline"
							@click="showWeekOf(day.key)"
						>
							+{{ itemsByDay[day.key].length - MAX_PER_DAY }} more
						</button>
					</div>
				</div>
			</section>

			<section v-else-if="data" class="flex flex-col gap-3" :class="loading ? 'opacity-60' : ''">
				<div
					v-for="week in monthWeeks"
					:id="`week-${week.key}`"
					:key="week.key"
					class="rounded-lg border border-outline-gray-2 bg-surface-white p-4"
				>
					<div class="mb-2 flex flex-wrap items-baseline justify-between gap-2">
						<h3 class="text-sm font-semibold text-ink-gray-9">
							{{ week.label }} · {{ shortDay(week.start) }} – {{ shortDay(week.end) }}
						</h3>
						<span class="text-sm tabular-nums text-ink-gray-7">
							{{ pluralize(week.count, "payment", "payments") }} · {{ money(week.amount) }}
						</span>
					</div>
					<p v-if="!week.count" class="text-sm text-ink-gray-5">Nothing due.</p>
					<ul v-else class="divide-y divide-outline-gray-1">
						<li v-for="item in itemsInWeek(week)" :key="`${item.kind}-${item.name}`">
							<button
								type="button"
								class="grid w-full grid-cols-[4.5rem_minmax(0,1fr)_auto] items-center gap-3 py-1.5 text-left text-sm hover:bg-surface-gray-1"
								@click="openItem(item)"
							>
								<span class="text-ink-gray-6" :class="item.days_overdue ? 'text-ink-red-4' : ''">{{ shortDay(item.date) }}</span>
								<span class="min-w-0">
									<span class="block truncate text-ink-gray-9" :title="item.title">{{ item.title }}</span>
									<span class="block truncate text-xs text-ink-gray-5">
										{{ item.kind === "payment_request" ? "Payment Request" : item.status }} · {{ item.name }}
										<template v-if="item.reference"> · {{ item.reference }}</template>
									</span>
								</span>
								<span class="tabular-nums font-medium text-ink-gray-9">{{ money(item.amount) }}</span>
							</button>
						</li>
					</ul>
				</div>
			</section>

			<section
				v-if="data?.undated.length"
				class="rounded-lg border border-outline-gray-2 bg-surface-white p-4"
			>
				<h3 class="mb-2 text-sm font-semibold text-ink-gray-9">
					No due date · {{ data.undated.length }}
				</h3>
				<div class="flex flex-wrap gap-2">
					<button
						v-for="item in data.undated"
						:key="`${item.kind}-${item.name}`"
						type="button"
						class="inline-flex max-w-full items-center gap-2 rounded-md border border-outline-gray-2 px-2 py-1 text-xs hover:bg-surface-gray-1"
						:title="itemTitle(item)"
						@click="openItem(item)"
					>
						<span class="truncate text-ink-gray-8">{{ item.title }}</span>
						<span class="tabular-nums text-ink-gray-7">{{ money(item.amount) }}</span>
					</button>
				</div>
			</section>

			<p v-if="data && !data.totals.count && !data.overdue.count && !data.undated.length" class="text-sm text-ink-gray-5">
				Nothing approved and unpaid. Approve a receipt to see it here.
			</p>
			<p class="text-xs text-ink-gray-5">
				Approved to Pay and Sent to DATEV receipts that are not paid, plus open Payment Requests without a receipt.
				Keys: ← / → month, t today.
			</p>
		</div>
	</div>
</template>

<script setup>
import { computed, nextTick, onBeforeUnmount, onMounted, ref, watch } from "vue"
import { useRouter } from "vue-router"
import { Button, call } from "frappe-ui"
import { pluralize } from "@spa/utils/dashboardFormat.js"
import { dayKey, formatMoney, monthGridDays, monthTitle, shortDay } from "../statsFormat"

const STATS_API = "phamos.api.accounting_stats"
const VIEWS = ["Month", "Weeks"]
const WEEKDAYS = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]
const MAX_PER_DAY = 3

const router = useRouter()
const today = new Date()
const todayKey = dayKey(today)
const month = ref(new Date(today.getFullYear(), today.getMonth(), 1))
// The 7-column grid is unreadable on a phone; start there with the week list.
const view = ref(window.matchMedia?.("(max-width: 639px)").matches ? "Weeks" : "Month")
const data = ref(null)
const loading = ref(false)
const error = ref("")
let requestId = 0

const gridDays = computed(() =>
	monthGridDays(month.value).map((date) => ({
		date,
		key: dayKey(date),
		inMonth: date.getMonth() === month.value.getMonth(),
	}))
)

const itemsByDay = computed(() => {
	const groups = {}
	for (const item of data.value?.items || []) {
		;(groups[item.date] ||= []).push(item)
	}
	return groups
})

const monthWeeks = computed(() => data.value?.weeks || [])

function itemsInWeek(week) {
	return (data.value?.items || []).filter((item) => item.date >= week.start && item.date <= week.end)
}

function money(value, compact = false) {
	return formatMoney(value, data.value?.currency, { compact })
}

function itemTitle(item) {
	const kind = item.kind === "payment_request" ? "Payment Request" : "Receipt"
	const due = item.date ? `due ${shortDay(item.date)}` : "no due date"
	return `${kind} ${item.name} · ${item.title} · ${money(item.amount)} · ${due}`
}

function openItem(item) {
	if (item.kind === "receipt") router.push(item.route)
	else window.open(item.desk_url, "_blank", "noopener")
}

async function showWeekOf(key) {
	view.value = "Weeks"
	await nextTick()
	const week = monthWeeks.value.find((w) => key >= w.start && key <= w.end)
	if (week) document.getElementById(`week-${week.key}`)?.scrollIntoView({ block: "start", behavior: "smooth" })
}

function shiftMonth(delta) {
	month.value = new Date(month.value.getFullYear(), month.value.getMonth() + delta, 1)
}

function goToday() {
	month.value = new Date(today.getFullYear(), today.getMonth(), 1)
}

async function load() {
	const days = gridDays.value
	const id = ++requestId
	loading.value = true
	try {
		const result = await call(`${STATS_API}.get_payment_calendar`, {
			from_date: days[0].key,
			to_date: days[days.length - 1].key,
		})
		if (id !== requestId) return
		data.value = result
		error.value = ""
	} catch (e) {
		if (id !== requestId) return
		error.value = e?.messages?.[0] || e?.message || "Could not load the payment calendar"
	} finally {
		if (id === requestId) loading.value = false
	}
}

function isTyping(event) {
	const target = event.target
	return target?.isContentEditable || ["INPUT", "TEXTAREA", "SELECT"].includes(target?.tagName)
}

function onKeydown(event) {
	if (event.defaultPrevented || event.metaKey || event.ctrlKey || event.altKey || isTyping(event)) return
	if (event.key === "ArrowLeft") shiftMonth(-1)
	else if (event.key === "ArrowRight") shiftMonth(1)
	else if (event.key === "t") goToday()
	else return
	event.preventDefault()
}

watch(month, load)
onMounted(() => {
	load()
	window.addEventListener("keydown", onKeydown)
})
onBeforeUnmount(() => window.removeEventListener("keydown", onKeydown))
</script>
