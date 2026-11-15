// The panels every cockpit knows (#1910, #1915). A cockpit hides or adds panels per record type
// in its config.js: `panels: { Issue: { hide: ["checklists"], add: [...] } }`.
//
// A panel body gets `embedded: true` plus its props(ctx), and may emit `state` with
// { summary, hidden, badge, tone }: the rail's tooltip text, `hidden` to drop the panel (e.g. no
// permission), and the badge on its rail icon. Keep ids stable: users' layouts store them.

import { markRaw } from "vue"
import LinkedChecklistsSection from "@spa/components/LinkedChecklistsSection.vue"
import IssuePhriendReport from "@spa/components/IssuePhriendReport.vue"
import PhriendMark from "@spa/components/PhriendMark.vue"
import ChatDockHost from "./ChatDockHost.vue"
import HostPanel from "./HostPanel.vue"
import { typeLabel } from "@spa/utils/phriendReport.js"
import { definePanel } from "./registry.js"
import { GUTTER, normalize } from "./tiling.js"

// Record states in which no new checklist may be linked.
const CLOSED_STATES = ["Closed", "Completed", "Cancelled"]

// The Issue's description and properties: IssueDetail.vue teleports into these hosts.
export const description = definePanel({
	id: "description",
	title: "Description",
	icon: "align-left",
	doctypes: ["Issue"],
	component: markRaw(HostPanel),
	props: () => ({ hostId: "description" }),
	minWidth: 280,
	minHeight: 200,
	persistent: true,
	bare: true,
	popout: false,
})

export const properties = definePanel({
	id: "properties",
	title: "Properties",
	icon: "sliders",
	doctypes: ["Issue"],
	component: markRaw(HostPanel),
	props: () => ({ hostId: "properties" }),
	minWidth: 240,
	minHeight: 240,
	persistent: true,
	bare: true,
	popout: false,
})

// The record's Raven chat (#1911). Without Raven it reports itself hidden.
export const chat = definePanel({
	id: "chat",
	title: "Chat",
	icon: "message-circle",
	doctypes: ["Issue"],
	component: markRaw(ChatDockHost),
	// Raven keeps its desktop layout from 768px (#1613)
	minWidth: 768,
	minHeight: 320,
	persistent: true,
	bare: true,
	popout: false,
	props: ({ record }) => ({ recordName: record.name }),
})

export const phriendReport = definePanel({
	id: "phriend",
	title: "Phriend report",
	icon: markRaw(PhriendMark),
	doctypes: ["Issue"],
	component: markRaw(IssuePhriendReport),
	// only Issues reported through Phriend carry the block (get_issue → phamos/phriend/report.py)
	when: (issue) => !!issue.phriend,
	props: ({ record }) => ({ report: record.phriend }),
	summary: (issue) => typeLabel(issue.phriend?.type),
	place: { near: "checklists", side: "top" },
})

export const checklists = definePanel({
	id: "checklists",
	title: "Checklists",
	icon: "check-square",
	doctypes: ["Issue", "Lead"],
	component: markRaw(LinkedChecklistsSection),
	props: ({ doctype, record }) => ({
		document: doctype,
		referenceRecord: record.name,
		referenceTitle: record.subject || record.title || record.name,
		allowCreate: !CLOSED_STATES.includes(record.status),
	}),
	place: { near: "chat", side: "bottom" },
})

export const PANELS = [description, chat, phriendReport, checklists, properties]

/**
 * The layout a user starts with, per record type: a tree for the width the page has, and the
 * opening order (oldest first) that decides which panel closes first when the window is too
 * small (tiling.fit).
 */
export const DEFAULT_LAYOUTS = {
	// Today's Issue page: description | chat over Phriend report over checklists | properties
	Issue: {
		tree(width) {
			const side = 288
			const middle = 768
			const rest = Math.max(280, width - side - middle - 2 * GUTTER)
			return {
				split: "row",
				sizes: normalize([rest, middle, side]),
				children: [
					{ panel: "description" },
					{
						split: "column",
						sizes: [0.6, 0.15, 0.25],
						children: [{ panel: "chat" }, { panel: "phriend" }, { panel: "checklists" }],
					},
					{ panel: "properties" },
				],
			}
		},
		opened: ["phriend", "checklists", "properties", "chat", "description"],
	},
}
