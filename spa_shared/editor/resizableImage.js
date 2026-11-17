// The cockpits' image node for rich text (#1918): frappe-ui's image, plus a stored `width` and a
// handle to resize it. Registered after frappe-ui's own node of the same name, so this schema
// and node view win; its paste/drop plugin and input rule stay with the original (not repeated
// here, or a pasted image would arrive twice).

// frappe-ui has no public export for its image node; this path is from frappe-ui 0.1.105. After a
// frappe-ui upgrade, check that it still exists and that paste/drop still add images once.
import FrappeImage from "frappe-ui/src/components/TextEditor/image-extension"
import { clampImageWidth, parseImageWidth } from "@spa/utils/imageSize.js"
import { __ } from "@spa/utils/i18n.js"

export const ResizableImage = FrappeImage.extend({
	addAttributes() {
		return {
			...this.parent?.(),
			width: {
				default: null,
				// a width set in Desk (attribute or inline style) survives a save in the cockpit
				parseHTML: (el) => parseImageWidth({ widthAttr: el.getAttribute("width"), styleWidth: el.style?.width }),
				renderHTML: (attrs) => (attrs.width ? { width: String(attrs.width) } : {}),
			},
		}
	},

	addProseMirrorPlugins() {
		return []
	},

	addInputRules() {
		return []
	},

	addNodeView() {
		return ({ node, getPos, editor }) => {
			let current = node
			const dom = document.createElement("div")
			dom.className = "phamos-image"
			const img = document.createElement("img")
			dom.appendChild(img)

			const handle = document.createElement("button")
			handle.type = "button"
			handle.className = "phamos-image-handle"
			handle.setAttribute("contenteditable", "false")
			handle.title = __("Drag to resize, or use the arrow keys")
			handle.setAttribute("aria-label", handle.title)
			dom.appendChild(handle)

			function render() {
				const { src, alt, title, width } = current.attrs
				img.src = src || ""
				if (alt) img.alt = alt
				else img.removeAttribute("alt")
				if (title) img.title = title
				else img.removeAttribute("title")
				if (width) img.setAttribute("width", String(width))
				else img.removeAttribute("width")
				handle.hidden = !editor.isEditable
			}
			render()

			function save(width) {
				const pos = typeof getPos === "function" ? getPos() : null
				if (pos == null) return
				editor.view.dispatch(editor.view.state.tr.setNodeMarkup(pos, undefined, { ...current.attrs, width }))
			}

			const room = () => dom.parentElement?.clientWidth || dom.clientWidth
			let start = null
			handle.addEventListener("pointerdown", (event) => {
				if (event.button !== 0 || !editor.isEditable) return
				event.preventDefault()
				event.stopPropagation()
				start = { x: event.clientX, width: img.getBoundingClientRect().width }
				handle.setPointerCapture(event.pointerId)
				dom.classList.add("is-resizing")
			})
			handle.addEventListener("pointermove", (event) => {
				if (!start) return
				if ((event.buttons & 1) !== 1) return finish()
				img.setAttribute("width", String(clampImageWidth(start.width + event.clientX - start.x, room())))
			})
			function finish() {
				if (!start) return
				start = null
				dom.classList.remove("is-resizing")
				const width = Number(img.getAttribute("width")) || null
				if (width !== current.attrs.width) save(width)
			}
			handle.addEventListener("pointerup", finish)
			handle.addEventListener("pointercancel", finish)
			handle.addEventListener("lostpointercapture", finish)
			// keyboard: ±10% of the current width
			handle.addEventListener("keydown", (event) => {
				if (event.key !== "ArrowLeft" && event.key !== "ArrowRight") return
				event.preventDefault()
				event.stopPropagation()
				const now = img.getBoundingClientRect().width
				const step = Math.max(10, Math.round(now * 0.1)) * (event.key === "ArrowRight" ? 1 : -1)
				save(clampImageWidth(now + step, room()))
			})

			return {
				dom,
				update(updated) {
					if (updated.type !== current.type) return false
					current = updated
					render()
					return true
				},
				selectNode() {
					dom.classList.add("is-selected")
				},
				deselectNode() {
					dom.classList.remove("is-selected")
				},
				// the handle and the live width while dragging are ours, not ProseMirror's
				ignoreMutation: () => true,
				stopEvent: (event) => event.target === handle,
			}
		}
	},
})
