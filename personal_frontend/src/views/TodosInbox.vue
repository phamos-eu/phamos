<template>
	<div class="flex h-full min-h-0">
		<section
			class="flex min-w-0 flex-col border-r border-outline-gray-2 bg-surface-white"
			:class="selectedName ? 'w-1/2 flex-none' : 'flex-1'"
		>
			<div class="flex flex-wrap items-center gap-3 border-b border-outline-gray-2 px-5 py-3">
				<FormControl
					v-model="search"
					type="text"
					size="sm"
					placeholder="Search ToDos and references…"
					class="w-full min-w-0 max-w-xs"
				/>
				<InboxStatusFilter
					v-model="includeClosed"
					active-label="Open"
					include-label="Include done"
					aria-label="Which ToDos to show"
				/>
				<span class="text-xs text-ink-gray-5">{{ countLabel }}</span>
				<button
					v-if="staleCount"
					type="button"
					class="rounded-full px-2 py-0.5 text-xs transition"
					:class="staleOnly ? 'bg-surface-gray-7 text-ink-white' : 'bg-surface-gray-2 text-ink-gray-7 hover:bg-surface-gray-3'"
					:aria-pressed="staleOnly"
					title="Overdue for more than two weeks, or postponed three times or more"
					@click="staleOnly = !staleOnly"
				>
					Stale ({{ staleCount }})
				</button>
				<Button v-if="staleOnly && staleCount" size="sm" @click="decideStale">Decide all</Button>
				<Button class="ml-auto" variant="solid" @click="showCreate = true">New ToDo</Button>
			</div>

			<div v-if="error" class="flex flex-1 items-center justify-center px-6 text-sm text-red-600">
				{{ error }}
			</div>
			<div v-else-if="loading && !todos.length" class="flex flex-1 items-center justify-center text-sm text-ink-gray-5">
				Loading…
			</div>
			<div v-else-if="!filtered.length" class="flex flex-1 flex-col items-center justify-center gap-2 px-6 text-center">
				<p class="font-medium text-ink-gray-9">{{ search ? "No matching ToDos" : "Nothing on your list" }}</p>
				<p class="text-sm text-ink-gray-5">
					{{ search ? "Try another search." : "ToDos assigned to you, and the ones you create here, show up in this list." }}
				</p>
				<Button v-if="!search" class="mt-2" @click="showCreate = true">Create a ToDo</Button>
			</div>
			<div v-else class="min-h-0 flex-1 overflow-y-auto px-4">
				<TodoList :todos="filtered" :selected-name="selectedName" :busy="busy" @select="openTodo" @toggle="toggle" />
			</div>
		</section>

		<section v-if="selectedName" class="min-w-0 flex-1 bg-surface-white">
			<TodoDetail v-if="selected" :todo="selected" @close="closeDetail" @updated="applyUpdate" />
			<div v-else-if="detailError" class="flex h-full items-center justify-center px-6 text-sm text-red-600">
				{{ detailError }}
			</div>
			<div v-else class="flex h-full items-center justify-center text-sm text-ink-gray-5">Loading…</div>
		</section>

		<CreateTodoDialog v-model="showCreate" @created="onCreated" />
		<DecideTodoDialog v-model="showDecide" :todos="decideQueue" @decided="({ todo }) => applyUpdate(todo)" />
	</div>
</template>

<script setup>
import { computed, onMounted, ref, watch } from "vue"
import { useRoute, useRouter } from "vue-router"
import { call, toast } from "frappe-ui"
import InboxStatusFilter from "@spa/components/InboxStatusFilter.vue"
import TodoList from "@spa/components/TodoList.vue"
import TodoDetail from "@spa/components/TodoDetail.vue"
import CreateTodoDialog from "@spa/components/CreateTodoDialog.vue"
import DecideTodoDialog from "@spa/components/DecideTodoDialog.vue"
import { useUserRealtime } from "@spa/composables/useUserRealtime.js"
import { matchesTodo, sortTodos } from "@spa/utils/todoSort.js"
import spaConfig from "@/config"

const props = defineProps({
	name: { type: String, default: "" },
})

const API = spaConfig.api
const route = useRoute()
const router = useRouter()

const todos = ref([])
const loading = ref(false)
const error = ref("")
const search = ref("")
const includeClosed = ref(false)
const showCreate = ref(false)
const busy = ref("")
const selected = ref(null)
const detailError = ref("")

const selectedName = computed(() => props.name || "")
const staleOnly = ref(false)
const showDecide = ref(false)
const decideQueue = ref([])
const staleCount = computed(() => todos.value.filter((todo) => todo.stale).length)
const filtered = computed(() =>
	todos.value.filter((todo) => (!staleOnly.value || todo.stale) && matchesTodo(todo, search.value))
)

function decideStale() {
	decideQueue.value = todos.value.filter((todo) => todo.stale)
	showDecide.value = true
}
const countLabel = computed(() => {
	const open = todos.value.filter((t) => t.status === "Open")
	const overdue = open.filter((t) => t.overdue).length
	return overdue ? `${open.length} open · ${overdue} overdue` : `${open.length} open`
})

function message(e, fallback) {
	return e?.messages?.[0] || e?.message || fallback
}

async function loadTodos() {
	loading.value = true
	error.value = ""
	try {
		todos.value = await call(`${API}.get_my_todos`, { include_closed: includeClosed.value ? 1 : 0 })
	} catch (e) {
		error.value = message(e, "Could not load your ToDos")
	} finally {
		loading.value = false
	}
}

async function loadSelected() {
	detailError.value = ""
	if (!selectedName.value) {
		selected.value = null
		return
	}
	const fromList = todos.value.find((t) => t.name === selectedName.value)
	if (fromList) {
		selected.value = fromList
		return
	}
	selected.value = null
	try {
		selected.value = await call(`${API}.get_todo`, { name: selectedName.value })
	} catch (e) {
		detailError.value = message(e, "Could not open this ToDo")
	}
}

function openTodo(name) {
	router.replace({ name: "TodoDetail", params: { name } })
}

function closeDetail() {
	router.replace({ name: "TodosList" })
}

/** Put a changed ToDo back into the list, keeping the agreed order and the done filter. */
function applyUpdate(todo) {
	const others = todos.value.filter((t) => t.name !== todo.name)
	const keep = todo.status === "Open" || (includeClosed.value && todo.status === "Closed")
	todos.value = sortTodos(keep ? [...others, todo] : others)
	if (todo.name === selectedName.value) selected.value = todo
}

async function toggle(todo) {
	busy.value = todo.name
	try {
		const method = todo.status === "Closed" ? "reopen_todo" : "close_todo"
		const updated = await call(`${API}.${method}`, { name: todo.name })
		applyUpdate(updated)
		if (updated.status === "Closed") {
			toast({ title: "Marked as done", icon: "check-circle", iconClasses: "text-ink-green-4" })
		}
	} catch (e) {
		toast({ title: message(e, "Could not change the ToDo"), icon: "x-circle", iconClasses: "text-ink-red-4" })
	} finally {
		busy.value = ""
	}
}

function onCreated(todo) {
	applyUpdate(todo)
	openTodo(todo.name)
}

watch(includeClosed, loadTodos)
watch(staleCount, (count) => {
	if (!count) staleOnly.value = false
})
// Another tab, Desk or an assigner changed one of my ToDos: refresh the list.
useUserRealtime("cockpit_todos_changed", async () => {
	await loadTodos()
	await loadSelected()
})
watch(() => route.params.name, loadSelected)

onMounted(async () => {
	await loadTodos()
	await loadSelected()
})
</script>
