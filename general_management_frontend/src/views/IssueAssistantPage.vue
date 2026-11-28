<template>
	<div class="h-full overflow-y-auto p-5">
		<p class="mb-4 text-sm text-ink-gray-6">
			{{ __("What the Issue Assistant learns from your corrections. A suggested rule applies only after a trainer uses it.") }}
		</p>
		<AiLearningView
			doctype="Issue"
			:field-labels="FIELD_LABELS"
			:group-labels="GROUP_LABELS"
			:party-label="__('Customer')"
			:reference-label="__('Issue')"
			:reference-to="(name) => `/app/issue/${encodeURIComponent(name)}`"
			:empty-text="__('No suggestions. When someone changes what the assistant set on an Issue, a rule is suggested here.')"
		/>
	</div>
</template>

<script setup>
// The Issue Assistant's learning (#2226): the shared view, for trainers and System Managers.
import AiLearningView from "@spa/components/AiLearningView.vue"
import { __ } from "@spa/utils/i18n.js"

const FIELD_LABELS = {
	customer: __("Customer"),
	contact: __("Contact"),
	custom_implementation: __("Implementation"),
	project: __("Project"),
	issue_type: __("Issue Type"),
	priority: __("Priority"),
	person: __("Person"),
}
const GROUP_LABELS = {
	identify: __("Identify (sender and links)"),
	classify: __("Classify (type and priority)"),
	person: __("Suggested person"),
}
</script>
