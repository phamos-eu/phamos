<template>
	<Dialog
		:model-value="modelValue"
		:options="{
			title: 'New checklist',
			size: '3xl',
			actions: [
				{
					label: 'Cancel',
					variant: 'subtle',
					onClick: () => emit('update:modelValue', false),
				},
				{
					label: creating ? 'Creating…' : 'Create checklist',
					variant: 'solid',
					loading: creating,
					onClick: submit,
				},
			],
		}"
		@update:model-value="emit('update:modelValue', $event)"
	>
		<template #body-content>
			<div class="space-y-4">
				<FormControl
					v-model="title"
					label="Title"
					type="text"
					required
					size="sm"
					placeholder="Checklist title"
				/>

				<div>
					<label class="mb-1.5 block text-xs font-medium text-gray-600 dark:text-gray-400">
						Checklist Owner *
					</label>
					<FrappeLink
						doctype="User"
						v-model="checklistOwner"
						placeholder="Select owner"
						query="phamos.api.checklist_inbox.checklist_owner_query"
					/>
				</div>

				<div>
					<label class="mb-2 block text-xs font-medium text-gray-600 dark:text-gray-400">Items *</label>

					<div class="space-y-3">
						<div
							v-for="(row, index) in rows"
							:key="row.id"
							class="rounded-md border border-gray-200 p-3 dark:border-gray-700 dark:bg-gray-800/40"
						>
							<div class="mb-2 flex items-center justify-between gap-2">
								<span class="text-xs font-semibold text-gray-500 dark:text-gray-400">
									Item {{ index + 1 }}
								</span>
								<button
									v-if="rows.length > 1"
									type="button"
									class="text-xs text-gray-500 hover:text-red-600 dark:text-gray-400 dark:hover:text-red-400"
									@click="removeRow(row.id)"
								>
									Remove
								</button>
							</div>
							<div class="space-y-2">
								<input
									v-model="row.description"
									type="text"
									class="w-full rounded-md border border-gray-300 px-3 py-2 text-sm"
									placeholder="Short description"
								/>
								<textarea
									:ref="(el) => setNoteRef(row.id, el)"
									v-model="row.note"
									rows="2"
									class="w-full rounded-md border border-gray-300 bg-white px-3 py-2 text-sm text-gray-900 dark:border-gray-600 dark:bg-gray-800 dark:text-gray-100"
									placeholder="What needs to be done?"
								/>
								<div class="grid grid-cols-2 gap-2">
									<div>
										<label class="mb-1 block text-[11px] font-medium text-gray-500 dark:text-gray-400">
											Document
										</label>
										<FrappeLink
											doctype="DocType"
											:model-value="row.document"
											placeholder="DocType"
											@update:model-value="(val) => onDocumentChange(row, val)"
										/>
									</div>
									<div>
										<label class="mb-1 block text-[11px] font-medium text-gray-500 dark:text-gray-400">
											Record
										</label>
										<FrappeLink
											:doctype="row.document || 'DocType'"
											v-model="row.record"
											placeholder="Record"
											:disabled="!row.document"
										/>
									</div>
								</div>
							</div>
						</div>
					</div>

					<div class="mt-3">
						<Button size="sm" @click="addRow">Add item</Button>
					</div>
				</div>

				<p v-if="error" class="text-sm text-red-600 dark:text-red-400">{{ error }}</p>
			</div>
		</template>
	</Dialog>
</template>

<script setup>
import { nextTick, ref, watch } from "vue"
import { call } from "frappe-ui"
import FrappeLink from "@spa/components/FrappeLink.vue"

const props = defineProps({
	modelValue: { type: Boolean, default: false },
	document: { type: String, required: true },
	referenceRecord: { type: String, required: true },
	referenceTitle: { type: String, default: "" },
})

const emit = defineEmits(["update:modelValue", "created"])

const API = "phamos.api.checklist_inbox"

let nextId = 1
const title = ref("")
const checklistOwner = ref("")
const rows = ref([])
const noteRefs = new Map()
const creating = ref(false)
const error = ref("")

function setNoteRef(id, el) {
	if (el) noteRefs.set(id, el)
	else noteRefs.delete(id)
}

function emptyRow() {
	return {
		id: nextId++,
		description: "",
		note: "",
		document: "",
		record: "",
	}
}

function resetForm() {
	nextId = 1
	noteRefs.clear()
	title.value = (props.referenceTitle || "").trim()
	checklistOwner.value = ""
	rows.value = [emptyRow()]
	error.value = ""
}

async function addRow() {
	const row = emptyRow()
	rows.value = [...rows.value, row]
	await nextTick()
	noteRefs.get(row.id)?.focus()
}

function removeRow(id) {
	rows.value = rows.value.filter((row) => row.id !== id)
}

function onDocumentChange(row, document) {
	if (row.document !== document) {
		row.record = ""
	}
	row.document = document
}

function buildItems() {
	return rows.value
		.map((row) => ({
			description: (row.description || "").trim(),
			note: row.note.trim(),
			document: row.document || null,
			record: row.record || null,
		}))
		.filter((row) => row.description || row.note || row.document || row.record)
}

async function submit() {
	error.value = ""
	const name = title.value.trim()
	if (!name) {
		error.value = "Title is required"
		return
	}
	const owner = (checklistOwner.value || "").trim()
	if (!owner) {
		error.value = "Checklist Owner is required"
		return
	}
	const items = buildItems()
	if (!items.length) {
		error.value = "Add at least one checklist item"
		return
	}

	creating.value = true
	try {
		const created = await call(`${API}.create_spa_checklist`, {
			document: props.document,
			reference_record: props.referenceRecord,
			name,
			checklist_owner: owner,
			items,
		})
		emit("created", created)
		emit("update:modelValue", false)
	} catch (e) {
		error.value = e?.messages?.[0] || e?.message || "Could not create checklist"
	} finally {
		creating.value = false
	}
}

watch(
	() => props.modelValue,
	(open) => {
		if (open) resetForm()
	}
)
</script>
