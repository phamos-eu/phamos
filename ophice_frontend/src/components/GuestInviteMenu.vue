<template>
	<!--
		Invite a guest to a customer meeting (#2084), from their chip or the people list. Sets a pin
		in the chosen room; the guest accepts or declines. An open invite can be taken back.
	-->
	<div
		ref="root"
		class="fixed z-50 w-72 rounded-xl border border-outline-gray-2 bg-surface-white p-2 text-sm text-ink-gray-9 shadow-2xl"
		:style="position"
		role="dialog"
		:aria-label="__('Invite {0}', [guestName])"
		data-testid="guest-invite-menu"
		tabindex="-1"
		@keydown.esc.stop.prevent="$emit('close')"
	>
		<div class="flex items-center gap-2 px-1.5 pb-2 pt-1">
			<span class="rounded-full bg-amber-600 px-1.5 text-[10px] font-semibold leading-4 text-white">{{ __("Guest") }}</span>
			<span class="min-w-0 flex-1 truncate font-medium">{{ guestName }}</span>
			<button type="button" class="rounded p-0.5 text-ink-gray-5 hover:bg-surface-gray-2" :title="__('Close')" @click="$emit('close')">
				<FeatherIcon name="x" class="h-3.5 w-3.5" />
			</button>
		</div>
		<p v-if="loading" class="px-1.5 py-1 text-xs text-ink-gray-5">{{ __("Loading…") }}</p>
		<p v-else-if="error" class="px-1.5 py-1 text-xs text-ink-red-4">{{ error }}</p>
		<template v-else>
			<!-- An invite is open or under way -->
			<div v-if="invite" class="space-y-2 rounded-lg bg-surface-gray-1 p-2">
				<p class="text-xs text-ink-gray-7">
					{{ STATUS[invite.status]?.([invite.area_title, invite.by_name]) }}
				</p>
				<Button
					v-if="invite.status !== 'arrived'"
					size="sm"
					variant="subtle"
					theme="red"
					:loading="busy === 'withdraw'"
					data-testid="guest-invite-withdraw"
					@click="withdraw"
				>
					{{ __("Take the invite back") }}
				</Button>
			</div>
			<template v-else>
				<p class="px-1.5 pb-1 text-xs text-ink-gray-6">{{ __("Invite to a customer meeting:") }}</p>
				<p v-if="!rooms.length" class="px-1.5 pb-1 text-xs text-ink-gray-5">
					{{ __("No customer meeting areas yet. Map editors can draw one.") }}
				</p>
				<button
					v-for="room in rooms"
					:key="room.name"
					type="button"
					class="flex w-full items-center gap-2 rounded-lg px-1.5 py-1.5 text-left hover:bg-surface-gray-2"
					data-testid="guest-invite-room"
					@click="inviteTo(room)"
				>
					<FeatherIcon name="briefcase" class="h-4 w-4 flex-shrink-0 text-ink-gray-6" />
					<span class="min-w-0 flex-1 truncate">{{ room.title }}</span>
					<FeatherIcon v-if="busy === room.name" name="loader" class="h-3.5 w-3.5 animate-spin text-ink-gray-5" />
				</button>
			</template>
		</template>
	</div>
</template>

<script setup>
import { computed, nextTick, onMounted, ref } from "vue"
import { Button, call, FeatherIcon, toast } from "frappe-ui"
import { __ } from "@spa/utils/i18n.js"

const props = defineProps({
	/** the guest's chip: { user: "guest:<id>", full_name } */
	guest: { type: Object, required: true },
	/** where it was clicked: { x, y } (px) */
	at: { type: Object, required: true },
})
const emit = defineEmits(["close"])

const API = "phamos.api.ophice_guest"
const STATUS = {
	pending: (args) => __("Invited to {0} by {1}. Waiting for the answer.", args),
	accepted: (args) => __("On the way to {0} (invited by {1}).", args),
	arrived: (args) => __("In {0} (invited by {1}).", args),
}

const root = ref(null)
const loading = ref(true)
const error = ref("")
const busy = ref("")
const rooms = ref([])
const invite = ref(null)
const guestName = ref(props.guest.full_name || "")

const position = computed(() => ({
	left: `${Math.max(8, Math.min(window.innerWidth - 296, props.at.x + 8))}px`,
	top: `${Math.max(8, Math.min(window.innerHeight - 260, props.at.y + 8))}px`,
}))

function errorText(e) {
	return e?.messages?.[0] || e?.message || __("Something went wrong. Please try again.")
}

async function load() {
	loading.value = true
	try {
		const data = await call(`${API}.get_customer_rooms`, { guest: props.guest.user })
		rooms.value = data.rooms || []
		invite.value = data.invite
		guestName.value = data.guest || guestName.value
	} catch (e) {
		error.value = errorText(e)
	} finally {
		loading.value = false
	}
}

async function inviteTo(room) {
	busy.value = room.name
	try {
		invite.value = await call(`${API}.invite_guest`, { guest: props.guest.user, area: room.name })
		toast({ title: __("{0} is invited to {1}.", [guestName.value, room.title]), icon: "send" })
		emit("close")
	} catch (e) {
		error.value = errorText(e)
	} finally {
		busy.value = ""
	}
}

async function withdraw() {
	busy.value = "withdraw"
	try {
		await call(`${API}.withdraw_invite`, { guest: props.guest.user })
		invite.value = null
	} catch (e) {
		error.value = errorText(e)
	} finally {
		busy.value = ""
	}
}

onMounted(() => {
	load()
	nextTick(() => root.value?.focus())
})
</script>
