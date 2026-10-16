<template>
	<div
		ref="el"
		:contenteditable="disabled ? 'false' : 'plaintext-only'"
		role="textbox"
		:aria-label="label"
		:aria-disabled="disabled ? 'true' : 'false'"
		:data-placeholder="placeholder"
		spellcheck="false"
		class="plain-text-field"
		:class="{ 'is-disabled': disabled }"
		@input="onInput"
		@focus="focused = true; emit('focus')"
		@blur="onBlur"
		@keydown.enter.prevent
		@paste="onPaste"
	></div>
</template>

<script setup>
// A one-line text field that is not a form <input>.
//
// Browsers decide whether to offer saving payment data (IBANs, card numbers) by looking
// at <input> elements; autocomplete="off" does not stop Chrome's IBAN prompt. A
// plain-text editable element looks and behaves like an input but is never treated as a
// payment field. Use it for values such as IBANs that are data about third parties, not
// the user's own payment details.
import { onMounted, ref, watch } from "vue"

const props = defineProps({
	modelValue: { type: String, default: "" },
	placeholder: { type: String, default: "" },
	label: { type: String, default: "" },
	disabled: { type: Boolean, default: false },
})
const emit = defineEmits(["update:modelValue", "focus", "blur"])

const el = ref(null)
const focused = ref(false)

function render(value) {
	if (el.value && el.value.innerText !== (value || "")) el.value.innerText = value || ""
}

function onInput() {
	emit("update:modelValue", el.value.innerText.replace(/\n/g, " "))
}

function onBlur() {
	focused.value = false
	render(props.modelValue)
	emit("blur")
}

function onPaste(event) {
	// Keep it plain text on one line, whatever the clipboard holds.
	event.preventDefault()
	const text = (event.clipboardData?.getData("text/plain") || "").replace(/\s*\n\s*/g, " ")
	document.execCommand("insertText", false, text)
}

// Never overwrite the text under the cursor while the user is typing.
watch(
	() => props.modelValue,
	(value) => {
		if (!focused.value) render(value)
	}
)
onMounted(() => render(props.modelValue))
</script>

<style scoped>
.plain-text-field {
	@apply flex h-8 items-center overflow-hidden whitespace-nowrap rounded-md border border-outline-gray-2 bg-surface-white px-2 text-sm text-ink-gray-9 outline-none focus:border-outline-gray-4;
}
.plain-text-field:empty::before {
	content: attr(data-placeholder);
	@apply text-ink-gray-4;
}
.plain-text-field.is-disabled {
	@apply opacity-60;
}
</style>
