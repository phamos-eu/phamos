<template>
	<div class="h-full min-h-0 overflow-y-auto bg-surface-gray-1 p-5">
		<div class="mx-auto flex max-w-7xl flex-col gap-4">
			<div class="flex flex-wrap items-center justify-between gap-3">
				<p class="text-sm text-ink-gray-6">
					Pick the few that matter. Drag a ToDo, or focus it and press 1–4.
					<span v-if="data">Urgent means due by {{ formatDate(data.urgent_until) }}.</span>
				</p>
				<div class="flex items-center gap-2">
					<TabButtons v-model="scope" :buttons="SCOPE_BUTTONS" />
					<Button v-if="bucket('do').total" variant="solid" @click="showStartFocus = true">
						<template #prefix><FeatherIcon name="target" class="h-4 w-4" /></template>
						Focus on “Do now”
					</Button>
				</div>
			</div>

			<div v-if="error" class="rounded-lg border border-outline-gray-2 bg-surface-red-1 p-4 text-sm text-ink-red-4">
				{{ error }}
			</div>
			<div v-else-if="loading && !data" class="flex min-h-64 items-center justify-center text-sm text-ink-gray-5">
				Loading your matrix…
			</div>
			<template v-else-if="data">
				<div class="grid grid-cols-[auto_minmax(0,1fr)_minmax(0,1fr)] gap-3">
					<div />
					<div class="text-center text-xs font-medium uppercase tracking-wide text-ink-gray-5">Urgent</div>
					<div class="text-center text-xs font-medium uppercase tracking-wide text-ink-gray-5">Not urgent</div>
					<template v-for="row in ROWS" :key="row.label">
						<div
							class="flex items-center text-xs font-medium uppercase tracking-wide text-ink-gray-5 [writing-mode:vertical-rl] rotate-180"
						>
							{{ row.label }}
						</div>
						<section
							v-for="q in row.quadrants"
							:key="q.key"
							class="flex min-h-56 min-w-0 flex-col rounded-lg border bg-surface-white p-4 transition"
							:class="dropTarget === q.key ? 'border-outline-gray-5 ring-2 ring-outline-gray-3' : 'border-outline-gray-2'"
							:aria-label="`${q.label}: ${q.hint}`"
							@dragover.prevent="dropTarget = q.key"
							@dragleave="dropTarget === q.key && (dropTarget = '')"
							@drop.prevent="onDrop(q.key)"
						>
							<header class="mb-3 flex items-baseline justify-between gap-2">
								<div>
									<h2 class="text-base font-semibold" :class="TITLE_CLASS[q.key]">
										<span class="mr-1 text-xs text-ink-gray-4">{{ q.shortcut }}</span>{{ q.label }}
									</h2>
									<p class="text-xs text-ink-gray-5">{{ q.hint }}</p>
								</div>
								<span class="text-sm text-ink-gray-6">{{ bucket(q.key).total }}</span>
							</header>

							<ul v-if="bucket(q.key).items.length" class="space-y-1.5">
								<li
									v-for="todo in bucket(q.key).items"
									:key="todo.name"
									:ref="(el) => setCardRef(todo.name, el)"
									draggable="true"
									tabindex="0"
									class="group flex items-start gap-2 rounded-md border border-outline-gray-1 bg-surface-gray-1 px-2.5 py-2 text-sm outline-none focus:border-outline-gray-4 focus:bg-surface-gray-2"
									:class="busy[todo.name] ? 'opacity-50' : 'cursor-grab'"
									:aria-label="`${todo.summary}. Press 1 to 4 to move, Enter to open.`"
									@dragstart="onDragStart($event, todo, q.key)"
									@dragend="dragging = null; dropTarget = ''"
									@keydown="onCardKey($event, todo)"
								>
									<input
										type="checkbox"
										class="mt-0.5 h-4 w-4 flex-none rounded border-outline-gray-3"
										:aria-label="`Mark ${todo.summary} as done`"
										:disabled="busy[todo.name]"
										@click.stop="close(todo)"
									/>
									<div class="min-w-0 flex-1">
										<button
											type="button"
											class="block w-full truncate text-left text-ink-gray-9 hover:underline"
											tabindex="-1"
											@click="openTodo(todo)"
										>
											{{ todo.summary || todo.name }}
										</button>
										<div class="mt-0.5 flex flex-wrap gap-x-2 text-xs text-ink-gray-5">
											<span v-if="todo.date" :class="todo.overdue ? 'text-ink-red-3' : ''">
												{{ todo.overdue ? "overdue since" : "due" }} {{ formatDate(todo.date) }}
											</span>
											<span v-else>no due date</span>
											<span v-if="todo.estimate_minutes">~{{ estimateLabel(todo.estimate_minutes) }}</span>
											<span
												v-if="todo.reschedule_count"
												:class="todo.reschedule_count >= 3 ? 'text-ink-red-3' : ''"
												:title="`Postponed ${todo.reschedule_count} times`"
											>
												↻ {{ todo.reschedule_count }}
											</span>
										</div>
									</div>
									<Button
										size="sm"
										variant="ghost"
										class="hidden group-hover:inline-flex group-focus:inline-flex"
										:aria-label="`Decide on ${todo.summary}`"
										@click.stop="decide(todo)"
									>
										Decide
									</Button>
								</li>
							</ul>
							<p v-else class="text-sm text-ink-gray-5">{{ EMPTY[q.key] }}</p>

							<button
								v-if="bucket(q.key).total > bucket(q.key).items.length"
								type="button"
								class="mt-2 self-start text-xs text-ink-gray-6 hover:underline"
								@click="router.push({ name: 'TodosList' })"
							>
								{{ bucket(q.key).total - bucket(q.key).items.length }} more in the list
							</button>
						</section>
					</template>
				</div>
				<p v-if="data.out_of_scope && scope === 'week'" class="text-xs text-ink-gray-5">
					{{ pluralize(data.out_of_scope, "ToDo is", "ToDos are") }} due after this week and not marked important.
					<button type="button" class="hover:underline" @click="scope = 'all'">Show all open</button>
				</p>
			</template>
		</div>

		<Dialog v-model="showMove" :options="{ title: moveTitle, size: 'md' }">
			<template #body-content>
				<div v-if="pending" class="space-y-4">
					<div class="rounded-md bg-surface-gray-2 px-3 py-2 text-sm text-ink-gray-9">
						{{ pending.todo.summary || pending.todo.name }}
					</div>
					<FormControl
						v-if="pending.needs.laterDate"
						v-model="moveDate"
						type="date"
						size="sm"
						label="New due date"
						:min="data.next_after_urgent"
						:description="`Not urgent means due after ${formatDate(data.urgent_until)}. The deadline moves, it does not disappear.`"
					/>
					<FormControl
						v-if="pending.needs.dueSoon"
						v-model="moveDate"
						type="date"
						size="sm"
						label="Due on"
						:min="data.today"
						:max="data.urgent_until"
					/>
					<FormControl
						v-if="pending.needs.payoff"
						v-model="payoffNote"
						type="textarea"
						size="sm"
						label="What happens if this isn't done this week?"
						placeholder="Optional. Kept as a comment on the ToDo."
					/>
					<ErrorMessage :message="moveError" />
					<div class="flex justify-end gap-2">
						<Button v-if="pending.target === 'eliminate'" class="mr-auto" variant="subtle" @click="dropInstead">
							Drop it instead
						</Button>
						<Button variant="ghost" @click="showMove = false">Cancel</Button>
						<Button variant="solid" :loading="moving" :disabled="pending.needs.laterDate && !moveDate" @click="applyMove">
							Move to {{ quadrant(pending.target).label }}
						</Button>
					</div>
				</div>
			</template>
		</Dialog>

		<DecideTodoDialog v-model="showDecide" :todos="decideQueue" @decided="load" />
		<StartFocusDialog
			v-model="showStartFocus"
			:preselect="bucket('do').items.map((todo) => todo.name)"
		/>
	</div>
