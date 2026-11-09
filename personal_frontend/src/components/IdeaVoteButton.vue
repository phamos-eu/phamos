<template>
	<!-- My vote on someone else's idea (#1842); my own ideas show the count only. -->
	<span v-if="row.mine" class="shrink-0 whitespace-nowrap pt-0.5 text-xs text-ink-gray-5">
		{{ __("Your idea") }} · {{ voteLabel(row.vote_count) }}
	</span>
	<Button
		v-else
		class="shrink-0"
		:variant="row.voted ? 'solid' : 'subtle'"
		:loading="pending"
		:aria-pressed="row.voted ? 'true' : 'false'"
		:aria-label="row.voted ? __('Take back your vote') : __('Vote for this idea')"
		:title="row.voted ? __('Take back your vote') : __('Vote for this idea')"
		@click.prevent="toggle"
	>
		<template #prefix><FeatherIcon name="thumbs-up" class="h-3.5 w-3.5" /></template>
		{{ row.vote_count }}
	</Button>
</template>

<script setup>
import { ref } from "vue"
import { __ } from "@spa/utils/i18n.js"
import { notify } from "@spa/utils/notify.js"
import { toggleVote, voteLabel } from "../ideasStore.js"

const props = defineProps({ row: { type: Object, required: true } })
const emit = defineEmits(["voted"])
const pending = ref(false)

async function toggle() {
	if (pending.value) return
	pending.value = true
	try {
		const result = await toggleVote(props.row.name)
		emit("voted", result)
	} catch (e) {
		notify.error(__("Could not save your vote"), e?.messages?.[0] || e?.message || "")
	} finally {
		pending.value = false
	}
}
</script>
