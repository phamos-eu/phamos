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
				<div>
					<label class="mb-1.5 block text-xs text-ink-gray-5">Checklist Template</label>
					<ChecklistTemplatePicker
						v-model="checklistTemplate"
						:document="document"
						:disabled="loadingTemplate"
					/>
				</div>

				<div ref="titleFieldHost">
					<FormControl
						v-model="title"
						label="Title"
						type="text"
						required
						size="sm"
						placeholder="Checklist title"
					/>
				</div>

				<div>
					<label class="mb-1.5 block text-xs text-ink-gray-5">
						Checklist Owner
						<span class="text-ink-red-3">*</span>
					</label>
					<FrappeLink
						doctype="User"
						v-model="checklistOwner"
						placeholder="Select owner"
						query="phamos.api.checklist_inbox.checklist_owner_query"
					/>
				</div>

				<div>
					<label class="mb-2 block text-xs text-ink-gray-5">
						Items
						<span class="text-ink-red-3">*</span>
					</label>

					<div v-if="loadingTemplate" class="text-sm text-ink-gray-6">Loading template…</div>

					<div v-else class="space-y-3">
						<div
							v-for="(row, index) in rows"
							:key="row.id"
							class="rounded-lg border border-outline-gray-2 bg-surface-gray-1 p-3"
						>
							<div class="mb-2 flex items-center justify-between gap-2">
								<span class="text-xs font-medium text-ink-gray-6">
									Item {{ index + 1 }}
								</span>
								<Button
									v-if="rows.length > 1 && !checklistTemplate"
									variant="ghost"
									theme="red"
									size="sm"
									label="Remove"
									@click="removeRow(row.id)"
								/>
							</div>

							<div class="space-y-2">
								<div :ref="(el) => setDescriptionHost(row.id, el)">
									<FormControl
										v-model="row.description"
										label="Description"
										type="text"
										size="sm"
										placeholder="Short description"
									/>
								</div>
								<div>
									<label class="mb-1.5 block text-xs text-ink-gray-5">Note</label>
									<TextEditor
										:key="`${row.id}-${noteEditorKey}`"
										:content="row.note"
										:fixed-menu="noteEditorMenu"
										placeholder="What needs to be done?"
										editor-class="prose-sm max-w-none min-h-[72px] max-h-[160px] overflow-y-auto rounded-md border border-outline-gray-2 bg-surface-white px-2 py-1.5 text-ink-gray-8"
										@change="(html) => (row.note = html)"
									/>
								</div>
								<div class="grid grid-cols-2 gap-2">
									<div>
										<label class="mb-1.5 block text-xs text-ink-gray-5">Document</label>
										<FrappeLink
											doctype="DocType"
											:model-value="row.document"
											placeholder="DocType"
											@update:model-value="(val) => onDocumentChange(row, val)"
										/>
									</div>
									<div>
										<label class="mb-1.5 block text-xs text-ink-gray-5">Record</label>
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
						<Button size="sm" :disabled="loadingTemplate" @click="addRow">Add item</Button>
					</div>
				</div>

				<ErrorMessage :message="error" />
			</div>
		</template>
	</Dialog>
</template>

<script setup>
import { nextTick, ref, watch } from "vue"
import { call, TextEditor } from "frappe-ui"
import ChecklistTemplatePicker from "@spa/components/ChecklistTemplatePicker.vue"
import FrappeLink from "@spa/components/FrappeLink.vue"

const props = defineProps({
	modelValue: { type: Boolean, default: false },
	document: { type: String, required: true },
	referenceRecord: { type: String, required: true },
	referenceTitle: { type: String, default: "" },
})

const emit = defineEmits(["update:modelValue", "created"])

const API = "phamos.api.checklist_inbox"
const noteEditorMenu = ["Bold", "Italic", "Link", "Separator", "Bullet List", "Numbered List"]

