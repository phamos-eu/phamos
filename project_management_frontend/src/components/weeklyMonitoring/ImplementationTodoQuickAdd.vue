<template>
	<form class="flex flex-wrap items-end gap-2" @submit.prevent="submit">
		<div class="min-w-[200px] flex-1">
			<label class="mb-1 block text-xs font-medium text-gray-600 dark:text-gray-400">Topic</label>
			<input
				v-model="description"
				type="text"
				class="w-full rounded-md border border-gray-300 bg-white px-3 py-2 text-sm dark:border-gray-600 dark:bg-gray-800 dark:text-gray-200"
				placeholder="Follow-up action…"
			/>
		</div>
		<div>
			<label class="mb-1 block text-xs font-medium text-gray-600 dark:text-gray-400">Due date</label>
			<DatePicker v-model="dueDate" placeholder="Due date" class="w-40" />
		</div>
		<div class="min-w-[160px]">
			<label class="mb-1 block text-xs font-medium text-gray-600 dark:text-gray-400">Assignee</label>
			<select
				v-model="allocatedTo"
				class="w-full rounded-md border border-gray-300 bg-white px-3 py-2 text-sm dark:border-gray-600 dark:bg-gray-800 dark:text-gray-200"
			>
				<option value="">—</option>
				<option v-for="user in users" :key="user.name" :value="user.name">
					{{ user.full_name }}
				</option>
			</select>
		</div>
		<Button type="submit" variant="solid" :loading="saving" class="mb-0.5">Add</Button>
	</form>
</template>

<script setup>
import { ref } from "vue"
import { call, DatePicker, toast } from "frappe-ui"

const props = defineProps({
	implementation: {
		type: String,
		required: true,
	},
	users: {
		type: Array,
		default: () => [],
	},
	defaultAssignee: {
		type: String,
		default: "",
	},
})

const emit = defineEmits(["created"])

const API = "phamos.api.project_management_spa"

const description = ref("")
const dueDate = ref("")
const allocatedTo = ref(props.defaultAssignee || "")
const saving = ref(false)

async function submit() {
	if (!description.value.trim()) {
		toast.error("Topic is required")
		return
	}
	saving.value = true
	try {
		const todo = await call(`${API}.create_implementation_todo`, {
			implementation: props.implementation,
			description: description.value.trim(),
			date: dueDate.value || null,
			allocated_to: allocatedTo.value || null,
		})
		description.value = ""
		dueDate.value = ""
		allocatedTo.value = props.defaultAssignee || ""
		emit("created", todo)
		toast.success("To-do created")
	} catch (e) {
		toast.error(e?.messages?.[0] || e?.message || "Could not create to-do")
	} finally {
		saving.value = false
	}
}
</script>
