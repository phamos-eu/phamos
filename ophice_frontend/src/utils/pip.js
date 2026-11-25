// Document Picture-in-Picture (#2074, #2075): a small window that stays on top of everything
// (Chrome, Edge, newer Firefox; not Safari). Parts of Ophice move into it with a Teleport.

export const canFloat = typeof window !== "undefined" && "documentPictureInPicture" in window

/**
 * Open a floating window with this page's styles. Resolves to its <body> (the Teleport target),
 * or null when the browser refused. `onClose` runs when the window goes away.
 */
export async function openFloatingWindow({ width, height, onClose }) {
	let pip
	try {
		pip = await window.documentPictureInPicture.requestWindow({ width, height })
	} catch {
		return null
	}
	for (const sheet of [...document.styleSheets]) {
		try {
			const style = pip.document.createElement("style")
			style.textContent = [...sheet.cssRules].map((rule) => rule.cssText).join("\n")
			pip.document.head.appendChild(style)
		} catch {
			if (sheet.href) {
				const link = pip.document.createElement("link")
				link.rel = "stylesheet"
				link.href = sheet.href
				pip.document.head.appendChild(link)
			}
		}
	}
	pip.document.body.className = document.body.className
	pip.document.documentElement.dataset.theme = document.documentElement.dataset.theme || ""
	Object.assign(pip.document.body.style, { margin: "0", display: "flex", flexDirection: "column", height: "100vh" })
	pip.addEventListener("pagehide", () => onClose?.())
	return pip.document.body
}
