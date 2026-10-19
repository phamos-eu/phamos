<template>
	<div v-if="uploads.length" class="border-b border-outline-gray-2 bg-surface-gray-1 px-5 py-2 text-sm">
		<div class="mb-1 flex items-center justify-between">
			<span class="font-medium text-ink-gray-8">
				{{ running ? `Uploading ${running} of ${uploads.length}…` : "Upload finished" }}
			</span>
			<button v-if="!running" type="button" class="text-xs text-ink-gray-5 hover:text-ink-gray-8" @click="emit('clear')">
				Clear
			</button>
		</div>
		<ul class="space-y-1">
			<li v-for="upload in uploads" :key="upload.id" class="flex flex-wrap items-center gap-x-2 gap-y-1">
				<span class="max-w-xs truncate text-ink-gray-7" :title="upload.filename">{{ upload.filename }}</span>
				<span v-if="upload.state === 'uploading'" class="text-ink-gray-5">uploading…</span>
				<span v-else-if="upload.state === 'error'" class="text-ink-red-4">{{ upload.error }}</span>
				<template v-for="(result, index) in upload.results" :key="index">
					<button
						v-if="result.receipt"
						type="button"
						class="rounded bg-surface-green-2 px-1.5 py-0.5 text-xs text-ink-green-3 hover:underline"
						@click="emit('open', result.receipt)"
					>
						{{ result.receipt }} created
					</button>
					<span v-else-if="result.duplicate_of" class="inline-flex items-center gap-1 text-xs text-ink-amber-3">
						already on
						<button type="button" class="underline" @click="emit('open', result.duplicate_of)">{{ result.duplicate_of }}</button>
						<button type="button" class="rounded border border-outline-gray-2 px-1.5 py-0.5 text-ink-gray-7" @click="emit('force', upload)">
							Create anyway
						</button>
					</span>
				</template>
			</li>
		</ul>
	</div>
</template>

<script setup>
import { computed } from "vue"

const props = defineProps({
	uploads: { type: Array, default: () => [] },
})
const emit = defineEmits(["open", "force", "clear"])

const running = computed(() => props.uploads.filter((u) => u.state === "uploading").length)
</script>
