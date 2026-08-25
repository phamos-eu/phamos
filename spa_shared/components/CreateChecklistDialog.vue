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
				<p v-if="referenceTitle" class="text-sm text-gray-600">
					Checklist name:
					<span class="font-medium text-gray-900">{{ referenceTitle }}</span>
				</p>

				<div>
					<div class="mb-2 flex items-center justify-between gap-2">
						<label class="text-xs font-medium text-gray-600">Items *</label>
						<Button size="sm" variant="subtle" @click="addRow">Add item</Button>
					</div>

					<div class="space-y-3">
						<div
							v-for="(row, index) in rows"
							:key="row.id"
							class="rounded-md border border-gray-200 p-3"
						>
							<div class="mb-2 flex items-center justify-between gap-2">
								<span class="text-xs font-semibold text-gray-500">Item {{ index + 1 }}</span>
								<button
									v-if="rows.length > 1"
									type="button"
									class="text-xs text-gray-500 hover:text-red-600"
									@click="removeRow(row.id)"
								>
									Remove
								</button>
							</div>
							<div class="space-y-2">
								<textarea
									v-model="row.note"
									rows="2"
									class="w-full rounded-md border border-gray-300 px-3 py-2 text-sm"
									placeholder="What needs to be done?"
								/>
								<div class="grid grid-cols-2 gap-2">
									<div>
										<label class="mb-1 block text-[11px] font-medium text-gray-500">
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
										<label class="mb-1 block text-[11px] font-medium text-gray-500">
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
				</div>

				<p v-if="error" class="text-sm text-red-600">{{ error }}</p>
			</div>
		</template>
	</Dialog>
</template>

<script setup>
import { ref, watch } from "vue"
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
const rows = ref([])
const creating = ref(false)
const error = ref("")

function emptyRow() {
	return {
		id: nextId++,
		note: "",
		document: "",
		record: "",
	}
}

function resetRows() {
	nextId = 1
	rows.value = [emptyRow()]
	error.value = ""
}

function addRow() {
	rows.value = [...rows.value, emptyRow()]
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
			note: row.note.trim(),
			document: row.document || null,
			record: row.record || null,
		}))
		.filter((row) => row.note || row.document || row.record)
}

async function submit() {
	error.value = ""
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
		if (open) resetRows()
	}
)
</script>
