<template>
	<!-- My vote on someone else's idea (#1842); on my own idea the count and a way to take it back. -->
	<span v-if="row.mine" class="flex shrink-0 items-center gap-2 whitespace-nowrap text-xs text-ink-gray-5">
		{{ __("Your idea") }} · {{ voteLabel(row.vote_count) }}
		<Button size="sm" variant="subtle" :loading="pending" @click.prevent="withdraw">
			<template #prefix><FeatherIcon name="corner-up-left" class="h-3.5 w-3.5" /></template>
			{{ __("Withdraw from vote") }}
		</Button>
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
import { WITHDRAW_QUESTION, toggleVote, voteLabel, withdrawFromVote } from "../ideasStore.js"

const props = defineProps({ row: { type: Object, required: true } })
const emit = defineEmits(["voted", "withdrawn"])
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

async function withdraw() {
	if (pending.value || !window.confirm(__(WITHDRAW_QUESTION))) return
	pending.value = true
	try {
		const doc = await withdrawFromVote(props.row.name)
		notify.success(__("Idea withdrawn from vote"))
		emit("withdrawn", doc)
	} catch (e) {
		notify.error(__("Could not withdraw the idea"), e?.messages?.[0] || e?.message || "")
	} finally {
		pending.value = false
	}
}
</script>
