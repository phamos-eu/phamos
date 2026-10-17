<template>
	<div ref="root">
		<Dropdown :options="groups" placement="right">
			<Button size="sm" variant="solid" :aria-label="__('Create something new')">
				<template #prefix><FeatherIcon name="plus" class="h-4 w-4" /></template>
				{{ __("Create") }}
				<template #suffix><FeatherIcon name="chevron-down" class="h-3.5 w-3.5" /></template>
			</Button>
		</Dropdown>

		<CreateTodoDialog v-model="open.todo" @created="(doc) => opened(__('ToDo created'), 'TodoDetail', doc)" />
		<CreateIssueDialog v-model="open.issue" :options="formOptions" @created="(doc) => opened(__('Issue created'), 'IssueDetail', doc)" />
		<CreateTaskDialog v-model="open.task" :options="formOptions" @created="(doc) => opened(__('Task created'), 'TaskDetail', doc)" />
		<CreateChecklistDialog
			v-model="open.checklist"
			:create-method="`${API}.create_checklist`"
			:reference-query="`${API}.checklist_reference_query`"
			:doctypes="['Issue', 'Task', 'ToDo']"
			@created="(doc) => opened(__('Checklist created'), 'ChecklistDetail', doc)"
		/>
		<StartFocusDialog v-model="open.focus" />
		<CreateChallengeDialog v-model="open.challenge" @created="onChallenge" />
	</div>
</template>

<script setup>
// One "Create" menu in the top bar (#1592) for everything the Personal Cockpit shows: ToDos,
// Issues, Tasks, Checklists, a timesheet timer, a check-in or check-out, a focus session and a
// target. Each entry opens the dialog its own page uses.
import { computed, reactive, ref, watch } from "vue"
import { useRouter } from "vue-router"
import { call, Dropdown } from "frappe-ui"
import CreateChecklistDialog from "@spa/components/CreateChecklistDialog.vue"
import CreateIssueDialog from "@spa/components/CreateIssueDialog.vue"
import CreateTaskDialog from "@spa/components/CreateTaskDialog.vue"
import CreateTodoDialog from "@spa/components/CreateTodoDialog.vue"
import { requestTimerStart, timer } from "@spa/timerStore.js"
import { shortcuts } from "@/shortcutsStore.js"
import { notify } from "@spa/utils/notify.js"
import { __ } from "@spa/utils/i18n.js"
import spaConfig from "@/config"
import { checkin, checkInOrOut, checkinUsable } from "@/checkinStore.js"
import CreateChallengeDialog from "./CreateChallengeDialog.vue"
import StartFocusDialog from "./StartFocusDialog.vue"

const props = defineProps({
	// Guard before checking out (the running timer asks to be stopped first).
	beforeCheckout: { type: Function, default: null },
})

const API = spaConfig.api
const router = useRouter()
const root = ref(null)
const open = reactive({ todo: false, issue: false, task: false, checklist: false, focus: false, challenge: false })
const formOptions = ref({ priorities: [], issue_types: [], shortlist_users: [], departments: [], projects: [] })
let optionsLoaded = false

const groups = computed(() => {
	const work = [
		{ label: __("ToDo"), icon: "check-circle", onClick: () => (open.todo = true) },
		{ label: __("Issue"), icon: "inbox", onClick: () => (open.issue = true) },
		{ label: __("Task"), icon: "check-square", onClick: () => (open.task = true) },
		{ label: __("Checklist"), icon: "list", onClick: () => (open.checklist = true) },
	]
	const time = []
	if (timer.state?.available && !timer.state.session) {
		time.push({ label: __("Timesheet timer"), icon: "play", onClick: requestTimerStart })
	}
	if (checkinUsable(checkin.state)) {
		const out = checkin.state.next_action === "OUT"
		time.push({
			label: out ? __("Check-out") : __("Check-in"),
			icon: out ? "log-out" : "log-in",
			onClick: () => checkInOrOut(props.beforeCheckout),
		})
	}
	const focus = [
		{ label: __("Focus session"), icon: "target", onClick: () => (open.focus = true) },
		{ label: __("Target"), icon: "award", onClick: () => (open.challenge = true) },
	]
	return [
		{ group: __("Work"), items: work },
		...(time.length ? [{ group: __("Time"), items: time }] : []),
		{ group: __("Focus"), items: focus },
		{ group: __("Help"), items: [{ label: `${__("Keyboard shortcuts")}  ?`, icon: "command", onClick: () => (shortcuts.open = true) }] },
	]
})

async function loadFormOptions() {
	if (optionsLoaded) return
	try {
		formOptions.value = await call(`${API}.get_form_options`)
		optionsLoaded = true
	} catch {
		/* the dialogs show their own error when saving */
	}
}

function opened(message, routeName, doc) {
	notify.success(message)
	if (doc?.name) router.push({ name: routeName, params: { name: doc.name } })
}

function onChallenge() {
	notify.success(__("Target set"))
	router.push({ name: "Todos" })
}

// Ctrl/Cmd+B (#1603): open the menu with the first entry focused, as ArrowDown on its button does
// (Headless UI's MenuButton opens on ArrowDown and moves focus into the menu).
function openMenu() {
	const button = root.value?.querySelector('[id^="headlessui-menu-button"]')
	if (!button) return
	button.focus()
	button.dispatchEvent(new KeyboardEvent("keydown", { key: "ArrowDown", bubbles: true }))
}
defineExpose({ open: openMenu })

watch(
	() => open.issue || open.task,
	(value) => value && loadFormOptions()
)
</script>
