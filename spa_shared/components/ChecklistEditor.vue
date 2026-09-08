<template>
	<div ref="root">
		<div v-if="!checklist.items?.length" class="mb-3 text-sm text-gray-500 dark:text-gray-400">
			No items yet
		</div>

		<div v-else class="mb-3 space-y-2">
			<div
				v-for="item in checklist.items"
				:key="item.name"
				class="rounded-lg border bg-white transition dark:bg-gray-900"
				:class="[
					expandedItem === item.name
						? 'border-gray-900 shadow-sm ring-1 ring-gray-900/10 dark:border-gray-200 dark:ring-gray-200/20'
						: 'cursor-pointer border-gray-200 hover:border-gray-300 hover:bg-gray-50 dark:border-gray-700 dark:hover:border-gray-600 dark:hover:bg-gray-800/60',
					savingItem === item.name ? 'opacity-60' : '',
				]"
				role="button"
				tabindex="0"
				@click.stop="expand(item)"
				@keydown.enter.prevent="expand(item)"
			>
				<!-- Collapsed -->
				<div v-if="expandedItem !== item.name" class="flex items-start gap-3 px-3 py-2.5">
					<div class="min-w-0 flex-1">
						<div
							v-if="(item.description || '').trim()"
							class="truncate text-sm font-medium text-gray-900 dark:text-gray-100"
						>
							{{ item.description }}
						</div>
						<div
							v-if="hasNote(item)"
							class="prose-sm dark:prose-invert max-w-none text-gray-900 dark:text-gray-100 [&_p]:my-0.5"
							:class="(item.description || '').trim() ? 'mt-0.5 text-gray-600 dark:text-gray-300' : ''"
							v-html="item.note"
						/>
						<span
							v-else-if="!(item.description || '').trim()"
							class="text-sm text-gray-400 dark:text-gray-500"
						>
							Click to edit…
						</span>
						<div
							v-if="item.document"
							class="mt-1 truncate text-xs text-gray-500 dark:text-gray-400"
						>
							{{ item.document }}
							<span v-if="item.record"> · {{ item.record }}</span>
						</div>
					</div>
					<div class="flex-shrink-0 pt-0.5" @click.stop>
						<input
							type="checkbox"
							class="h-5 w-5 rounded-full border-gray-300 text-green-600 focus:ring-green-600 dark:border-gray-600 dark:text-green-500 dark:focus:ring-green-500"
							:checked="!!item.done"
							:disabled="savingItem === item.name"
							@change="saveField(item, 'done', $event.target.checked ? 1 : 0, $event)"
						/>
					</div>
				</div>

				<!-- Expanded -->
				<div v-else class="space-y-3 px-3 py-3" @click.stop>
					<div class="flex items-start gap-3">
						<div class="min-w-0 flex-1 space-y-2">
							<input
								type="text"
								class="w-full rounded-md border border-gray-300 bg-white px-2 py-1.5 text-sm text-gray-900 dark:border-gray-600 dark:bg-gray-800 dark:text-gray-100"
								:value="item.description || ''"
								:disabled="savingItem === item.name"
								placeholder="Short description"
								@change="saveField(item, 'description', $event.target.value)"
							/>
							<TextEditor
								ref="noteEditor"
								:content="item.note || ''"
								:fixed-menu="editorMenu"
								placeholder="Item note…"
								:editor-class="
									compact
										? 'prose-sm dark:prose-invert min-h-[72px] max-h-[180px] overflow-y-auto px-2 py-1.5 border border-gray-200 rounded-md bg-white dark:border-gray-600 dark:bg-gray-800'
										: 'prose-sm dark:prose-invert min-h-[96px] max-h-[220px] overflow-y-auto px-2 py-1.5 border border-gray-200 rounded-md bg-white dark:border-gray-600 dark:bg-gray-800'
								"
								@change="(html) => onNoteChange(item, html)"
							/>
						</div>
						<div class="flex-shrink-0 pt-1" @click.stop>
							<input
								type="checkbox"
								class="h-5 w-5 rounded-full border-gray-300 text-green-600 focus:ring-green-600 dark:border-gray-600 dark:text-green-500 dark:focus:ring-green-500"
								:checked="!!item.done"
								:disabled="savingItem === item.name"
								@change="saveField(item, 'done', $event.target.checked ? 1 : 0, $event)"
							/>
						</div>
					</div>
					<div class="space-y-1.5 border-t border-gray-100 pt-3 dark:border-gray-800">
						<label class="block text-[11px] font-medium text-gray-500 dark:text-gray-400">
							Document
						</label>
						<FrappeLink
							doctype="DocType"
							:model-value="item.document || ''"
							placeholder="DocType"
							:disabled="savingItem === item.name"
							@update:model-value="(val) => onDocumentChange(item, val)"
						/>
						<template v-if="item.document">
							<label class="mt-2 block text-[11px] font-medium text-gray-500 dark:text-gray-400">
								Record
							</label>
							<FrappeLink
								:doctype="item.document"
								:model-value="item.record || ''"
								placeholder="Record"
								:disabled="savingItem === item.name"
								@update:model-value="(val) => saveField(item, 'record', val)"
							/>
						</template>
					</div>
				</div>
			</div>
		</div>

		<div class="flex flex-wrap items-center justify-between gap-2">
			<Button :loading="adding" size="sm" @click="addItem">Add item</Button>
			<Button
				v-if="deskUrl"
				variant="ghost"
				theme="gray"
				size="sm"
				icon-left="external-link"
				label="Open in Desk"
				:link="deskUrl"
			/>
		</div>
	</div>
