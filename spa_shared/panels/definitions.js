// The panels every cockpit knows (#1910). A cockpit hides, reorders or adds panels per record
// type in its config.js: `panels: { Issue: { hide: ["checklists"], order: [...], add: [...] } }`.
//
// A panel body gets `embedded: true` plus its props(ctx), and may emit `state` with
// { summary, hidden } for the dock row: summary text, and hidden to drop the panel (e.g. no
// permission). Keep ids stable: users' layouts store them.

import { markRaw } from "vue"
import LinkedChecklistsSection from "@spa/components/LinkedChecklistsSection.vue"
import IssuePhriendReport from "@spa/components/IssuePhriendReport.vue"
import PhriendMark from "@spa/components/PhriendMark.vue"
import ChatDockHost from "./ChatDockHost.vue"
import { typeLabel } from "@spa/utils/phriendReport.js"
import { definePanel } from "./registry.js"

// Record states in which no new checklist may be linked.
const CLOSED_STATES = ["Closed", "Completed", "Cancelled"]

export const phriendReport = definePanel({
	id: "phriend",
	title: "Phriend report",
	icon: markRaw(PhriendMark),
	doctypes: ["Issue"],
	component: markRaw(IssuePhriendReport),
	order: 10,
	// only Issues reported through Phriend carry the block (get_issue → phamos/phriend/report.py)
	when: (issue) => !!issue.phriend,
	props: ({ record }) => ({ report: record.phriend }),
	summary: (issue) => typeLabel(issue.phriend?.type),
	defaultOpen: () => true,
})

export const checklists = definePanel({
	id: "checklists",
	title: "Checklists",
	icon: "check-square",
	doctypes: ["Issue"],
	component: markRaw(LinkedChecklistsSection),
	order: 20,
	props: ({ doctype, record }) => ({
		document: doctype,
		referenceRecord: record.name,
		referenceTitle: record.subject || record.title || record.name,
		allowCreate: !CLOSED_STATES.includes(record.status),
	}),
	defaultOpen: () => true,
})

// The record's Raven chat (#1911). First, so it fills the dock with the other rows below it.
// Below lg, or without Raven, it reports itself hidden and the top-bar button opens the overlay.
export const chat = definePanel({
	id: "chat",
	title: "Chat",
	icon: "message-circle",
	doctypes: ["Issue"],
	component: markRaw(ChatDockHost),
	order: 5,
	// Raven keeps its desktop layout from 768px (#1613); the dock is that wide only while expanded
	minWidth: 768,
	fill: true,
	persistent: true,
	popout: false,
	props: ({ record }) => ({ recordName: record.name }),
	defaultOpen: () => true,
})

export const PANELS = [chat, phriendReport, checklists]
