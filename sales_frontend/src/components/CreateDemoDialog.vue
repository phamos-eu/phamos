<template>
	<Dialog
		:options="{
			title: `Create Demo — ${lead.lead_name || lead.name}`,
			size: '3xl',
			actions: [
				{ label: 'Cancel', variant: 'subtle', onClick: () => emit('update:modelValue', false) },
				{
					label: saving ? 'Creating…' : 'Create Demo',
					variant: 'solid',
					loading: saving,
					onClick: submit,
				},
			],
		}"
		:model-value="modelValue"
		@update:model-value="emit('update:modelValue', $event)"
	>
		<template #body-content>
			<div class="space-y-4">
				<FormControl v-model="subject" label="Subject" type="text" size="sm" required />

				<!-- Scheduling: same options the Mailcow-backed Desk dialogs offer
				     (day + duration + free-slot lookup against the organiser's calendar). -->
				<section class="rounded-md border border-outline-gray-2 p-3">
					<div class="mb-2 text-[11px] font-semibold uppercase tracking-wide text-ink-gray-6">
						Appointment
					</div>
					<div class="grid grid-cols-3 gap-3">
						<FormControl v-model="day" label="Day" type="date" size="sm" />
						<FormControl
							v-model="durationMinutes"
							label="Duration"
							type="select"
							size="sm"
							:options="durationOptions"
						/>
						<div class="flex items-end">
							<Button :loading="loadingSlots" class="w-full" @click="fetchSlots">
								Fetch available slots
							</Button>
						</div>
					</div>

					<div v-if="slotsError" class="mt-2 text-xs text-red-600">{{ slotsError }}</div>

					<div v-if="slots.length" class="mt-3 flex flex-wrap gap-2">
						<button
							v-for="slot in slots"
							:key="slot.start_local"
							type="button"
							class="rounded-md border px-2.5 py-1 text-xs transition"
							:class="
								startsOn === slot.start_local
									? 'border-transparent bg-surface-gray-7 text-ink-white'
									: 'border-outline-gray-2 text-ink-gray-7 hover:bg-surface-gray-2'
							"
							@click="selectSlot(slot)"
						>
							{{ slot.label || `${slot.start_local} – ${slot.end_local}` }}
						</button>
					</div>
					<p v-else-if="slotsFetched && !loadingSlots && !slotsError" class="mt-2 text-xs text-ink-gray-5">
						No free slots found for that day — pick another day, or set the times manually below.
					</p>

					<div class="mt-3 grid grid-cols-2 gap-3">
						<div>
							<label class="mb-1.5 block text-xs text-ink-gray-5">Starts On</label>
							<input
								v-model="startsOn"
								type="datetime-local"
								class="form-input block h-8 w-full rounded border border-outline-gray-2 bg-surface-white px-2 text-sm text-ink-gray-8"
							/>
						</div>
						<div>
							<label class="mb-1.5 block text-xs text-ink-gray-5">Ends On</label>
							<input
								v-model="endsOn"
								type="datetime-local"
								class="form-input block h-8 w-full rounded border border-outline-gray-2 bg-surface-white px-2 text-sm text-ink-gray-8"
							/>
						</div>
					</div>
				</section>

				<!-- Draft-only: the selection isn't persisted (see demoModules.js). -->
				<section class="rounded-md border border-outline-gray-2 p-3">
					<div class="mb-2 flex items-center justify-between">
						<span class="text-[11px] font-semibold uppercase tracking-wide text-ink-gray-6">
							Modules to demo
						</span>
						<span class="text-xs text-ink-gray-5">{{ selectedModules.length }} selected</span>
					</div>
					<div class="max-h-48 overflow-y-auto">
						<table class="w-full text-sm">
							<tbody>
								<tr
									v-for="module in DEMO_MODULES"
									:key="module.key"
									class="cursor-pointer border-b border-outline-gray-1 last:border-0 hover:bg-surface-gray-2"
									@click="toggleModule(module.key)"
								>
									<td class="w-8 py-1.5 pl-1">
										<input
											type="checkbox"
											class="h-4 w-4 rounded border-outline-gray-3"
											:checked="selectedModules.includes(module.key)"
											@click.stop
											@change="toggleModule(module.key)"
										/>
									</td>
									<td class="py-1.5 font-medium text-ink-gray-8">{{ module.label }}</td>
									<td class="py-1.5 text-xs text-ink-gray-6">{{ module.description }}</td>
								</tr>
							</tbody>
						</table>
					</div>
				</section>

				<FormControl
					v-model="agenda"
					label="Agenda"
					type="textarea"
					size="sm"
					rows="3"
					placeholder="What will be shown, who is attending…"
				/>

				<ErrorMessage :message="error" />
			</div>
		</template>
	</Dialog>
</template>

<script setup>
import { computed, ref, watch } from "vue"
import { call } from "frappe-ui"
import { DEMO_MODULES } from "@/demoModules.js"

const props = defineProps({
	modelValue: { type: Boolean, default: false },
	lead: { type: Object, required: true },
})

const emit = defineEmits(["update:modelValue", "created"])

const SLOTS_METHOD = "phamos.mailcow_integration.availability.next_free_slot.free_slots_for_day"

const subject = ref("")
const day = ref("")
const durationMinutes = ref("60")
const startsOn = ref("")
const endsOn = ref("")
const agenda = ref("")
const selectedModules = ref([])

const slots = ref([])
const slotsFetched = ref(false)
const loadingSlots = ref(false)
const slotsError = ref("")
const saving = ref(false)
const error = ref("")

const durationOptions = [15, 30, 45, 60, 90, 120].map((m) => ({ label: `${m} minutes`, value: String(m) }))

const defaultSubject = computed(
	() => `Demo — ${props.lead?.company_name || props.lead?.lead_name || props.lead?.name || ""}`.trim()
)

watch(
	() => props.modelValue,
	(open) => {
		if (!open) return
		subject.value = defaultSubject.value
		day.value = new Date().toISOString().slice(0, 10)
		durationMinutes.value = "60"
		startsOn.value = ""
		endsOn.value = ""
		agenda.value = ""
		selectedModules.value = []
		slots.value = []
		slotsFetched.value = false
		slotsError.value = ""
		error.value = ""
	}
)

function toggleModule(key) {
	const index = selectedModules.value.indexOf(key)
	if (index === -1) selectedModules.value.push(key)
	else selectedModules.value.splice(index, 1)
}

async function fetchSlots() {
	slotsError.value = ""
	loadingSlots.value = true
	try {
		slots.value =
			(await call(SLOTS_METHOD, {
				day: day.value,
				duration_minutes: Number(durationMinutes.value),
			})) || []
		slotsFetched.value = true
	} catch (e) {
		// Calendar lookups fail loudly (missing DAV password, unreachable SOGo);
		// surface it here rather than looking like a day with no free time.
		slots.value = []
		slotsError.value = e?.messages?.[0] || e?.message || "Could not load free slots"
	} finally {
		loadingSlots.value = false
	}
}

/** Slots come back as naive local 'YYYY-MM-DD HH:mm:ss'; the inputs want a T. */
function toInputValue(value) {
	return (value || "").replace(" ", "T").slice(0, 16)
}

function selectSlot(slot) {
	startsOn.value = toInputValue(slot.start_local)
	endsOn.value = toInputValue(slot.end_local)
}

/** ...and the backend wants the space-separated form back. */
function toApiValue(value) {
	if (!value) return null
	return `${value.replace("T", " ")}:00`.slice(0, 19)
}

async function submit() {
	error.value = ""
	if (!subject.value.trim()) {
		error.value = "Subject is required"
		return
	}

	const modules = DEMO_MODULES.filter((m) => selectedModules.value.includes(m.key)).map((m) => m.label)
	const agendaText = [agenda.value.trim(), modules.length ? `Modules: ${modules.join(", ")}` : ""]
		.filter(Boolean)
		.join("\n\n")

	saving.value = true
	try {
		const demo = await call("phamos.api.sales_demos.create_demo", {
			lead: props.lead.name,
			subject: subject.value.trim(),
			starts_on: toApiValue(startsOn.value),
			ends_on: toApiValue(endsOn.value),
			agenda: agendaText || null,
		})
		emit("created", demo)
		emit("update:modelValue", false)
	} catch (e) {
		error.value = e?.messages?.[0] || e?.message || "Could not create demo"
	} finally {
		saving.value = false
	}
}
</script>