</template>

<script setup>
import { computed, onMounted, ref, watch } from "vue"
import { useRouter } from "vue-router"
import { call, TabButtons, toast } from "frappe-ui"
import DecideTodoDialog from "@spa/components/DecideTodoDialog.vue"
import StartFocusDialog from "@/components/StartFocusDialog.vue"
import { useUserRealtime } from "@spa/composables/useUserRealtime.js"
import { pluralize } from "@spa/utils/dashboardFormat.js"
import { formatDate } from "@spa/utils/datetime.js"
import { moveNeeds, quadrant, quadrantForShortcut } from "@spa/utils/eisenhower.js"
import spaConfig from "@/config"

const API = spaConfig.api
const SCOPE_KEY = "personal-todos-matrix-scope"
const SCOPE_BUTTONS = [
	{ label: "This week", value: "week" },
	{ label: "All open", value: "all" },
]
const ROWS = [
	{ label: "Important", quadrants: [quadrant("do"), quadrant("schedule")] },
	{ label: "Not important", quadrants: [quadrant("delegate"), quadrant("eliminate")] },
]
const TITLE_CLASS = {
	do: "text-ink-red-4",
	schedule: "text-ink-blue-4",
	delegate: "text-ink-amber-4",
	eliminate: "text-ink-gray-7",
}
const EMPTY = {
	do: "Nothing on fire. Good.",
	schedule: "Drag what matters most here and give it a day.",
	delegate: "Nothing urgent that someone else could do.",
	eliminate: "Nothing to let go of.",
}

