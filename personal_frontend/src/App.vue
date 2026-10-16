<template>
	<CockpitShell :title="pageTitle">
		<template #sidebar>
			<div class="relative flex h-full">
				<div
					class="flex h-full transition-opacity"
					:class="locked ? 'pointer-events-none opacity-40' : ''"
					:inert="locked || undefined"
					:aria-hidden="locked || undefined"
				>
					<CockpitSidebar label="Personal Cockpit" storage-key="personal-cockpit-sidebar-collapsed" :items="navItems" />
				</div>
				<div
					v-if="locked"
					class="absolute inset-x-2 top-14 rounded-md bg-surface-gray-7 px-3 py-2 text-xs text-ink-white shadow"
					role="status"
				>
					{{ lockLabel }}
				</div>
			</div>
		</template>
		<template #header-actions>
			<PageSearch />
			<Button size="sm" variant="solid" @click="showCreateTodo = true">
				<template #prefix><FeatherIcon name="plus" class="h-4 w-4" /></template>
				New ToDo
			</Button>
			<CreateTodoDialog v-model="showCreateTodo" @created="onTodoCreated" />
			<TimerControl />
			<CheckinButton :before-checkout="beforeCheckout" />
			<CheckoutGuardDialog v-model="showGuard" @choose="onGuardChoice" />
		</template>
	</CockpitShell>
</template>

<script setup>
import { computed, onBeforeUnmount, onMounted, ref, watch } from "vue"
import { useRoute, useRouter } from "vue-router"
import CockpitShell from "@spa/components/CockpitShell.vue"
import CockpitSidebar from "@spa/components/CockpitSidebar.vue"
import { useUserRealtime } from "@spa/composables/useUserRealtime.js"
import { parseServerTime } from "@spa/utils/focusRules.js"
import { focus, loadFocus } from "./focusStore.js"
import { checkin, loadCheckin } from "./checkinStore.js"
import CheckinButton from "./components/CheckinButton.vue"
import CheckoutGuardDialog from "./components/CheckoutGuardDialog.vue"
import CreateTodoDialog from "@spa/components/CreateTodoDialog.vue"
import PageSearch from "@spa/components/PageSearch.vue"
import { notify } from "@spa/utils/notify.js"
import TimerControl from "@spa/components/timesheet/TimerControl.vue"
import { activeSession, loadTimer, requestTimerStop } from "@spa/timerStore.js"

const route = useRoute()
const router = useRouter()

// Focus mode (#1556): while a session runs, the sidebar is dimmed and unreachable.
const locked = computed(() => Boolean(focus.session))
const lockLabel = computed(() => {
	const end = parseServerTime(focus.session?.planned_end)
	if (!end) return "In focus. Leave from the focus view."
	const time = end.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" })
	return `In focus until ${time}. Leave from the focus view.`
})

useUserRealtime("cockpit_focus_changed", loadFocus, { debounceMs: 200 })

// A session started in another tab locks this one too.
watch(
	() => focus.session?.name,
	(name) => {
		if (name && route.name && route.name !== "TodosFocus") router.push({ name: "TodosFocus" })
	}
)

// Check-ins (#1571) and the timesheet timer (#1572): live from other tabs, the HRMS app, the
// Action Panels and Desk, and again when the tab returns.
useUserRealtime("cockpit_checkin_changed", loadCheckin, { debounceMs: 300 })
useUserRealtime("cockpit_timer_changed", loadTimer, { debounceMs: 300 })

function onVisible() {
	if (document.visibilityState !== "visible") return
	loadCheckin()
	loadTimer()
}

// New ToDo from anywhere (#1592): created, then opened in the list.
const showCreateTodo = ref(false)
function onTodoCreated(todo) {
	notify.success("ToDo created")
	if (todo?.name) router.push({ name: "TodoDetail", params: { name: todo.name } })
}

// Checking out while a timer runs offers to stop it first (decision of 2026-10-16).
const showGuard = ref(false)
let guardResolve = null

async function beforeCheckout() {
	await loadTimer()
	if (!activeSession()) return true
	showGuard.value = true
	return new Promise((resolve) => (guardResolve = resolve))
}

async function onGuardChoice(choice) {
	const resolve = guardResolve
	guardResolve = null
	if (!resolve) return
	if (choice === "anyway") return resolve(true)
	if (choice === "stop") return resolve(await requestTimerStop())
	resolve(false)
}

onMounted(() => {
	loadFocus()
	loadCheckin()
	loadTimer()
	document.addEventListener("visibilitychange", onVisible)
})
onBeforeUnmount(() => document.removeEventListener("visibilitychange", onVisible))

// Check-ins (#1571) appear for users with an active Employee only.
const CHECKIN_ITEM = {
	name: "Checkins",
	label: "Check-ins",
	icon: "clock",
	match: ["Checkins"],
	children: [{ name: "CheckinsList", label: "List", icon: "list", match: ["CheckinsList"] }],
}
const navItems = computed(() => {
	const items = [...BASE_ITEMS]
	if (checkin.state?.available && checkin.state.employee) items.splice(1, 0, CHECKIN_ITEM)
	return items
})

const BASE_ITEMS = [
	{
		name: "Todos",
		label: "ToDos",
		icon: "check-circle",
		match: ["Todos"],
		children: [
			{ name: "TodosPlan", label: "My Day", icon: "sun", match: ["TodosPlan"] },
			{ name: "TodosList", label: "List", icon: "list", match: ["TodosList", "TodoDetail"] },
			{ name: "TodosMatrix", label: "Matrix", icon: "grid", match: ["TodosMatrix"] },
		],
	},
	{
		name: "Issues",
		label: "Issues",
		icon: "inbox",
		match: ["Issues"],
		children: [
			{ name: "IssuesList", label: "List", icon: "list", match: ["IssuesList", "IssueDetail"] },
		],
	},
	{
		name: "Tasks",
		label: "Tasks",
		icon: "check-square",
		match: ["Tasks"],
		children: [
			{ name: "TasksGantt", label: "Gantt", icon: "bar-chart-2", match: ["TasksGantt", "TaskDetail"] },
		],
	},
	{
		name: "ChecklistsHome",
		label: "Checklists",
		icon: "list",
		match: ["ChecklistsHome"],
		children: [
			{
				name: "Checklists",
				label: "Checklists",
				icon: "list",
				match: ["Checklists", "ChecklistDetail"],
			},
		],
	},
]

const pageTitle = computed(() => {
	if (route.name === "TodosFocus") return "Focus"
	if (["Checkins", "CheckinsList"].includes(route.name)) return "My Check-ins"
	if (["Todos", "TodosList", "TodoDetail", "TodosMatrix", "TodosPlan"].includes(route.name)) return "My ToDos"
	if (["Tasks", "TasksGantt", "TaskDetail"].includes(route.name)) return "My Tasks"
	if (["ChecklistsHome", "Checklists", "ChecklistDetail"].includes(route.name)) return "My Checklists"
	return "My Issues"
})
</script>
