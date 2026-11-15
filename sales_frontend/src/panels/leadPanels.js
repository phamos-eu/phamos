// The Lead page's panels (#1913): the sales cockpit owns them and adds them through config.js
// (`panels.Lead.add`), next to the shared Checklists panel. The Lead's master data, conversation
// and status are host panels LeadDetail.vue teleports into; Notes is a panel of its own.

import { markRaw } from "vue"
import HostPanel from "@spa/panels/HostPanel.vue"
import { GUTTER, normalize } from "@spa/panels/tiling.js"
import LeadNotesPanel from "./LeadNotesPanel.vue"

const host = (id, extra) => ({
	id,
	doctypes: ["Lead"],
	component: markRaw(HostPanel),
	props: () => ({ hostId: id }),
	persistent: true,
	bare: true,
	popout: false,
	...extra,
})

export const LEAD_PANELS = [
	host("lead-details", { title: "Details", icon: "briefcase", minWidth: 280, minHeight: 120 }),
	host("lead-timeline", { title: "Conversation", icon: "message-square", minWidth: 360, minHeight: 240 }),
	host("lead-status", { title: "Status", icon: "flag", minWidth: 240, minHeight: 240 }),
	{
		id: "lead-notes",
		title: "Notes",
		icon: "edit-3",
		doctypes: ["Lead"],
		component: markRaw(LeadNotesPanel),
		place: { near: "lead-status", side: "bottom" },
	},
]

// Today's Lead page: details over the conversation | status, checklists and notes on the right.
export const LEAD_LAYOUT = {
	tree(width) {
		const side = 320
		const rest = Math.max(360, width - side - GUTTER)
		return {
			split: "row",
			sizes: normalize([rest, side]),
			children: [
				{ split: "column", sizes: [0.3, 0.7], children: [{ panel: "lead-details" }, { panel: "lead-timeline" }] },
				{
					split: "column",
					sizes: [0.45, 0.3, 0.25],
					children: [{ panel: "lead-status" }, { panel: "checklists" }, { panel: "lead-notes" }],
				},
			],
		}
	},
	opened: ["lead-notes", "checklists", "lead-details", "lead-status", "lead-timeline"],
}