const router = useRouter()
const data = ref(null)
const loading = ref(false)
const error = ref("")
const scope = ref(readScope())
const busy = ref({})
const dragging = ref(null)
const dropTarget = ref("")
const cardRefs = new Map()

const showMove = ref(false)
const pending = ref(null)
const moveDate = ref("")
const payoffNote = ref("")
const moveError = ref("")
const moving = ref(false)

const showDecide = ref(false)
const showStartFocus = ref(false)
const decideQueue = ref([])

const moveTitle = computed(() => (pending.value ? `Move to ${quadrant(pending.value.target).label}` : "Move"))

function readScope() {
	try {
		return localStorage.getItem(SCOPE_KEY) === "all" ? "all" : "week"
	} catch {
		return "week"
	}
}

function bucket(key) {
	return data.value?.quadrants?.[key] || { items: [], total: 0 }
}

function setCardRef(name, el) {
	if (el) cardRefs.set(name, el)
	else cardRefs.delete(name)
}

function estimateLabel(minutes) {
	return minutes >= 60 ? `${Math.round((minutes / 60) * 10) / 10} h` : `${minutes} min`
}

async function load() {
	loading.value = true
	error.value = ""
	try {
		data.value = await call(`${API}.get_todo_matrix`, { scope: scope.value })
	} catch (e) {
		error.value = e?.messages?.[0] || e?.message || "Could not load your matrix"
	} finally {
		loading.value = false
	}
}

function openTodo(todo) {
	router.push({ name: "TodoDetail", params: { name: todo.name } })
}

function decide(todo) {
	decideQueue.value = [todo]
	showDecide.value = true
}

async function close(todo) {
	busy.value = { ...busy.value, [todo.name]: true }
	try {
		await call(`${API}.close_todo`, { name: todo.name })
		toast.success("Done. One less.")
		await load()
	} catch (e) {
		toast.error(e?.messages?.[0] || e?.message || "Could not close the ToDo")
	} finally {
		const { [todo.name]: _, ...rest } = busy.value
		busy.value = rest
	}
}

function requestMove(todo, target) {
	const needs = moveNeeds(todo, target, data.value.urgent_until)
	if (!needs || needs.same) return
	pending.value = { todo, target, needs }
	moveDate.value = needs.laterDate ? data.value.next_after_urgent : needs.dueSoon ? data.value.today : ""
	payoffNote.value = ""
	moveError.value = ""
	if (needs.laterDate || needs.payoff || target === "eliminate") {
		showMove.value = true
		return
	}
	applyMove()
}

async function applyMove() {
	const { todo, target, needs } = pending.value
	moving.value = true
	moveError.value = ""
	busy.value = { ...busy.value, [todo.name]: true }
	try {
		await call(`${API}.set_todo_quadrant`, {
			name: todo.name,
			quadrant: target,
			date: needs.laterDate || needs.dueSoon ? moveDate.value || null : null,
			payoff_note: payoffNote.value || null,
		})
		showMove.value = false
		await load()
		cardRefs.get(todo.name)?.focus()
	} catch (e) {
		const message = e?.messages?.[0] || e?.message || "Could not move the ToDo"
		if (showMove.value) moveError.value = message
		else toast.error(message)
	} finally {
		moving.value = false
		const { [todo.name]: _, ...rest } = busy.value
		busy.value = rest
	}
}

// "Drop or let go" usually means letting it go: offer the Decide dialog's drop path directly.
function dropInstead() {
	const { todo } = pending.value
	showMove.value = false
	decide(todo)
}

function onDragStart(event, todo, from) {
	dragging.value = { todo, from }
	event.dataTransfer.effectAllowed = "move"
	event.dataTransfer.setData("text/plain", todo.name)
}

function onDrop(target) {
	dropTarget.value = ""
	const drag = dragging.value
	dragging.value = null
	if (drag && drag.from !== target) requestMove(drag.todo, target)
}

function onCardKey(event, todo) {
	if (event.target !== event.currentTarget || event.metaKey || event.ctrlKey || event.altKey) return
	if (event.key === "Enter") {
		event.preventDefault()
		openTodo(todo)
		return
	}
	const target = quadrantForShortcut(event.key)
	if (target) {
		event.preventDefault()
		requestMove(todo, target)
	}
}

watch(scope, (value) => {
	try {
		localStorage.setItem(SCOPE_KEY, value)
	} catch {
		// private mode: the scope is not remembered
	}
	load()
})

useUserRealtime("cockpit_todos_changed", () => {
	if (!showMove.value && !moving.value) load()
})

onMounted(load)
</script>
