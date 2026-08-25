<template>
	<div>
		<p class="mb-2 text-xs text-gray-500">Changes save automatically</p>

		<div v-if="!checklist.items?.length" class="mb-3 text-sm text-gray-500">No items yet</div>

		<div v-else class="mb-3 overflow-x-auto">
			<table class="w-full min-w-[640px] border-collapse text-sm">
				<thead>
					<tr class="border-b border-gray-200 text-left text-[11px] font-semibold uppercase tracking-wide text-gray-500">
						<th class="w-12 px-2 py-2">Done</th>
						<th class="min-w-[200px] px-2 py-2">Note</th>
						<th class="w-40 px-2 py-2">Document</th>
						<th class="w-44 px-2 py-2">Record</th>
					</tr>
				</thead>
				<tbody>
					<tr
						v-for="item in checklist.items"
						:key="item.name"
						class="border-b border-gray-100 align-top"
						:class="{ 'opacity-60': savingItem === item.name }"
					>
						<td class="px-2 py-2">
							<input
								type="checkbox"
								class="rounded border-gray-300"
								:checked="!!item.done"
								:disabled="savingItem === item.name"
								@change="saveField(item, 'done', $event.target.checked ? 1 : 0, $event)"
							/>
						</td>
						<td class="px-2 py-2">
							<TextEditor
								:content="item.note || ''"
								:fixed-menu="editorMenu"
								placeholder="Item note…"
								:editor-class="
									compact
										? 'prose-sm min-h-[72px] max-h-[140px] overflow-y-auto px-2 py-1.5 border border-gray-200 rounded-md bg-white'
										: 'prose-sm min-h-[96px] max-h-[180px] overflow-y-auto px-2 py-1.5 border border-gray-200 rounded-md bg-white'
								"
								@change="(html) => onNoteChange(item, html)"
							/>
						</td>
						<td class="px-2 py-2">
							<FrappeLink
								doctype="DocType"
								:model-value="item.document || ''"
								placeholder="DocType"
								:disabled="savingItem === item.name"
								@update:model-value="(val) => onDocumentChange(item, val)"
							/>
						</td>
						<td class="px-2 py-2">
							<FrappeLink
								:doctype="item.document || 'DocType'"
								:model-value="item.record || ''"
								placeholder="Record"
								:disabled="!item.document || savingItem === item.name"
								@update:model-value="(val) => saveField(item, 'record', val)"
							/>
						</td>
					</tr>
				</tbody>
			</table>
		</div>

		<Button :loading="adding" size="sm" @click="addItem">Add item</Button>
	</div>
</template>

<script setup>
import { ref } from "vue"
import { call, TextEditor, debounce } from "frappe-ui"
import FrappeLink from "@spa/components/FrappeLink.vue"

const props = defineProps({
	checklist: { type: Object, required: true },
	compact: { type: Boolean, default: false },
})

const emit = defineEmits(["updated"])

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

const savingItem = ref(null)
const adding = ref(false)

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
	debouncedNoteSave(item, html)
}

async function addItem() {
	adding.value = true
	try {
		const updated = await call(`${API}.add_spa_checklist_item`, {
			checklist_name: props.checklist.name,
			values: {},
		})
		emit("updated", updated)
	} finally {
		adding.value = false
	}
}
</script>
