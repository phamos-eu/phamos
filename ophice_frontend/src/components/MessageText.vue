<template>
	<template v-for="(part, i) in parts" :key="i"><a v-if="part.href" :href="part.href" target="_blank" rel="noopener noreferrer" class="break-all underline underline-offset-2" data-testid="chat-link">{{ part.text }}</a><template v-else>{{ part.text }}</template></template>
</template>

<script setup>
// A chat message with its links clickable (#2169). The template stays on one line: the chat
// bubble uses white-space: pre-wrap, so any whitespace between the parts would show.
import { computed } from "vue"
import { chatParts } from "../utils/chatLinks.js"

const props = defineProps({ text: { type: String, default: "" } })
const parts = computed(() => chatParts(props.text))
</script>
