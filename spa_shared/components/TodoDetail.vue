<template>
	<div class="flex h-full min-h-0 flex-col">
		<div class="flex items-center justify-between gap-3 border-b border-outline-gray-2 px-5 py-3">
			<div class="flex min-w-0 items-center gap-2">
				<Badge
					:label="todo.status === 'Closed' ? 'Done' : todo.overdue ? 'Overdue' : 'Open'"
					:theme="todo.status === 'Closed' ? 'green' : todo.overdue ? 'red' : 'gray'"
					size="sm"
					variant="subtle"
				/>
				<span class="truncate text-xs text-ink-gray-5">{{ todo.name }}</span>
			</div>
			<div class="flex flex-none items-center gap-2">
				<Button
					size="sm"
					:variant="todo.status === 'Closed' ? 'subtle' : 'solid'"
					:loading="toggling"
					@click="toggleStatus"
				>
					{{ todo.status === "Closed" ? "Reopen" : "Mark as done" }}
				</Button>
				<a
					:href="todo.desk_url"
					target="_blank"
					rel="noopener"
					class="text-xs text-ink-gray-5 hover:text-ink-gray-8"
					title="Open in Desk"
				>
					Desk
				</a>
				<button
					type="button"
					class="rounded p-1 text-ink-gray-5 hover:bg-surface-gray-2 hover:text-ink-gray-8"
					title="Close"
					@click="emit('close')"
				>
					<FeatherIcon name="x" class="h-4 w-4" />
				</button>
			</div>
		</div>

		<div class="min-h-0 flex-1 space-y-4 overflow-y-auto px-5 py-4">
			<div v-if="todo.reference_type" class="rounded-md bg-surface-gray-2 px-3 py-2 text-sm">
				<div class="text-xs text-ink-gray-5">Reference</div>
				<a
					:href="todo.reference_url"
					target="_blank"
					rel="noopener"
					class="mt-0.5 inline-flex max-w-full items-center gap-1 text-ink-gray-9 underline-offset-2 hover:underline"
				>
					<span class="truncate">
						{{ todo.reference_type }} · {{ todo.reference_title || todo.reference_name }}
					</span>
					<FeatherIcon name="external-link" class="h-3.5 w-3.5 flex-none" />
				</a>
			</div>

			<div class="w-full">
				<label class="mb-1.5 block text-xs text-ink-gray-5">Description</label>
				<TextEditor
					:key="todo.name"
					:content="draft.description"
					:editable="!readonly"
					:fixed-menu="editorMenu"
					editor-class="prose-sm dark:prose-invert max-w-none w-full min-h-[140px] max-h-[360px] overflow-y-auto px-3 py-2 border border-t-0 border-gray-300 rounded-b-lg bg-white dark:border-gray-600 dark:bg-gray-800"
					@change="(html) => (draft.description = html)"
				/>
			</div>

			<div class="grid grid-cols-2 gap-3">
				<FormControl
					v-model="draft.date"
					label="Due date"
					type="date"
					size="sm"
					:min="minDate"
					:disabled="readonly"
				/>
				<FormControl
					v-model="draft.priority"
					label="Priority"
					type="select"
					size="sm"
					:options="TODO_PRIORITIES"
					:disabled="readonly"
				/>
			</div>
			<p v-if="todo.overdue && draft.date === todo.date" class="text-xs text-ink-gray-5">
				This ToDo is overdue. A new due date must be today or later.
			</p>

			<div class="text-xs text-ink-gray-5">
				<span v-if="todo.assigned_by && todo.assigned_by !== currentUser">
					Assigned by {{ todo.assigned_by_name }} ·
				</span>
				Created {{ formatDatetime(todo.creation) }}
			</div>

			<ErrorMessage :message="error" />
			<div v-if="!readonly" class="flex items-center gap-3">
				<Button variant="solid" :disabled="!dirty" :loading="saving" @click="save">Save</Button>
				<Button v-if="dirty" variant="ghost" @click="reset">Discard changes</Button>
			</div>
		</div>
	</div>
</template>

<script setup>
import { computed, reactive, ref, watch } from "vue"
import { Badge, call, TextEditor, toast } from "frappe-ui"
import { formatDatetime, todayIsoInUserTz } from "@spa/utils/datetime.js"
import { isEmptyHtml, normalizeHtml } from "@spa/utils/autosaveCore.js"
import { TODO_PRIORITIES } from "@spa/utils/todoSort.js"
import { session } from "@spa/session.js"
import spaConfig from "@/config"

const props = defineProps({
	todo: { type: Object, required: true },
})

const emit = defineEmits(["close", "updated"])

const API = spaConfig.api
const currentUser = session.user
const editorMenu = [["Paragraph", "Heading 2", "Heading 3"], ["Bold", "Italic"], ["Bullet List", "Numbered List"]]

const draft = reactive({ description: "", date: "", priority: "Medium" })
const saving = ref(false)
const toggling = ref(false)
const error = ref("")

const readonly = computed(() => props.todo.status === "Closed")
// Today or later; an unchanged overdue date stays valid until it is edited.
const minDate = computed(() => todayIsoInUserTz())
const dirty = computed(
	() =>
		normalizeHtml(draft.description) !== normalizeHtml(props.todo.description) ||
		(draft.date || "") !== (props.todo.date || "") ||
		draft.priority !== props.todo.priority
)

function reset() {
	draft.description = props.todo.description || ""
	draft.date = props.todo.date || ""
	draft.priority = props.todo.priority || "Medium"
	error.value = ""
}

watch(() => [props.todo.name, props.todo.modified], reset, { immediate: true })

function message(e, fallback) {
	return e?.messages?.[0] || e?.message || fallback
}

async function save() {
	if (isEmptyHtml(draft.description)) {
		error.value = "Description is required"
		return
	}
	saving.value = true
	error.value = ""
	try {
		const updated = await call(`${API}.update_todo`, {
			name: props.todo.name,
			description: draft.description,
			date: draft.date || "",
			priority: draft.priority,
			modified: props.todo.modified,
		})
		emit("updated", updated)
		toast({ title: "ToDo saved", icon: "check-circle", iconClasses: "text-ink-green-4" })
	} catch (e) {
		error.value = message(e, "Could not save the ToDo")
	} finally {
		saving.value = false
	}
}

async function toggleStatus() {
	toggling.value = true
	error.value = ""
	try {
		const method = props.todo.status === "Closed" ? "reopen_todo" : "close_todo"
		emit("updated", await call(`${API}.${method}`, { name: props.todo.name }))
	} catch (e) {
		error.value = message(e, "Could not change the ToDo")
	} finally {
		toggling.value = false
	}
}
</script>
