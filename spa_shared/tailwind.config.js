/** Prefer spa_shared/tailwind.shared.js + per-SPA preset import (frappe-ui resolves from SPA root). */
import frappeUIPreset from "frappe-ui/src/tailwind/preset"
import { makeConfig } from "./tailwind.shared.js"

export default makeConfig(frappeUIPreset)
