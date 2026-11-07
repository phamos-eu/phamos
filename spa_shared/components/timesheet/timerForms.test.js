// Run with `yarn test:spa`. The timer dialogs check their minutes in `submit()`; the browser's own
// form check must stay out of the way, or `step` on a number field rejects valid input such as
// 40 expected minutes (#1806).
import fs from "fs"
import path from "path"

// Only the dialogs with a minutes field; Stop timer keeps the browser check on its End date.
const DIALOGS = ["StartTimerDialog.vue", "PauseDialog.vue"]

describe("timer dialog forms", () => {
	it.each(DIALOGS)("%s leaves validation to submit()", (file) => {
		const source = fs.readFileSync(path.resolve(__dirname, file), "utf8")
		const forms = source.match(/<form\b[^>]*>/g) || []
		expect(forms.length).toBeGreaterThan(0)
		for (const tag of forms) expect(tag).toMatch(/\bnovalidate\b/)
	})
})
