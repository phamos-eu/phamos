/**
 * Pure helpers for StageSteps.vue, the chevron step bar (#1773). It is the cockpit twin of the
 * ticket order's step bar on the event page (`.wp-steps` in web_profile.bundle.css).
 * DOM-free so they can be unit-tested (stageSteps.test.js).
 */

/** Index of `value` in `steps` ([{ value, label }]), -1 when it is not on the path. */
export function stepIndex(steps, value) {
	return (steps || []).findIndex((step) => step.value === value)
}

/** "done" before the current step, "current", or "upcoming"; all "upcoming" off the path. */
export function stepState(index, currentIndex) {
	if (currentIndex < 0) return "upcoming"
	if (index < currentIndex) return "done"
	if (index === currentIndex) return "current"
	return "upcoming"
}

/** Numbers for the "Growing, step 5 of 7" tooltip; null when the value is off the path. */
export function progress(steps, value) {
	const index = stepIndex(steps, value)
	if (index < 0) return null
	return { label: steps[index].label, step: index + 1, total: steps.length }
}