let nextId = 1
const checklistTemplate = ref("")
const title = ref("")
const checklistOwner = ref("")
const titleFieldHost = ref(null)
const rows = ref([])
const descriptionHosts = new Map()
const creating = ref(false)
const loadingTemplate = ref(false)
const noteEditorKey = ref(0)
const error = ref("")
let applyToken = 0

function setDescriptionHost(id, el) {
	if (el) descriptionHosts.set(id, el)
	else descriptionHosts.delete(id)
}

function focusHostInput(host) {
	host?.querySelector?.("input")?.focus()
}

function emptyRow(seed = {}) {
	return {
		id: nextId++,
		description: seed.description || "",
		note: seed.note || "",
		document: seed.document || "",
		record: seed.record || "",
	}
}

function isEmptyHtml(html) {
	if (!html) return true
	const text = String(html)
		.replace(/<img[^>]*>/gi, "img")
		.replace(/<[^>]+>/g, "")
		.replace(/&nbsp;/g, " ")
		.trim()
	return !text
}

function resetForm() {
	nextId = 1
	descriptionHosts.clear()
	applyToken += 1
	checklistTemplate.value = ""
	title.value = (props.referenceTitle || "").trim()
	checklistOwner.value = ""
	rows.value = [emptyRow()]
	noteEditorKey.value += 1
	error.value = ""
	loadingTemplate.value = false
}

function applyBlankItems() {
	nextId = 1
	descriptionHosts.clear()
	title.value = (props.referenceTitle || "").trim()
	checklistOwner.value = ""
	rows.value = [emptyRow()]
	noteEditorKey.value += 1
}

async function applyTemplate(name) {
	const token = ++applyToken
	error.value = ""
	loadingTemplate.value = true
	try {
		const template = await call(`${API}.get_checklist_template`, { name })
		if (token !== applyToken) return
		if (template.document && template.document !== props.document) {
			error.value = `Template is for ${template.document}, not ${props.document}`
			checklistTemplate.value = ""
			applyBlankItems()
			return
		}
		nextId = 1
		descriptionHosts.clear()
		title.value = (template.title || "").trim() || (props.referenceTitle || "").trim()
		checklistOwner.value = template.checklist_template_owner || ""
		const items = template.items || []
		rows.value = items.length
			? items.map((item) => emptyRow(item))
			: [emptyRow()]
		noteEditorKey.value += 1
	} catch (e) {
		if (token !== applyToken) return
		error.value = e?.messages?.[0] || e?.message || "Could not load checklist template"
		checklistTemplate.value = ""
		applyBlankItems()
	} finally {
		if (token === applyToken) loadingTemplate.value = false
	}
}

async function focusTitleEnd() {
	await nextTick()
	// Let Dialog finish mounting/focus trapping before we take focus.
	await new Promise((resolve) => setTimeout(resolve, 50))
	const input = titleFieldHost.value?.querySelector?.("input")
	if (!input) return
	input.focus()
	const len = (input.value || "").length
	input.setSelectionRange(len, len)
}

async function addRow() {
	const row = emptyRow()
	rows.value = [...rows.value, row]
	await nextTick()
	focusHostInput(descriptionHosts.get(row.id))
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
		.map((row) => {
			const note = isEmptyHtml(row.note) ? "" : row.note
			return {
				description: (row.description || "").trim(),
				note,
				document: row.document || null,
				record: row.record || null,
			}
		})
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
			checklist_template: checklistTemplate.value || null,
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
	async (open) => {
		if (!open) return
		resetForm()
		await focusTitleEnd()
	}
)

watch(checklistTemplate, (name, previous) => {
	if (!props.modelValue) return
	const next = (name || "").trim()
	const prev = (previous || "").trim()
	if (next === prev) return
	if (!next) {
		applyToken += 1
		loadingTemplate.value = false
		applyBlankItems()
		return
	}
	applyTemplate(next)
})
</script>
