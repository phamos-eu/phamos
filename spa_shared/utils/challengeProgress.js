// Copy and progress for self-set ToDo challenges (#1557). Feedback informs, never scolds:
// no "failed", no "streak lost", nothing resets (enforced by challengeProgress.test.js).
import { __ } from "./i18n.js"

const COUNTED = new Set(["Met", "Joker", "Repaired"])

export function ringFraction(challenge) {
	const total = challenge?.working_days || 0
	return total ? Math.min((challenge.counted_days || 0) / total, 1) : 0
}

// Small-area rule: count up while less than half is done, count down afterwards.
export function progressText(challenge) {
	const total = challenge.working_days
	const done = challenge.counted_days
	if (done >= total) return __("All days done")
	if (done * 2 < total) return total === 1 ? __("{0} of 1 day done", [done]) : __("{0} of {1} days done", [done, total])
	return total - done === 1 ? __("1 day to go") : __("{0} days to go", [total - done])
}

export function todayText(challenge, formatDate = (d) => d) {
	if (challenge.not_started) return __("Starts {0}.", [formatDate(challenge.start_date)])
	const today = challenge.today || {}
	if (!today.in_schedule) return __("Day off today. It does not count either way.")
	if (today.met ?? today.remaining <= 0) return __("Today counts. Nice work.")
	if (challenge.split) {
		return __("Today: {0} of {1} planned, {2} of {3} spontaneous.", [today.planned, challenge.target_planned, today.spontaneous, challenge.target_spontaneous])
	}
	return __("Today: {0} of {1} closed, {2} to go.", [today.closes, today.target, today.remaining])
}

export function repairText(challenge) {
	const repair = challenge.today?.repair
	if (!repair || repair.reached) return ""
	const needs = repair.needs || {}
	if (challenge.split) {
		return __("Close {0} planned and {1} spontaneous today and the day before counts too.", [needs.planned, needs.spontaneous])
	}
	return __("Close {0} today and the day before counts too.", [needs.closes])
}

export function welcomeText(challenge) {
	return challenge.welcome_back ? __("Welcome back. Today is a fresh day.") : ""
}

export function jokerText(challenge) {
	const left = challenge.jokers_left
	if (left === 1) return __("1 joker in reserve for a day that slips.")
	if (left > 0) return __("{0} jokers in reserve for a day that slips.", [left])
	return __("No jokers left. A day that slips can still be made up on the next one.")
}

export function streakText(challenge) {
	return challenge.current_streak >= 2 ? __("{0} days in a row", [challenge.current_streak]) : ""
}

export function finishedText(challenge) {
	const done = challenge.counted_days
	const total = challenge.working_days
	if (challenge.status === "Completed") return __("Completed: all {0} days counted.", [total])
	return total === 1
		? __("Ended with {0} of 1 day counted. Each of them is real progress.", [done])
		: __("Ended with {0} of {1} days counted. Each of them is real progress.", [done, total])
}

export function dayState(result) {
	if (result === "Met") return { label: __("counted"), tone: "met" }
	if (result === "Repaired") return { label: __("made up the next day"), tone: "met" }
	if (result === "Joker") return { label: __("covered by a joker"), tone: "joker" }
	if (result === "Missed") return { label: __("not counted"), tone: "open" }
	if (result === "Today") return { label: __("today"), tone: "today" }
	return { label: __("upcoming"), tone: "upcoming" }
}

export function isCounted(result) {
	return COUNTED.has(result)
}

export function suggestionText(suggestion) {
	if (!suggestion) return ""
	if (suggestion.kind === "Planned and spontaneous") {
		if (!suggestion.baseline_per_day) return __("Plan your day in My Day first; then planned closes start to count.")
		return __("You close about {0} planned and {1} spontaneous a day.", [suggestion.baseline_planned, suggestion.baseline_spontaneous])
	}
	const base = suggestion.baseline_per_day
	if (!base) return __("On most working days you closed none so far. Start small: one a day is a real habit.")
	return __("You close about {0} a day. {1} is a good stretch.", [base, suggestion.suggested])
}
