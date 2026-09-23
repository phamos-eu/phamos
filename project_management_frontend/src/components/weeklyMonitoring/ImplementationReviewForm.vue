<template>
	<div class="grid gap-4 md:grid-cols-2">
		<div>
			<label class="mb-1 block text-xs font-medium text-gray-600 dark:text-gray-400">Maturity Level</label>
			<select
				:value="modelValue.maturity_level"
				class="w-full rounded-md border border-gray-300 bg-white px-3 py-2 text-sm dark:border-gray-600 dark:bg-gray-800 dark:text-gray-200"
				@change="update('maturity_level', $event.target.value)"
			>
				<option value="">—</option>
				<option v-for="opt in options.maturity_level || []" :key="opt" :value="opt">{{ opt }}</option>
			</select>
		</div>

		<div>
			<label class="mb-1 block text-xs font-medium text-gray-600 dark:text-gray-400">Implementation Status (Forecast)</label>
			<select
				:value="modelValue.forecast"
				class="w-full rounded-md border border-gray-300 bg-white px-3 py-2 text-sm dark:border-gray-600 dark:bg-gray-800 dark:text-gray-200"
				@change="update('forecast', $event.target.value)"
			>
				<option value="">—</option>
				<option v-for="opt in options.forecast || []" :key="opt" :value="opt">{{ opt }}</option>
			</select>
		</div>

		<div>
			<label class="mb-1 block text-xs font-medium text-gray-600 dark:text-gray-400">Trend</label>
			<select
				:value="modelValue.trend"
				class="w-full rounded-md border border-gray-300 bg-white px-3 py-2 text-sm dark:border-gray-600 dark:bg-gray-800 dark:text-gray-200"
				@change="update('trend', $event.target.value)"
			>
				<option value="">—</option>
				<option v-for="opt in options.trend || []" :key="opt" :value="opt">{{ opt }}</option>
			</select>
		</div>

		<div class="md:col-span-2">
			<label class="mb-1 block text-xs font-medium text-gray-600 dark:text-gray-400">Status Statement</label>
			<textarea
				:value="modelValue.status_statement"
				rows="4"
				class="w-full rounded-md border border-gray-300 bg-white px-3 py-2 text-sm dark:border-gray-600 dark:bg-gray-800 dark:text-gray-200"
				placeholder="Meeting notes, risks, and next steps…"
				@input="update('status_statement', $event.target.value)"
			/>
		</div>
	</div>
</template>

<script setup>
const props = defineProps({
	modelValue: {
		type: Object,
		default: () => ({
			maturity_level: "",
			forecast: "",
			trend: "",
			status_statement: "",
		}),
	},
	options: {
		type: Object,
		default: () => ({ maturity_level: [], forecast: [], trend: [] }),
	},
})

const emit = defineEmits(["update:modelValue"])

function update(field, value) {
	emit("update:modelValue", { ...props.modelValue, [field]: value })
}
</script>
