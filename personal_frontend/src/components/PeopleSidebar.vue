<template>
	<!-- Everyone with Raven, online first, and what they are doing (#2063). Click to chat. -->
	<aside
		class="flex w-64 flex-shrink-0 flex-col border-r border-outline-gray-2 bg-surface-white text-ink-gray-9"
		:aria-label="__('People')"
		data-testid="people-sidebar"
	>
		<div class="flex items-center gap-2 px-3 pb-2 pt-3">
			<span class="text-sm font-semibold">{{ __("People") }}</span>
			<span class="text-xs text-ink-gray-5">{{ __("{0} online", [onlineCount]) }}</span>
		</div>
		<div class="px-3 pb-2">
			<input
				v-model="query"
				type="search"
				class="form-input h-7 w-full rounded border-outline-gray-2 bg-surface-gray-2 px-2 text-xs text-ink-gray-9"
				:placeholder="__('Find a person')"
				data-testid="people-search"
				@keydown.esc.stop.prevent="query ? (query = '') : $event.target.blur()"
			/>
		</div>
		<ul class="min-h-0 flex-1 overflow-y-auto px-1.5 pb-2">
			<li v-for="person in shown" :key="person.user">
				<button
					type="button"
					class="flex w-full items-center gap-2.5 rounded-lg px-1.5 py-1.5 text-left hover:bg-surface-gray-2"
					:class="{ 'opacity-60': !person.online }"
					:disabled="person.user === me"
					data-testid="person"
					@click="$emit('pick', person, $event)"
				>
					<span class="relative flex-shrink-0">
						<span
							class="block rounded-full"
							:style="{ boxShadow: `0 0 0 2px ${person.user === me ? 'rgb(37,99,235)' : `hsl(${ringHue(person.user)} 80% 45%)`}` }"
						>
							<UserAvatar :name="person.user" :label="person.full_name" :image="person.user_image" size="sm" />
						</span>
						<span
							class="absolute -bottom-0.5 -right-0.5 h-2.5 w-2.5 rounded-full border-2 border-surface-white"
							:class="dotClass(person)"
						/>
					</span>
					<span class="min-w-0 flex-1">
						<span class="block truncate text-sm">
							{{ person.full_name }}<span v-if="person.user === me" class="text-ink-gray-5"> ({{ __("you") }})</span>
						</span>
						<span class="flex items-center gap-1 truncate text-xs text-ink-gray-5">
							<FeatherIcon v-if="lineOf(person).icon" :name="lineOf(person).icon" class="h-3 w-3 flex-shrink-0" />
							<span class="truncate">{{ lineOf(person).text }}</span>
						</span>
					</span>
				</button>
				<WorkingOnCard v-if="person.working_on" :card="person.working_on" class="mb-1 ml-11 mr-1.5" />
			</li>
		</ul>
		<label class="flex cursor-pointer items-start gap-2 border-t border-outline-gray-2 px-3 py-2 text-xs text-ink-gray-6">
			<input
				type="checkbox"
				class="mt-0.5 rounded"
				:checked="hideDetails"
				data-testid="hide-details"
				@change="$emit('hide', $event.target.checked)"
			/>
			<span>
				<span class="font-medium text-ink-gray-8">{{ __("Hide my details") }}</span><br />
				{{ __("Others then only see that you are online, not where or on what.") }}
			</span>
		</label>
	</aside>
</template>

<script setup>
import { computed, ref } from "vue"
import { FeatherIcon } from "frappe-ui"
import UserAvatar from "@spa/components/UserAvatar.vue"
import WorkingOnCard from "./WorkingOnCard.vue"
import { __ } from "@spa/utils/i18n.js"
import { clockTime } from "../utils/ophiceTime.js"
import { ringHue } from "../utils/ophiceColor.js"

const props = defineProps({
	people: { type: Array, default: () => [] },
	me: { type: String, default: "" },
	hideDetails: { type: Boolean, default: false },
	/** Date.now(), ticking */
	now: { type: Number, default: () => Date.now() },
})
defineEmits(["pick", "hide"])

const query = ref("")
const onlineCount = computed(() => props.people.filter((p) => p.online).length)
const shown = computed(() => {
	const q = query.value.trim().toLowerCase()
	if (!q) return props.people
	return props.people.filter((p) => `${p.full_name} ${p.user}`.toLowerCase().includes(q))
})

function dotClass(person) {
	if (person.status?.kind === "away") return "bg-surface-gray-5"
	if (person.status?.kind === "brb") return "bg-amber-500"
	return person.online ? "bg-green-500" : "bg-surface-gray-4"
}

/** One line: their own status first, then where they are, as far as they show it. */
function lineOf(person) {
	const status = person.status
	if (status?.kind === "away") {
		const back = status.until ? clockTime(new Date(status.until), new Date(props.now)) : ""
		return { icon: "moon", text: [__("Away"), back && __("back {0}", [back]), status.note].filter(Boolean).join(" · ") }
	}
	if (!person.online) return { icon: "", text: __("Not in Ophice") }
	if (status?.kind === "brb") return { icon: "coffee", text: [__("Be right back"), status.note].filter(Boolean).join(" · ") }
	if (person.hidden && person.user !== props.me) return { icon: "", text: __("Online") }
	if (person.in_chat) return { icon: "message-circle", text: __("In a chat") }
	if (person.area) return { icon: "video", text: __("In {0}", [person.area]) }
	return { icon: "", text: __("Around in Ophice") }
}
</script>
