<template>
	<!-- Attendees of an appointment (#1949): Required and Optional sections, people move between
	     them by drag and drop; below, everyone grouped by department. Logic: utils/attendeePicker.js -->
	<div class="space-y-3">
		<div class="grid grid-cols-2 gap-2">
			<div
				v-for="section in SECTIONS"
				:key="section"
				class="min-h-[88px] rounded border border-dashed p-2 transition-colors"
				:class="
					dropTarget === section
						? 'border-outline-gray-4 bg-surface-gray-2'
						: 'border-outline-gray-2 bg-surface-white dark:bg-surface-gray-1'
				"
				:data-section="section"
				@dragover.prevent="dropTarget = section"
				@dragleave="onDragLeave(section, $event)"
				@drop.prevent="onDrop(section, $event)"
			>
				<div class="mb-1.5 flex items-center justify-between text-[11px] font-semibold uppercase tracking-wide text-ink-gray-6">
					<span>{{ section === "required" ? __("Required") : __("Optional") }}</span>
					<span class="font-normal">{{ modelValue[section].length }}</span>
				</div>
				<div class="flex flex-wrap gap-1.5">
					<span
						v-for="email in modelValue[section]"
						:key="email"
						draggable="true"
						class="inline-flex cursor-grab items-center gap-1 rounded-full py-0.5 pl-1 pr-1 text-xs font-medium"
						:class="
							section === 'required'
								? 'bg-surface-gray-3 text-ink-gray-9'
								: 'bg-surface-gray-2 text-ink-gray-7'
						"
						:title="email"
						@dragstart="onDragStart(email, $event)"
						@dragend="dropTarget = null"
					>
						<Avatar size="xs" shape="circle" :image="person(email).image || undefined" :label="person(email).name" />
						<span class="max-w-[140px] truncate pl-0.5">{{ person(email).name }}</span>
						<button
							type="button"
							class="rounded-full p-0.5 text-ink-gray-6 hover:bg-surface-gray-4 hover:text-ink-gray-9"
							:aria-label="__('Remove {0}', [person(email).name])"
							@click="update(removeAttendee(modelValue, email))"
						>
							<FeatherIcon name="x" class="h-3 w-3" />
						</button>
					</span>
					<span v-if="!modelValue[section].length" class="text-xs text-ink-gray-4">
						{{ section === "required" ? __("Nobody yet") : __("Drag people here") }}
					</span>
				</div>
			</div>
		</div>

		<div class="rounded border border-outline-gray-2">
			<div class="border-b border-outline-gray-2 p-1.5">
				<FormControl v-model="query" type="text" size="sm" :placeholder="__('Search people…')" />
			</div>
			<div class="max-h-56 overflow-y-auto">
				<div v-for="group in filteredGroups" :key="group.department || '-'">
					<button
						type="button"
						class="flex w-full items-center gap-1.5 bg-surface-gray-1 px-2 py-1 text-left text-[11px] font-semibold uppercase tracking-wide text-ink-gray-6 hover:bg-surface-gray-2 dark:bg-surface-gray-2"
						:title="
							departmentState(modelValue, group) === 'all'
								? __('Remove everyone in {0}', [group.label])
								: __('Add everyone in {0}', [group.label])
						"
						@click="update(toggleDepartment(modelValue, group))"
					>
						<FeatherIcon :name="groupIcon(group)" class="h-3 w-3" />
						<span class="flex-1 truncate">{{ group.label }}</span>
						<span class="font-normal">{{ group.people.length }}</span>
					</button>
					<button
						v-for="p in group.people"
						:key="p.email"
						type="button"
						class="flex w-full items-center gap-2 px-2 py-1 text-left text-xs hover:bg-surface-gray-2 disabled:cursor-default disabled:opacity-60"
						:disabled="isPicked(modelValue, p.email)"
						@click="update(addAttendees(modelValue, [p.email]))"
					>
						<Avatar size="xs" shape="circle" :image="p.image || undefined" :label="p.name" />
						<span class="min-w-0 flex-1 truncate text-ink-gray-8">{{ p.name }}</span>
						<FeatherIcon v-if="isPicked(modelValue, p.email)" name="check" class="h-3 w-3 text-ink-gray-5" />
					</button>
				</div>
				<div v-if="!filteredGroups.length" class="px-2 py-3 text-center text-xs text-ink-gray-5">
					{{ __("No people found") }}
				</div>
			</div>
		</div>
	</div>
</template>

<script setup>
import { computed, ref } from "vue"
import { Avatar, FeatherIcon, FormControl } from "frappe-ui"
import {
	SECTIONS,
	addAttendees,
	departmentState,
	isPicked,
	moveAttendee,
	peopleIndex,
	personFor,
	removeAttendee,
	toggleDepartment,
} from "@spa/utils/attendeePicker.js"
import { __ } from "@spa/utils/i18n.js"

const props = defineProps({
	// { required: [email], optional: [email] }
	modelValue: { type: Object, required: true },
	// get_appointment_options().departments: [{ department, label, people: [{ email, name, image }] }]
	departments: { type: Array, default: () => [] },
})
const emit = defineEmits(["update:modelValue"])

const DRAG_TYPE = "text/x-attendee-email"
const query = ref("")
const dropTarget = ref(null)

const index = computed(() => peopleIndex(props.departments))

const filteredGroups = computed(() => {
	const q = query.value.trim().toLowerCase()
	if (!q) return props.departments
	return props.departments
		.map((group) => ({
			...group,
			people: group.label.toLowerCase().includes(q)
				? group.people
				: group.people.filter((p) => `${p.name} ${p.email}`.toLowerCase().includes(q)),
		}))
		.filter((group) => group.people.length)
})

function person(email) {
	return personFor(index.value, email)
}

function groupIcon(group) {
	return { all: "check", some: "minus", none: "plus" }[departmentState(props.modelValue, group)]
}

function update(value) {
	emit("update:modelValue", value)
}

function onDragStart(email, event) {
	event.dataTransfer.setData(DRAG_TYPE, email)
	event.dataTransfer.effectAllowed = "move"
}

function onDragLeave(section, event) {
	// Leaving for a chip inside the same zone is not leaving the zone.
	if (!event.currentTarget.contains(event.relatedTarget) && dropTarget.value === section) dropTarget.value = null
}

function onDrop(section, event) {
	dropTarget.value = null
	const email = event.dataTransfer.getData(DRAG_TYPE)
	if (email) update(moveAttendee(props.modelValue, email, section))
}
</script>
