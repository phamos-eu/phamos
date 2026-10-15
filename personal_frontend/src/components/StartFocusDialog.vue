<template>
	<Dialog
		:model-value="modelValue"
		:options="{ title: 'Start a focus session', size: 'xl' }"
		@update:model-value="emit('update:modelValue', $event)"
	>
		<template #body-content>
			<div class="space-y-4">
				<p class="text-sm text-ink-gray-6">
					Pick up to {{ maxTodos }} ToDos. Until you finish or leave, the cockpit shows only these.
				</p>

				<div>
					<div class="mb-1.5 flex items-center justify-between text-xs text-ink-gray-5">
						<span>ToDos, in the order you want to do them</span>
						<span>{{ selected.length }} of {{ maxTodos }}</span>
					</div>
					<div v-if="loading" class="py-6 text-center text-sm text-ink-gray-5">Loading your ToDos…</div>
					<p v-else-if="!candidates.length" class="py-6 text-center text-sm text-ink-gray-5">
						No open ToDos. Create one first.
					</p>
					<ul v-else class="max-h-72 space-y-1 overflow-y-auto pr-1">
						<li v-for="todo in candidates" :key="todo.name">
							<label
								class="flex cursor-pointer items-start gap-2 rounded-md px-2 py-1.5 text-sm hover:bg-surface-gray-2"
								:class="isDisabled(todo) ? 'cursor-not-allowed opacity-50' : ''"
							>
								<input
									type="checkbox"
									class="mt-0.5 h-4 w-4 flex-none rounded border-outline-gray-3"
									:checked="selected.includes(todo.name)"
									:disabled="isDisabled(todo)"
									@change="toggle(todo.name)"
								/>
								<span v-if="selected.includes(todo.name)" class="w-4 flex-none text-xs text-ink-gray-5">
									{{ selected.indexOf(todo.name) + 1 }}
								</span>
								<span class="min-w-0 flex-1">
									<span class="block truncate text-ink-gray-9">{{ todo.summary || todo.name }}</span>
									<span class="flex gap-2 text-xs text-ink-gray-5">
										<span v-if="todo.important" class="text-ink-amber-3">★ important</span>
										<span v-if="todo.date" :class="todo.overdue ? 'text-ink-red-3' : ''">due {{ formatDate(todo.date) }}</span>
										<span v-if="todo.estimate_minutes">~{{ todo.estimate_minutes }} min</span>
									</span>
								</span>
							</label>
						</li>
					</ul>
				</div>

				<div>
					<label class="mb-1.5 block text-xs text-ink-gray-5">How long</label>
					<TabButtons v-model="length" :buttons="lengthButtons" />
					<p class="mt-1 text-xs text-ink-gray-5">{{ lengthHint }}</p>
				</div>

				<ErrorMessage :message="error" />
				<div class="flex justify-end gap-2">
					<Button variant="ghost" @click="emit('update:modelValue', false)">Cancel</Button>
					<Button variant="solid" :disabled="!selected.length" :loading="starting" @click="start">
						Start focus
					</Button>
				</div>
			</div>
		</template>
	</Dialog>
</template>

<script setup>
import { computed, ref, watch } from "vue"
import { useRouter } from "vue-router"
import { call, TabButtons } from "frappe-ui"
import { formatDate } from "@spa/utils/datetime.js"
import spaConfig from "@/config"
import { setFocus } from "@/focusStore.js"

const props = defineProps({
	modelValue: { type: Boolean, default: false },
	// ToDo names to preselect (e.g. the "Do now" quadrant), in order.
	preselect: { type: Array, default: () => [] },
})
const emit = defineEmits(["update:modelValue"])

const API = spaConfig.api
const router = useRouter()
const loading = ref(false)
const starting = ref(false)
const error = ref("")
const candidates = ref([])
const selected = ref([])
const options = ref({ presets: [25, 50], max_todos: 5 })
const length = ref("25")

const maxTodos = computed(() => options.value.max_todos || 5)
const lengthButtons = computed(() => [
	...(options.value.presets || [25, 50]).map((m) => ({ label: `${m} min`, value: String(m) })),
	{ label: "Stopwatch", value: "0" },
])
const lengthHint = computed(() =>
	length.value === "0"
		? "No end time. The session ends when you are done or leave."
		: "A timer runs; when it is up you finish your current step and wrap up."
)

function isDisabled(todo) {
	return !selected.value.includes(todo.name) && selected.value.length >= maxTodos.value
}

function toggle(name) {
	selected.value = selected.value.includes(name)
		? selected.value.filter((n) => n !== name)
		: [...selected.value, name]
}

// Important and due-soon ToDos first, so the obvious picks are at the top.
function rank(todo) {
	return [todo.important ? 0 : 1, todo.overdue ? 0 : todo.date ? 1 : 2, todo.date || "9999"]
}

async function load() {
	loading.value = true
	error.value = ""
	try {
		const [todos, opts] = await Promise.all([call(`${API}.get_my_todos`), call(`${API}.get_focus_options`)])
		options.value = opts
		candidates.value = [...todos].sort((a, b) => {
			const ra = rank(a)
			const rb = rank(b)
			for (let i = 0; i < ra.length; i++) if (ra[i] !== rb[i]) return ra[i] < rb[i] ? -1 : 1
			return 0
		})
		const open = new Set(todos.map((t) => t.name))
		selected.value = props.preselect.filter((name) => open.has(name)).slice(0, maxTodos.value)
	} catch (e) {
		error.value = e?.messages?.[0] || e?.message || "Could not load your ToDos"
	} finally {
		loading.value = false
	}
}

async function start() {
	starting.value = true
	error.value = ""
	try {
		const session = await call(`${API}.start_focus`, { todos: selected.value, minutes: Number(length.value) })
		setFocus(session)
		emit("update:modelValue", false)
		router.push({ name: "TodosFocus" })
	} catch (e) {
		error.value = e?.messages?.[0] || e?.message || "Could not start the focus session"
	} finally {
		starting.value = false
	}
}

watch(
	() => props.modelValue,
	(open) => {
		if (open) load()
	}
)
</script>
