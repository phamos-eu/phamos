<template>
	<section>
		<div class="mb-1.5 text-xs text-ink-gray-5" :id="labelId">{{ __("Depends on") }}</div>

		<ul v-if="dependencies.length" class="mb-2 space-y-1.5" :aria-labelledby="labelId">
			<li
				v-for="dep in dependencies"
				:key="dep.name"
				class="flex items-center gap-2 rounded-md bg-surface-gray-2 px-2 py-1.5 text-sm"
			>
				<span
					class="h-2 w-2 flex-shrink-0 rounded-full bg-surface-gray-5"
					:style="dep.color ? { backgroundColor: dep.color } : null"
				/>
				<span v-if="dep.readable" class="min-w-0 flex-1 truncate" :title="dep.subject">
					{{ dep.subject || dep.name }}
				</span>
				<span v-else class="min-w-0 flex-1 truncate text-ink-gray-5">
					{{ dep.name }} · {{ __("no access") }}
				</span>
				<span v-if="dep.exp_end_date" class="flex-shrink-0 text-xs text-ink-gray-5">
					{{ __("ends {0}", [formatDate(dep.exp_end_date)]) }}
				</span>
				<button
					type="button"
					class="flex h-5 w-5 flex-shrink-0 items-center justify-center rounded text-ink-gray-5 hover:bg-surface-gray-3 hover:text-ink-gray-9 disabled:opacity-50"
					:aria-label="__('Remove dependency on {0}', [dep.subject || dep.name])"
					:title="__('Remove dependency')"
					:disabled="busy"
					@click="remove(dep)"
				>
					<FeatherIcon name="x" class="h-3.5 w-3.5" />
				</button>
			</li>
		</ul>

		<div class="relative">
			<input
				ref="input"
				v-model="query"
				type="text"
				role="combobox"
				aria-autocomplete="list"
				:aria-expanded="open"
				:aria-controls="listId"
				:aria-activedescendant="open && results[active] ? `${listId}-${active}` : undefined"
				:placeholder="__('Add a task that must finish first…')"
				:disabled="busy"
				class="w-full rounded-md border border-outline-gray-2 bg-surface-white px-2.5 py-1.5 text-sm text-ink-gray-9 placeholder:text-ink-gray-4 focus:border-outline-gray-4 focus:outline-none focus:ring-0 dark:bg-surface-gray-2"
				@focus="openList"
				@blur="closeSoon"
				@keydown.down.prevent="moveActive(1)"
				@keydown.up.prevent="moveActive(-1)"
				@keydown.enter.prevent="pickActive"
				@keydown.escape="onEscape"
			/>
			<ul
				v-if="open"
				:id="listId"
				role="listbox"
				class="absolute left-0 right-0 z-20 mt-1 max-h-64 overflow-y-auto rounded-md border border-outline-gray-2 bg-surface-white p-1 shadow-lg dark:bg-surface-gray-2"
			>
				<li v-if="loading && !results.length" class="px-2 py-1.5 text-sm text-ink-gray-5">
					{{ __("Searching…") }}
				</li>
				<li v-else-if="!results.length" class="px-2 py-1.5 text-sm text-ink-gray-5">
					{{ __("No matching task") }}
				</li>
				<li
					v-for="(task, i) in results"
					:id="`${listId}-${i}`"
					:key="task.name"
					role="option"
					:aria-selected="i === active"
					class="flex cursor-pointer items-start gap-2 rounded px-2 py-1.5"
					:class="i === active ? 'bg-surface-gray-3' : 'hover:bg-surface-gray-2'"
					@mousedown.prevent="add(task)"
					@mousemove="active = i"
				>
					<span
						class="mt-1.5 h-2 w-2 flex-shrink-0 rounded-full bg-surface-gray-5"
						:style="task.color ? { backgroundColor: task.color } : null"
					/>
					<span class="min-w-0 flex-1">
						<span class="block truncate text-sm text-ink-gray-9">{{ task.subject || task.name }}</span>
						<span class="block truncate text-xs text-ink-gray-5">
							{{ [task.department, task.exp_end_date ? __("ends {0}", [formatDate(task.exp_end_date)]) : ""].filter(Boolean).join(" · ") }}
						</span>
					</span>
				</li>
			</ul>
		</div>
	</section>
</template>

<script setup>
// "Depends on" in the task side panel (#2000, slice 1 of #1999): lists a Task's predecessors and
// adds or removes them through the cockpit API. Keyboard: ↑/↓ choose, Enter adds, Esc closes.
import { computed, ref, watch } from "vue"
import { call, debounce, FeatherIcon, toast } from "frappe-ui"
import { formatDate } from "@spa/utils/datetime.js"
import { __ } from "@spa/utils/i18n.js"

const props = defineProps({
	task: { type: Object, required: true },
	api: { type: String, required: true },
})

const emit = defineEmits(["updated"])

const uid = Math.random().toString(36).slice(2, 8)
const labelId = `task-deps-label-${uid}`
const listId = `task-deps-list-${uid}`

const input = ref(null)
const query = ref("")
const results = ref([])
const active = ref(0)
const open = ref(false)
const loading = ref(false)
const busy = ref(false)
let searchSeq = 0
let closeTimer = null

const dependencies = computed(() => props.task.dependencies || [])

async function search() {
	const seq = ++searchSeq
	loading.value = true
	try {
		const rows = await call(`${props.api}.search_dependency_candidates`, {
			name: props.task.name,
			txt: query.value,
		})
		if (seq !== searchSeq) return
		results.value = rows || []
		active.value = 0
	} catch (e) {
		if (seq === searchSeq) results.value = []
	} finally {
		if (seq === searchSeq) loading.value = false
	}
}

const searchSoon = debounce(search, 200)

watch(query, () => {
	if (!open.value) open.value = true
	searchSoon()
})

watch(
	() => props.task.name,
	() => {
		query.value = ""
		results.value = []
		open.value = false
	}
)

function openList() {
	clearTimeout(closeTimer)
	open.value = true
	search()
}

function closeSoon() {
	// A click on an option lands after blur; mousedown.prevent keeps focus, this is the fallback.
	closeTimer = setTimeout(() => (open.value = false), 120)
}

function onEscape(e) {
	if (!open.value) return
	// Esc closes the list first; a second Esc may close the panel.
	e.stopPropagation()
	open.value = false
}

function moveActive(step) {
	if (!open.value) return openList()
	const n = results.value.length
	if (!n) return
	active.value = (active.value + step + n) % n
}

function pickActive() {
	const task = results.value[active.value]
	if (open.value && task) add(task)
}

async function run(method, depends_on, successTitle, failTitle) {
	busy.value = true
	try {
		const updated = await call(`${props.api}.${method}`, { name: props.task.name, depends_on })
		emit("updated", updated)
		toast({ title: successTitle, icon: "check-circle", iconClasses: "text-ink-green-4" })
		return true
	} catch (e) {
		toast({
			title: e?.messages?.[0] || e?.message || failTitle,
			icon: "x-circle",
			iconClasses: "text-ink-red-4",
		})
		return false
	} finally {
		busy.value = false
	}
}

async function add(task) {
	const ok = await run("add_task_dependency", task.name, __("Dependency linked"), __("Could not link tasks"))
	if (!ok) return
	query.value = ""
	results.value = results.value.filter((t) => t.name !== task.name)
	input.value?.focus()
}

function remove(dep) {
	return run("remove_task_dependency", dep.name, __("Dependency removed"), __("Could not remove the dependency"))
}
</script>
