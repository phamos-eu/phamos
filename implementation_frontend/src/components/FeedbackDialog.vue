<template>
	<!-- Feedback on one timesheet (#1685), given once like on /timesheet; then it is under review. -->
	<Dialog
		:options="{
			title: readOnly ? __('Feedback under review') : __('Feedback on {0}', [timesheet?.name || '']),
			size: 'lg',
			actions: readOnly
				? [{ label: __('Close'), variant: 'subtle', onClick: close }]
				: [
						{ label: __('Cancel'), variant: 'subtle', onClick: close },
						{ label: __('Send feedback'), variant: 'solid', loading: saving, onClick: submit },
					],
		}"
		:model-value="modelValue"
		@update:model-value="emit('update:modelValue', $event)"
	>
		<template #body-content>
			<div class="flex flex-col gap-4">
				<p class="text-sm text-ink-gray-6">
					{{ timesheet?.employee_name }} · {{ timesheet?.start_date }} · {{ __("{0} h", [timesheet?.total_hours]) }}
				</p>
				<div>
					<div class="mb-1.5 text-xs font-medium text-ink-gray-7">{{ __("Rating") }}</div>
					<div class="flex gap-1" role="radiogroup" :aria-label="__('Rating')">
						<button
							v-for="n in 5"
							:key="n"
							type="button"
							role="radio"
							:aria-checked="rating === n"
							:aria-label="__('{0} of 5', [n])"
							:disabled="readOnly"
							class="rounded p-1 text-ink-gray-4 hover:text-ink-amber-3 disabled:cursor-default disabled:hover:text-ink-gray-4"
							:class="n <= rating ? '!text-ink-amber-3' : ''"
							@click="rating = n"
						>
							<FeatherIcon name="star" class="h-5 w-5" :class="n <= rating ? 'fill-current' : ''" />
						</button>
					</div>
				</div>
				<FormControl
					v-model="comment"
					type="textarea"
					:label="__('Comment')"
					:placeholder="__('What should we check or adjust?')"
					:disabled="readOnly"
					:rows="4"
				/>
				<ErrorMessage :message="error" />
			</div>
		</template>
	</Dialog>
</template>

<script setup>
import { computed, ref, watch } from "vue"
import { toast } from "frappe-ui"
import { __ } from "@spa/utils/i18n.js"
import { giveFeedback } from "../timesheetStore.js"

const props = defineProps({
	modelValue: { type: Boolean, default: false },
	timesheet: { type: Object, default: null },
})
const emit = defineEmits(["update:modelValue", "saved"])

const rating = ref(0)
const comment = ref("")
const error = ref("")
const saving = ref(false)
const readOnly = computed(() => (props.timesheet?.custom_rating || 0) > 0)

watch(
	() => [props.modelValue, props.timesheet?.name],
	() => {
		rating.value = props.timesheet?.custom_rating || 0
		comment.value = props.timesheet?.customer_comment || ""
		error.value = ""
	},
	{ immediate: true }
)

function close() {
	emit("update:modelValue", false)
}

async function submit() {
	if (rating.value < 1) {
		error.value = __("Please choose a rating.")
		return
	}
	saving.value = true
	error.value = ""
	try {
		await giveFeedback(props.timesheet.name, rating.value, comment.value)
		toast.success(__("Thank you. We will review your feedback."))
		emit("saved")
		close()
	} catch (e) {
		error.value = e?.messages?.[0] || e?.message || __("Could not send the feedback")
	} finally {
		saving.value = false
	}
}
</script>
