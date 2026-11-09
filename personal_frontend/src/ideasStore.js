// Ideas (#1773): my ideas for the list, the stage options from the server, and small helpers the
// list and the Idea page share. The realtime listener lives in the views (it needs a component).
import { reactive } from "vue"
import { call } from "frappe-ui"
import { __ } from "@spa/utils/i18n.js"
import spaConfig from "./config"

export const ideas = reactive({ rows: [], options: null, loaded: false, error: "", showClosed: false })

// Ideas handed in for a vote (#1842): everyone's, most votes first.
export const voteIdeas = reactive({ rows: [], loaded: false, error: "" })

let inflight = null
let optionsInflight = null
let voteInflight = null

export function loadIdeas() {
	if (!inflight) {
		inflight = call(`${spaConfig.api}.get_ideas`, { include_closed: ideas.showClosed ? 1 : 0 })
			.then((rows) => {
				ideas.rows = rows || []
				ideas.error = ""
			})
			.catch((e) => {
				ideas.error = e?.messages?.[0] || e?.message || __("Could not load your ideas")
			})
			.finally(() => {
				ideas.loaded = true
				inflight = null
			})
	}
	return inflight
}

export function loadIdeaOptions() {
	if (ideas.options) return Promise.resolve(ideas.options)
	if (!optionsInflight) {
		optionsInflight = call(`${spaConfig.api}.get_idea_options`)
			.then((options) => (ideas.options = options))
			.finally(() => (optionsInflight = null))
	}
	return optionsInflight
}

export function createIdea(title = null) {
	return call(`${spaConfig.api}.create_idea`, { title }).then((doc) => {
		applyIdea(doc)
		return doc
	})
}

/** Put a detail payload into the list without a reload. */
export function applyIdea(doc) {
	if (!doc?.name) return
	const index = ideas.rows.findIndex((row) => row.name === doc.name)
	const closed = (ideas.options?.closed_stages || ["Harvest", "Compost"]).includes(doc.stage)
	const row = {
		name: doc.name,
		title: doc.title,
		stage: doc.stage,
		summary: doc.summary,
		spawned_from: doc.spawned_from,
		spawned_from_title: doc.spawned_from_title,
		last_session_words: doc.last_session_words,
		vote_status: doc.vote_status,
		vote_count: doc.vote_count,
		children_count: (doc.children || []).length,
		age_days: doc.age_days,
		creation: doc.creation,
		modified: doc.modified,
	}
	if (closed && !ideas.showClosed) {
		if (index >= 0) ideas.rows.splice(index, 1)
		return
	}
	if (index >= 0) ideas.rows.splice(index, 1)
	ideas.rows.unshift(row)
}

/** The stage path for the stage bar: Seed … Harvest, translated, with the job as hint. Compost is not on it. */
export function stageSteps() {
	const stages = ideas.options?.stages || []
	const jobs = ideas.options?.jobs || {}
	return stages.filter((s) => s !== "Compost").map((s) => ({ value: s, label: __(s), hint: __(jobs[s] || "") }))
}

export function stageJob(stage) {
	return __(ideas.options?.jobs?.[stage] || "")
}

export function ageLabel(days) {
	const d = Number(days) || 0
	if (d <= 0) return __("Aged today")
	if (d === 1) return __("Aged 1 day")
	if (d < 28) return __("Aged {0} days", [d])
	const weeks = Math.floor(d / 7)
	if (weeks < 8) return __("Aged {0} weeks", [weeks])
	return __("Aged {0} months", [Math.max(2, Math.floor(d / 30))])
}

export function loadIdeasForVote() {
	if (!voteInflight) {
		voteInflight = call(`${spaConfig.api}.get_ideas_for_vote`)
			.then((rows) => {
				voteIdeas.rows = rows || []
				voteIdeas.error = ""
			})
			.catch((e) => {
				voteIdeas.error = e?.messages?.[0] || e?.message || __("Could not load the ideas up for vote")
			})
			.finally(() => {
				voteIdeas.loaded = true
				voteInflight = null
			})
	}
	return voteInflight
}

/** Toggle my vote on an idea; returns the server's {name, voted, vote_count} and updates the list. */
export function toggleVote(name) {
	return call(`${spaConfig.api}.vote_idea`, { name }).then((result) => {
		const row = voteIdeas.rows.find((r) => r.name === name)
		if (row) Object.assign(row, { voted: result.voted, vote_count: result.vote_count })
		return result
	})
}

/** Take my idea off the vote (#1842): it is private again and its votes are removed. */
export function withdrawFromVote(name) {
	return call(`${spaConfig.api}.withdraw_idea_from_vote`, { name }).then((doc) => {
		voteIdeas.rows = voteIdeas.rows.filter((r) => r.name !== name)
		applyIdea(doc)
		return doc
	})
}

// A function, not a constant: the text must stay a literal inside __() to be found for translation.
export const withdrawQuestion = () => __("Withdraw this idea from the vote? The votes so far are removed.")

export function voteLabel(count) {
	const n = Number(count) || 0
	return n === 1 ? __("1 vote") : __("{0} votes", [n])
}
