<template>
	<!-- The team's successes (#1981): found by the daily rules, kudos and customer praise.
	     Full height; only the list scrolls. -->
	<div class="flex h-full min-h-0 flex-col bg-surface-gray-1">
		<div class="flex flex-shrink-0 flex-wrap items-center gap-2 border-b border-outline-gray-2 px-4 py-2">
			<div class="flex flex-wrap items-center gap-1" role="group">
				<button
					v-for="option in TYPES"
					:key="option.value"
					type="button"
					class="rounded px-2 py-0.5 text-xs"
					:class="filter === option.value ? 'bg-surface-gray-7 text-ink-white' : 'bg-surface-gray-2 text-ink-gray-7 hover:bg-surface-gray-3'"
					:aria-pressed="filter === option.value"
					@click="filter = option.value"
				>
					{{ option.label }}
				</button>
			</div>
			<div class="ml-auto flex items-center gap-2">
				<Button size="sm" variant="subtle" @click="openPraise">
					<template #prefix><FeatherIcon name="message-circle" class="h-3.5 w-3.5" /></template>
					{{ __("Customer praise") }}
				</Button>
				<Button size="sm" variant="solid" @click="openKudos">
					<template #prefix><FeatherIcon name="award" class="h-3.5 w-3.5" /></template>
					{{ __("Give kudos") }}
				</Button>
			</div>
		</div>

		<div v-if="error" class="m-4 rounded-lg border border-outline-gray-2 bg-surface-red-1 p-4 text-sm text-ink-red-4">{{ error }}</div>
		<section v-else class="min-h-0 flex-1 overflow-auto">
			<div v-if="loading" class="px-4 py-10 text-center text-sm text-ink-gray-5">{{ __("Loading successes…") }}</div>
			<p v-else-if="!shown.length" class="px-4 py-10 text-center text-sm text-ink-gray-5">
				{{ __("No successes yet. The daily rules add them as the team delivers; kudos and praise you can add now.") }}
			</p>
			<ul v-else class="divide-y divide-outline-gray-1 bg-surface-white">
				<li v-for="row in shown" :key="row.name" class="flex items-start gap-3 px-4 py-2.5">
					<span class="mt-0.5 text-lg leading-none" aria-hidden="true">{{ ICONS[row.success_type] || "🎉" }}</span>
					<div class="min-w-0 flex-1">
						<div class="text-sm font-medium text-ink-gray-9">{{ row.title }}</div>
						<p v-if="row.text" class="whitespace-pre-line text-sm text-ink-gray-7">{{ row.text }}</p>
						<div class="mt-0.5 flex flex-wrap gap-x-3 text-xs text-ink-gray-5">
							<span>{{ __(row.success_type) }}</span>
							<span>{{ formatDay(row.date) }}</span>
							<span v-if="row.employee_name && row.success_type !== 'Kudos'">{{ row.employee_name }}</span>
							<span v-if="row.success_type === 'Customer praise' && row.given_by_name">{{ __("entered by {0}", [row.given_by_name]) }}</span>
						</div>
					</div>
				</li>
			</ul>
		</section>

		<Dialog v-model="kudosOpen" :options="{ title: __('Give kudos'), size: 'lg' }">
			<template #body-content>
				<div class="space-y-3">
					<FormControl v-model="kudos.employee" :label="__('To')" type="select" size="sm" :options="peopleOptions(false)" />
					<FormControl v-model="kudos.text" :label="__('For what')" type="textarea" size="sm" :rows="4" />
					<p class="text-xs text-ink-gray-5">{{ __("The team sees the kudos and that they are from you; they are also posted in the team chat.") }}</p>
					<ErrorMessage v-if="dialogError" :message="dialogError" />
				</div>
			</template>
			<template #actions>
				<div class="flex justify-end gap-2">
					<Button variant="subtle" @click="kudosOpen = false">{{ __("Close") }}</Button>
					<Button variant="solid" :loading="saving" :disabled="!kudos.employee || !kudos.text.trim()" @click="saveKudos">{{ __("Give kudos") }}</Button>
				</div>
			</template>
		</Dialog>

		<Dialog v-model="praiseOpen" :options="{ title: __('Customer praise'), size: 'lg' }">
			<template #body-content>
				<div class="space-y-3">
					<FormControl v-model="praise.customer" :label="__('Customer')" type="select" size="sm" :options="customerOptions" />
					<FormControl v-model="praise.text" :label="__('What they said')" type="textarea" size="sm" :rows="4" />
					<FormControl v-model="praise.employee" :label="__('About (optional)')" type="select" size="sm" :options="peopleOptions(true)" />
					<ErrorMessage v-if="dialogError" :message="dialogError" />
				</div>
			</template>
			<template #actions>
				<div class="flex justify-end gap-2">
					<Button variant="subtle" @click="praiseOpen = false">{{ __("Close") }}</Button>
					<Button variant="solid" :loading="saving" :disabled="!praise.customer || !praise.text.trim()" @click="savePraise">{{ __("Add praise") }}</Button>
				</div>
			</template>
		</Dialog>
	</div>
