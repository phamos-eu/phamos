// Whether the keyboard-shortcut overview is open (#1603): the "?" key and the Create menu's
// "Keyboard shortcuts" entry both open it.
import { reactive } from "vue"

export const shortcuts = reactive({ open: false })
