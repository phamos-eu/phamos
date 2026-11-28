<template>
	<div>
		<div
			v-for="todo in todos"
			:key="todo.name"
			role="button"
			tabindex="0"
			data-list-item
			:class="[
				'flex items-start gap-3 border-b border-outline-gray-1 px-1 py-3 text-left hover:bg-surface-gray-2 focus:outline-none focus-visible:bg-surface-gray-2',
				todo.name === selectedName ? 'bg-surface-gray-2 shadow-[inset_3px_0_0_0_var(--outline-gray-4)]' : '',
			]"
			@click="emit('select', todo.name)"
			@keydown.enter.prevent="emit('select', todo.name)"
		>
			<button
				type="button"
				class="mt-0.5 flex h-4 w-4 flex-none items-center justify-center rounded-full border transition disabled:opacity-50"
				:class="
					todo.status === 'Closed'
						? 'border-ink-gray-5 bg-surface-gray-5 text-ink-white'
						: 'border-outline-gray-4 hover:border-ink-gray-7'
				"
				:title="todo.status === 'Closed' ? 'Reopen' : 'Mark as done'"
				:aria-label="todo.status === 'Closed' ? 'Reopen' : 'Mark as done'"
				:disabled="busy === todo.name"
				@click.stop="emit('toggle', todo)"
			>
				<FeatherIcon v-if="todo.status === 'Closed'" name="check" class="h-3 w-3" />
			</button>

			<div class="min-w-0 flex-1">
				<div class="flex min-w-0 items-center gap-1.5">
					<FeatherIcon
						v-if="todo.important"
						name="star"
						class="h-3.5 w-3.5 flex-none text-ink-amber-3"
						aria-label="Important"
					/>
					<div
						class="truncate text-sm"
						:class="todo.status === 'Closed' ? 'text-ink-gray-5 line-through' : 'font-medium text-ink-gray-9'"
						:title="todo.summary"
					>
						{{ todo.summary || "(no description)" }}
					</div>
				</div>
				<div v-if="todo.reference_type" class="mt-1 flex min-w-0 items-center gap-1 text-xs text-ink-gray-5">
					<span class="flex-none">{{ todo.reference_type }}</span>
					<a
						:href="todo.reference_url"
						target="_blank"
						rel="noopener"
						class="truncate text-ink-gray-7 underline-offset-2 hover:underline"
						:title="`Open ${todo.reference_type} ${todo.reference_name} in Desk`"
						@click.stop
					>
						{{ todo.reference_title || todo.reference_name }}
					</a>
				</div>
			</div>

			<div class="flex flex-none flex-col items-end gap-1">
				<span
					class="whitespace-nowrap text-xs"
					:class="todo.overdue ? 'font-medium text-ink-red-4' : 'text-ink-gray-5'"
				>
					{{ dueLabel(todo) }}
					<span
						v-if="todo.reschedule_count"
						class="ml-1"
						:class="todo.reschedule_count >= 3 ? 'font-medium text-ink-red-3' : 'text-ink-gray-5'"
						:title="`Postponed ${todo.reschedule_count} times`"
					>
						↻ {{ todo.reschedule_count }}
					</span>
				</span>
				<Badge :label="todo.priority" :theme="todoPriorityTheme(todo.priority)" size="sm" variant="subtle" />
			</div>
		</div>
	</div>
</template>

<script setup>
import { Badge } from "frappe-ui"
import { formatDate, todayIsoInUserTz } from "@spa/utils/datetime.js"
import { todoPriorityTheme } from "@spa/utils/todoSort.js"

defineProps({
	todos: { type: Array, default: () => [] },
	selectedName: { type: String, default: "" },
	busy: { type: String, default: "" },
})

const emit = defineEmits(["select", "toggle"])

function dueLabel(todo) {
	if (!todo.date) return "No date"
	if (todo.date === todayIsoInUserTz()) return "Today"
	return todo.overdue ? `Overdue · ${formatDate(todo.date)}` : formatDate(todo.date)
}
</script>