</template>

<script setup>
import { computed, nextTick, onBeforeUnmount, onMounted, ref } from "vue"
import { call, TextEditor, debounce } from "frappe-ui"
import FrappeLink from "@spa/components/FrappeLink.vue"

const props = defineProps({
	checklist: { type: Object, required: true },
	compact: { type: Boolean, default: false },
})

const emit = defineEmits(["updated"])

const deskUrl = computed(
	() => props.checklist.desk_url || (props.checklist.name ? `/app/checklist/${props.checklist.name}` : "")
)
const API = "phamos.api.checklist_inbox"
const editorMenu = [
	"Paragraph",
	"Bold",
	"Italic",
	"Link",
	"Separator",
	"Bullet List",
	"Numbered List",
]

const root = ref(null)
const noteEditor = ref(null)
const savingItem = ref(null)
const adding = ref(false)
const expandedItem = ref(null)

async function focusNoteEditor() {
	// TextEditor creates TipTap in mounted(), then v-if reveals .ProseMirror on a later tick.
	for (let i = 0; i < 20; i++) {
		await nextTick()
		const editor = noteEditor.value?.editor
		if (editor?.view?.dom?.isConnected) {
			editor.commands.focus("end")
			return
		}
		await new Promise((resolve) => setTimeout(resolve, 20))
	}
	root.value?.querySelector?.(".ProseMirror")?.focus?.()
}

function hasNote(item) {
	const raw = pendingNotes[item.name] !== undefined ? pendingNotes[item.name] : item.note
	const note = (raw || "").replace(/<[^>]*>/g, "").replace(/&nbsp;/g, " ").trim()
	return Boolean(note)
}

function isEmptyItem(item) {
	return (
		!hasNote(item) &&
		!(item.description || "").trim() &&
		!(item.document || "").trim() &&
		!(item.record || "").trim()
	)
}

function findItem(name) {
	return (props.checklist.items || []).find((row) => row.name === name) || null
}

async function removeEmptyItem(item) {
	if (!item?.name || !isEmptyItem(item)) return
	if (typeof debouncedNoteSave.cancel === "function") {
		debouncedNoteSave.cancel()
	}
	delete pendingNotes[item.name]
	savingItem.value = item.name
	try {
		const updated = await call(`${API}.delete_spa_checklist_item`, {
			checklist_name: props.checklist.name,
			item_name: item.name,
		})
		emit("updated", updated)
	} finally {
		savingItem.value = null
	}
}

async function collapse() {
	const name = expandedItem.value
	if (!name) return
	const item = findItem(name)
	expandedItem.value = null
	if (item) await removeEmptyItem(item)
}

async function expand(item) {
	if (expandedItem.value === item.name) return
	await collapse()
	expandedItem.value = item.name
}

async function onDocClick(event) {
	if (!expandedItem.value || !root.value) return
	const path = typeof event.composedPath === "function" ? event.composedPath() : []
	const inside = root.value.contains(event.target) || path.includes(root.value)
	if (!inside) await collapse()
}

async function onKeydown(event) {
	if (event.key === "Escape" && expandedItem.value) {
		await collapse()
	}
}

onMounted(() => {
	document.addEventListener("click", onDocClick)
	document.addEventListener("keydown", onKeydown)
})

onBeforeUnmount(() => {
	document.removeEventListener("click", onDocClick)
	document.removeEventListener("keydown", onKeydown)
})

async function saveField(item, field, value, event = null) {
	const values = { [field]: value }
	savingItem.value = item.name
	try {
		const updated = await call(`${API}.update_spa_checklist_item`, {
			checklist_name: props.checklist.name,
			item_name: item.name,
			values,
		})
		emit("updated", updated)
	} catch (e) {
		if (field === "done" && event?.target) {
			event.target.checked = !value
		}
	} finally {
		savingItem.value = null
	}
}

async function onDocumentChange(item, document) {
	const previousDocument = item.document || ""
	const record = document === previousDocument ? item.record || "" : ""
	savingItem.value = item.name
	try {
		const updated = await call(`${API}.update_spa_checklist_item`, {
			checklist_name: props.checklist.name,
			item_name: item.name,
			values: { document, record },
		})
		emit("updated", updated)
	} finally {
		savingItem.value = null
	}
}

const pendingNotes = {}

const debouncedNoteSave = debounce(async (item, note) => {
	savingItem.value = item.name
	try {
		const updated = await call(`${API}.update_spa_checklist_item`, {
			checklist_name: props.checklist.name,
			item_name: item.name,
			values: { note },
		})
		emit("updated", updated)
	} finally {
		savingItem.value = null
	}
}, 500)

function onNoteChange(item, html) {
	pendingNotes[item.name] = html
	debouncedNoteSave(item, html)
}

async function addItem() {
	adding.value = true
	let newestName = null
	try {
		const updated = await call(`${API}.add_spa_checklist_item`, {
			checklist_name: props.checklist.name,
			values: {},
		})
		emit("updated", updated)
		const items = updated?.items || []
		const newest = items[items.length - 1]
		newestName = newest?.name || null
		if (newestName) expandedItem.value = newestName
	} finally {
		adding.value = false
	}
	if (newestName) await focusNoteEditor()
}
</script>
