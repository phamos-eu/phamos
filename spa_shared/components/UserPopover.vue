<template>
	<Popover placement="bottom-start" class="inline-flex">
		<template #target="{ togglePopover }">
			<button
				type="button"
				class="inline-flex items-center rounded-full focus:outline-none focus-visible:ring-2 focus-visible:ring-outline-gray-4"
				:title="label"
				:aria-label="__('About {0}', [label])"
				@click.stop="togglePopover"
			>
				<slot />
			</button>
		</template>
		<template #body-main="{ close }">
			<div class="w-64 space-y-3 p-3 text-sm">
				<div class="flex items-center gap-3">
					<UserAvatar size="md" :name="user.name" :label="label" :image="user.user_image" />
					<div class="min-w-0">
						<div class="truncate font-medium text-ink-gray-9">{{ label }}</div>
						<div class="truncate text-xs text-ink-gray-5">{{ user.name }}</div>
					</div>
				</div>
				<template v-if="canMessage">
					<Button class="w-full" variant="solid" :loading="busy" @click="message(close)">
						<template #prefix><FeatherIcon name="message-square" class="h-3.5 w-3.5" /></template>
						{{ __("Message") }}
					</Button>
					<p class="text-xs text-ink-gray-5">
						{{ __("Opens your Raven chat with {0} in a new window, with a link to {1}.", [label, documentName]) }}
					</p>
				</template>
			</div>
		</template>
	</Popover>
</template>

<script setup>
// A person on a record (#1616): who they are and "Message", which opens the Raven DM with them in
// a new window and posts a link to the record there (start_issue_dm). Leaving the cockpit is the
// point: one-to-one talk happens in Raven, the record keeps the link.
import { computed, ref } from "vue"
import { Button, call, FeatherIcon, Popover, toast } from "frappe-ui"
import UserAvatar from "@spa/components/UserAvatar.vue"
import { sessionUser } from "@spa/session.js"
import { __ } from "@spa/utils/i18n.js"

const props = defineProps({
	/** { name, full_name, user_image } */
	user: { type: Object, required: true },
	/** Record the DM links to; "Message" only shows with it */
	documentName: { type: String, default: "" },
	apiPrefix: { type: String, default: "" },
	messageable: { type: Boolean, default: false },
})

const busy = ref(false)
const label = computed(() => props.user.full_name || props.user.name)
const canMessage = computed(
	() => props.messageable && props.documentName && props.apiPrefix && props.user.name !== sessionUser()
)

async function message(close) {
	// Open the window inside the click, or the browser blocks it as a popup; point it at the DM
	// once the server has it.
	const win = window.open("", "_blank")
	busy.value = true
	try {
		const result = await call(`${props.apiPrefix}.start_issue_dm`, {
			name: props.documentName,
			user: props.user.name,
		})
		if (win) win.location.href = result.url
		else window.open(result.url, "_blank")
		close()
		if (!result.linked) {
			toast({
				title: __("{0} cannot open {1}, so the chat opens without the link.", [label.value, props.documentName]),
				icon: "info",
			})
		}
	} catch (e) {
		win?.close()
		toast({ title: e?.messages?.[0] || e?.message || __("Something went wrong"), icon: "x-circle", iconClasses: "text-ink-red-4" })
	} finally {
		busy.value = false
	}
}
</script>
