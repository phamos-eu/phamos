<template>
	<!-- Name and Jitsi URL of a meeting area (#2060), new or existing. -->
	<Dialog v-model="open" :options="{ title: area?.name ? __('Edit meeting area') : __('New meeting area'), size: 'md' }">
		<template #body-content>
			<form class="space-y-3" @submit.prevent="save">
				<FormControl v-model="title" :label="__('Name')" :placeholder="__('Standup')" :maxlength="60" autofocus />
				<FormControl
					v-model="url"
					:label="__('Jitsi meeting URL')"
					placeholder="https://meet.jit.si/FullTimeDefencesRejectOverly"
				/>
				<p class="text-xs text-ink-gray-5">
					{{ __("Whoever stops inside the area joins this meeting, with microphone and camera off.") }}
				</p>
				<p v-if="error" class="text-sm text-ink-red-4">{{ error }}</p>
				<button type="submit" class="hidden" />
			</form>
		</template>
		<template #actions>
			<div class="flex items-center gap-2">
				<Button v-if="area?.name" variant="subtle" theme="red" :loading="busy === 'delete'" @click="remove">
					{{ __("Delete") }}
				</Button>
				<Button class="ml-auto" variant="ghost" @click="open = false">{{ __("Cancel") }}</Button>
				<Button variant="solid" :loading="busy === 'save'" @click="save">{{ __("Save") }}</Button>
			</div>
		</template>
	</Dialog>
</template>

<script setup>
import { computed, ref, watch } from "vue"
import { Button, Dialog, FormControl } from "frappe-ui"
import { __ } from "@spa/utils/i18n.js"

const props = defineProps({
	/** { name?, title?, meeting_url?, x, y, width, height } or null (closed) */
	area: { type: Object, default: null },
	/** async (values) => void; throws with a readable message */
	onSave: { type: Function, required: true },
	onDelete: { type: Function, required: true },
})
const emit = defineEmits(["close"])

const open = computed({
	get: () => Boolean(props.area),
	set: (value) => !value && emit("close"),
})
const title = ref("")
const url = ref("")
const error = ref("")
const busy = ref("")

watch(
	() => props.area,
	(area) => {
		title.value = area?.title || ""
		url.value = area?.meeting_url || ""
		error.value = ""
	},
	{ immediate: true }
)

async function save() {
	busy.value = "save"
	error.value = ""
	try {
		await props.onSave({ ...props.area, title: title.value, meeting_url: url.value })
		emit("close")
	} catch (e) {
		error.value = e?.message || __("The area could not be saved.")
	} finally {
		busy.value = ""
	}
}

async function remove() {
	busy.value = "delete"
	try {
		await props.onDelete(props.area)
		emit("close")
	} catch (e) {
		error.value = e?.message || __("The area could not be deleted.")
	} finally {
		busy.value = ""
	}
}
</script>