</template>

<script setup>
import { computed, onMounted, ref } from "vue"
import { Button, Dialog, ErrorMessage, FeatherIcon, FormControl, call } from "frappe-ui"
import { formatDate } from "@spa/utils/datetime"
import { __ } from "@spa/utils/i18n.js"
import spaConfig from "../config"

const TYPES = [
	{ value: "", label: __("All") },
	{ value: "Delivery", label: __("Delivery") },
	{ value: "Implementations", label: __("Implementations") },
	{ value: "Timesheets", label: __("Timesheets") },
	{ value: "Team ideas", label: __("Team ideas") },
	{ value: "Picked up", label: __("Picked up") },
	{ value: "SLA", label: __("SLA") },
	{ value: "Kudos", label: __("Kudos") },
	{ value: "Customer praise", label: __("Customer praise") },
]
// system emoji, as the cockpits use them
const ICONS = {
	Delivery: "🚀",
	Implementations: "🌱",
	Timesheets: "⏱️",
	"Team ideas": "💡",
	"Picked up": "🙌",
	SLA: "⚡",
	Kudos: "👏",
	"Customer praise": "💬",
}

const loading = ref(true)
const error = ref("")
const rows = ref([])
const filter = ref("")
const options = ref({ people: [], customers: [] })
const kudosOpen = ref(false)
const praiseOpen = ref(false)
const kudos = ref({ employee: "", text: "" })
const praise = ref({ customer: "", text: "", employee: "" })
const saving = ref(false)
const dialogError = ref("")

const shown = computed(() => (filter.value ? rows.value.filter((r) => r.success_type === filter.value) : rows.value))
const customerOptions = computed(() => [{ label: __("Pick a customer…"), value: "" }, ...options.value.customers])

function peopleOptions(optional) {
	const people = options.value.people.filter((p) => optional || !p.me)
	return [{ label: optional ? __("Nobody in particular") : __("Pick a team mate…"), value: "" }, ...people]
}

function formatDay(value) {
	return value ? formatDate(value) : ""
}

async function load() {
	try {
		const [data, opts] = await Promise.all([
			call(`${spaConfig.api}.get_team_successes`),
			call(`${spaConfig.api}.get_success_options`),
		])
		rows.value = data.successes || []
		options.value = opts
		error.value = ""
	} catch (e) {
		error.value = e.messages?.[0] || e.message || __("Could not load the successes.")
	} finally {
		loading.value = false
	}
}

function openKudos() {
	kudos.value = { employee: "", text: "" }
	dialogError.value = ""
	kudosOpen.value = true
}

function openPraise() {
	praise.value = { customer: "", text: "", employee: "" }
	dialogError.value = ""
	praiseOpen.value = true
}

async function save(method, args, dialog) {
	saving.value = true
	dialogError.value = ""
	try {
		await call(`${spaConfig.api}.${method}`, args)
		dialog.value = false
		await load()
	} catch (e) {
		dialogError.value = e.messages?.[0] || e.message || __("Could not save.")
	} finally {
		saving.value = false
	}
}

const saveKudos = () => save("give_kudos", { employee: kudos.value.employee, text: kudos.value.text }, kudosOpen)
const savePraise = () =>
	save("add_customer_praise", { customer: praise.value.customer, text: praise.value.text, employee: praise.value.employee }, praiseOpen)

onMounted(load)
</script>
