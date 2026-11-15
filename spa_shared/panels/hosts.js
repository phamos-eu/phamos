// Where record content that lives in another component lays itself (#1915). The Issue's
// description and properties stay in IssueDetail.vue, which owns the autosave, field locks and
// realtime of the Issue; their panels are only host elements, registered here, that IssueDetail
// teleports into. The chat does the same with #issue-chat-host (ChatDockHost.vue).
import { reactive } from "vue"

/** host id → element, while the host panel is mounted */
export const panelHosts = reactive({})

/**
 * panel id → the free slot in that panel's title bar, while its tile shows (#1917). A panel's
 * content can teleport small actions there instead of spending a row of its own (the chat's
 * "Open in Raven").
 */
export const panelTitleSlots = reactive({})
