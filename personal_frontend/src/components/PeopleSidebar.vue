<template>
	<!--
		In a meeting (#2067): only the chips. The people in my meeting come first, in a frame of the
		area's colour; then the others, online first. Each chip shows the glow of the area it is in.
	-->
	<aside
		v-if="meeting"
		class="flex w-16 flex-shrink-0 flex-col items-center gap-2 overflow-y-auto border-r border-outline-gray-2 bg-surface-white py-3"
		:aria-label="__('People')"
		data-testid="people-sidebar"
	>
		<div
			class="flex flex-col items-center gap-2.5 rounded-xl px-1.5 py-2"
			:style="frameStyle(meeting)"
			:title="__('In {0}', [meeting.title])"
			data-testid="people-meeting"
		>
			<button
				v-for="person in inMeeting"
				:key="person.user"
				type="button"
				class="relative rounded-full"
				:title="person.user === me ? __('{0} (you)', [person.full_name]) : person.full_name"
				:disabled="person.user === me"
				data-testid="person"
				@click="$emit('pick', person, $event)"
			>
				<span class="block rounded-full" :style="chipStyle(person)">
					<UserAvatar :name="person.user" :label="person.full_name" :image="person.user_image" size="sm" />
				</span>
				<span class="absolute -bottom-0.5 -right-0.5 h-2.5 w-2.5 rounded-full border-2 border-surface-white" :class="dotClass(person)" />
			</button>
		</div>
		<button
			v-for="person in outside"
			:key="person.user"
			type="button"
			class="relative flex-shrink-0 rounded-full"
			:class="{ 'opacity-50': !person.online }"
			:title="`${person.full_name} · ${lineOf(person).text}`"
			data-testid="person"
			@click="$emit('pick', person, $event)"
		>
			<span class="block rounded-full" :style="chipStyle(person)">
				<UserAvatar :name="person.user" :label="person.full_name" :image="person.user_image" size="sm" />
			</span>
			<span class="absolute -bottom-0.5 -right-0.5 h-2.5 w-2.5 rounded-full border-2 border-surface-white" :class="dotClass(person)" />
		</button>
	</aside>
	<!-- Everyone with Raven, online first, and what they are doing (#2063). Click to chat. -->
	<aside
		v-else
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
							:style="chipStyle(person)"
						>
							<UserAvatar :name="person.user" :label="person.full_name" :image="person.user_image" size="sm" />
						</span>
						<span
							class="absolute -bottom-0.5 -right-0.5 h-2.5 w-2.5 rounded-full border-2 border-surface-white"
							:class="dotClass(person)"
						/>
					</span>
					<span class="min-w-0 flex-1">
						<span class="flex items-center gap-1 text-sm">
							<span class="truncate">
								{{ person.full_name }}<span v-if="person.user === me" class="text-ink-gray-5"> ({{ __("you") }})</span>
							</span>
							<!-- The cockpit they are in right now (#2065). -->
							<img
								v-if="person.cockpit?.logo"
								:src="person.cockpit.logo"
								:alt="person.cockpit.title"
								:title="__('In {0}', [person.cockpit.title])"
								class="h-4 w-4 flex-shrink-0 rounded"
								data-testid="person-cockpit"
							/>
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
	/** The area I'm meeting in (collapses the list to chips), or null. */
	meeting: { type: Object, default: null },
	/** user → the area their chip stands in, from the map */
	areaOf: { type: Object, default: () => ({}) },
})
defineEmits(["pick", "hide"])

const query = ref("")
const onlineCount = computed(() => props.people.filter((p) => p.online).length)
const shown = computed(() => {
	const q = query.value.trim().toLowerCase()
	if (!q) return props.people
	return props.people.filter((p) => `${p.full_name} ${p.user}`.toLowerCase().includes(q))
})

const inMeeting = computed(() => {
	const name = props.meeting?.name
	const here = props.people.filter((p) => p.online && props.areaOf[p.user]?.name === name)
	// I'm always in it, first.
	return here.sort((a, b) => (a.user === props.me ? -1 : b.user === props.me ? 1 : 0))
})
const outside = computed(() => {
	const here = new Set(inMeeting.value.map((p) => p.user))
	return props.people.filter((p) => !here.has(p.user))
})

/** The person's ring; when they stand in a meeting area, a glow in its colour around it. */
function chipStyle(person) {
	const ring = person.user === props.me ? "rgb(37,99,235)" : `hsl(${ringHue(person.user)} 80% 45%)`
	const area = person.online ? props.areaOf[person.user] : null
	if (!area) return { boxShadow: `0 0 0 2px ${ring}` }
	const glow = `hsl(${area.color_hue} 75% 50%)`
	return { boxShadow: `0 0 0 2px ${ring}, 0 0 0 4px var(--surface-white, #fff), 0 0 0 6px ${glow}, 0 0 10px 4px hsl(${area.color_hue} 75% 50% / 0.55)` }
}

function frameStyle(area) {
	return {
		border: `2px solid hsl(${area.color_hue} 75% 50%)`,
		background: `hsl(${area.color_hue} 75% 50% / 0.12)`,
		boxShadow: `0 0 10px 2px hsl(${area.color_hue} 75% 50% / 0.35)`,
	}
}

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
