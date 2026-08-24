<template>
	<div>
		<div class="mb-2 text-xs font-medium uppercase tracking-wide text-gray-500 dark:text-gray-400">
			Future hours (next 3 months)
		</div>
		<div class="grid gap-3 sm:grid-cols-3">
			<div v-for="row in localPredictions" :key="row.month_and_year">
				<label class="mb-1 block text-xs text-gray-600 dark:text-gray-400">{{ row.month_and_year }}</label>
				<input
					v-model.number="row.prediction"
					type="number"
					min="0"
					step="1"
					class="w-full rounded-md border border-gray-300 bg-white px-3 py-2 text-sm dark:border-gray-600 dark:bg-gray-800 dark:text-gray-200"
					@input="emitChange"
				/>
			</div>
		</div>
	</div>
</template>

<script setup>
import { ref, watch } from "vue"

const props = defineProps({
	modelValue: {
		type: Array,
		default: () => [],
	},
})

const emit = defineEmits(["update:modelValue"])

const localPredictions = ref([])

watch(
	() => props.modelValue,
	(value) => {
		localPredictions.value = (value || []).map((row) => ({ ...row }))
	},
	{ immediate: true, deep: true }
)

function emitChange() {
	emit(
		"update:modelValue",
		localPredictions.value.map((row) => ({
			month_and_year: row.month_and_year,
			prediction: Number(row.prediction) || 0,
		}))
	)
}
</script>
