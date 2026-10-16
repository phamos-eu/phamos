// Short success / error messages for the cockpits. frappe-ui 0.1.105 only has `toast(options)`;
// `toast.success()` / `toast.error()` do not exist there and threw. Needs <Toasts /> mounted
// once, which CockpitShell does.
import { toast } from "frappe-ui"

const TIMEOUT_SECONDS = 4
// Bottom right, so a message never covers the top bar it reports on.
const POSITION = "bottom-right"

export function notifySuccess(title, text = "") {
	return toast({ title, text, icon: "check", iconClasses: "text-ink-green-3", timeout: TIMEOUT_SECONDS, position: POSITION })
}

export function notifyError(title, text = "") {
	return toast({ title, text, icon: "alert-circle", iconClasses: "text-ink-red-4", timeout: TIMEOUT_SECONDS + 2, position: POSITION })
}

export const notify = { success: notifySuccess, error: notifyError }
