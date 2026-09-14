import { nextTick } from "vue"

/**
 * frappe-ui's TextEditor renders its fixed-menu toolbar as plain <button> elements
 * right before the .ProseMirror content, so they become Tab stops even though they
 * aren't form fields. Users tabbing through a form only need to reach the editable
 * body, not every toolbar button, so drop the toolbar buttons out of the tab order.
 *
 * The editor mounts TipTap asynchronously (and may not exist in the DOM yet right
 * after a v-for adds a new row), so this retries for a short while.
 */
export async function skipTextEditorToolbarTabStops(scopeEl, { attempts = 20, interval = 20 } = {}) {
	for (let i = 0; i < attempts; i++) {
		await nextTick()
		scopeEl?.querySelectorAll?.(".ProseMirror").forEach((proseMirror) => {
			const editorRoot = proseMirror.closest(".relative.w-full") || proseMirror.parentElement
			// Mark editors we've already fixed so a later poll never re-scans (and
			// potentially detabs) buttons in something the user opened since, like
			// the toolbar's "Link" dialog.
			if (!editorRoot || editorRoot.dataset.toolbarTabStopsFixed) return
			editorRoot.querySelectorAll("button").forEach((button) => {
				if (!proseMirror.contains(button)) button.setAttribute("tabindex", "-1")
			})
			editorRoot.dataset.toolbarTabStopsFixed = "true"
		})
		await new Promise((resolve) => setTimeout(resolve, interval))
	}
}
