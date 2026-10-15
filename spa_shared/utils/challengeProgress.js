// Copy and progress for self-set ToDo challenges (#1557). Feedback informs, never scolds:
// no "failed", no "streak lost", nothing resets (enforced by challengeProgress.test.js).
import { pluralize } from "./dashboardFormat.js"

const COUNTED = new Set(["Met", "Joker", "Repaired"])

export function ringFraction(challenge) {
	const total = challenge?.working_days || 0
	return total ? Math.min((challenge.counted_days || 0) / total, 1) : 0
}

// Small-area rule: count up while less than half is done, count down afterwards.
export function progressText(challenge) {
	const total = challenge.working_days
	const done = challenge.counted_days
	if (done >= total) return "All days done"
	if (done * 2 < total) return `${done} of ${pluralize(total, "day", "days")} done`
	return `${pluralize(total - done, "day", "days")} to go`
}

export function todayText(challenge, formatDate = (d) => d) {
	if (challenge.not_started) return `Starts ${formatDate(challenge.start_date)}.`
	const today = challenge.today || {}
	if (!today.in_schedule) return "Day off today. It does not count either way."
	if (today.remaining <= 0) return "Today counts. Nice work."
	return `Today: ${today.closes} of ${today.target} closed, ${today.remaining} to go.`
}

export function repairText(challenge) {
	const repair = challenge.today?.repair
	if (!repair || challenge.today.closes >= repair.closes_needed) return ""
	return `Close ${repair.closes_needed} today and the day before counts too.`
}

export function welcomeText(challenge) {
	return challenge.welcome_back ? "Welcome back. Today is a fresh day." : ""
}

export function jokerText(challenge) {
	const left = challenge.jokers_left
	if (left > 0) return `${pluralize(left, "joker", "jokers")} in reserve for a day that slips.`
	return "No jokers left. A day that slips can still be made up on the next one."
}

export function streakText(challenge) {
	return challenge.current_streak >= 2 ? `${challenge.current_streak} days in a row` : ""
}

export function finishedText(challenge) {
	const done = challenge.counted_days
	const total = challenge.working_days
	if (challenge.status === "Completed") return `Completed: all ${total} days counted.`
	return `Ended with ${done} of ${pluralize(total, "day", "days")} counted. Each of them is real progress.`
}

export function dayState(result) {
	if (result === "Met") return { label: "counted", tone: "met" }
	if (result === "Repaired") return { label: "made up the next day", tone: "met" }
	if (result === "Joker") return { label: "covered by a joker", tone: "joker" }
	if (result === "Missed") return { label: "not counted", tone: "open" }
	if (result === "Today") return { label: "today", tone: "today" }
	return { label: "upcoming", tone: "upcoming" }
}

export function isCounted(result) {
	return COUNTED.has(result)
}

export function suggestionText(suggestion) {
	if (!suggestion) return ""
	const base = suggestion.baseline_per_day
	if (!base) return "On most working days you closed none so far. Start small: one a day is a real habit."
	return `You close about ${base} a day. ${suggestion.suggested} is a good stretch.`
}
