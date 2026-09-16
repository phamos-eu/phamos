<template>
	<div class="relative">
		<label class="mb-1.5 block text-xs text-ink-gray-5">{{ label }}</label>
		<input
			ref="inputEl"
			:value="modelValue"
			type="text"
			:placeholder="placeholder"
			class="form-input block h-8 w-full rounded border border-outline-gray-2 bg-surface-white px-2 text-sm text-ink-gray-8"
			@input="onInput"
			@focus="emit('focus')"
			@keydown.down.prevent="move(1)"
			@keydown.up.prevent="move(-1)"
			@keydown.enter="onEnter"
			@keydown.esc="close"
			@blur="onBlur"
		/>

		<!-- Results drop under the field being typed in, so there's no separate
		     search box to go and find. -->
		<ul
			v-if="open && results.length"
			class="absolute z-10 mt-1 max-h-48 w-full overflow-y-auto rounded-md border border-outline-gray-2 bg-surface-white py-1 shadow-md"
		>
			<li v-for="(result, index) in results" :key="result.email">
				<button
					type="button"
					class="flex w-full items-center justify-between gap-2 px-2.5 py-1.5 text-left text-sm"
					:class="index === activeIndex ? 'bg-surface-gray-2 text-ink-gray-9' : 'text-ink-gray-8 hover:bg-surface-gray-2'"
					@mousedown.prevent="choose(result)"
				>
					<span class="min-w-0 flex-1 truncate">
						<span class="font-medium">{{ result.label }}</span>
						<span v-if="result.label !== result.email" class="text-ink-gray-6"> · {{ result.email }}</span>
					</span>
					<span class="flex-none text-xs text-ink-gray-5">{{ result.source }}</span>
				</button>
			</li>
		</ul>
	</div>
</template>

<script setup>
import { ref } from "vue"
import { call, debounce } from "frappe-ui"

const props = defineProps({
	modelValue: { type: String, default: "" },
	label: { type: String, default: "" },
	placeholder: { type: String, default: "" },
	lead: { type: String, required: true },
})

const emit = defineEmits(["update:modelValue", "focus", "blur"])

const inputEl = ref(null)
const results = ref([])
const open = ref(false)
const activeIndex = ref(0)

/** Only the fragment after the last comma is what the user is typing. */
function currentFragment(value) {
	const parts = String(value || "").split(",")
	return parts[parts.length - 1].trim()
}

const search = debounce(async (fragment) => {
	if (fragment.length < 2) {
		results.value = []
		open.value = false
		return
	}
	try {
		results.value = await call("phamos.api.sales_leads.search_email_recipients", {
			lead: props.lead,
			txt: fragment,
		})
		activeIndex.value = 0
		open.value = results.value.length > 0
	} catch (e) {
		results.value = []
		open.value = false
	}
}, 250)

function onInput(event) {
	emit("update:modelValue", event.target.value)
	search(currentFragment(event.target.value))
}

function move(step) {
	if (!open.value || !results.value.length) return
	const next = activeIndex.value + step
	activeIndex.value = (next + results.value.length) % results.value.length
}

function onEnter(event) {
	if (!open.value || !results.value.length) return
	event.preventDefault()
	choose(results.value[activeIndex.value])
}

/** Replace the fragment being typed with the chosen address. */
function choose(result) {
	const parts = String(props.modelValue || "").split(",")
	parts[parts.length - 1] = ` ${result.email}`
	emit("update:modelValue", `${parts.join(",").trim()}, `.replace(/^,\s*/, ""))
	close()
	inputEl.value?.focus()
}

function close() {
	open.value = false
	results.value = []
}

// mousedown on a result fires before blur, so the pick still lands.
function onBlur() {
	setTimeout(close, 120)
	emit("blur")
}
</script>
