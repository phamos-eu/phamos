import "./main.css"

import { createApp } from "vue"
import {
	Button,
	Dialog,
	ErrorMessage,
	FeatherIcon,
	FormControl,
	frappeRequest,
	FrappeUI,
	setConfig,
	toast,
} from "frappe-ui"
import App from "./App.vue"
import router from "./router"
import { session } from "./session"

setConfig("resourceFetcher", frappeRequest)

const app = createApp(App)
app.use(FrappeUI)
app.use(router)

app.component("Button", Button)
app.component("Dialog", Dialog)
app.component("ErrorMessage", ErrorMessage)
app.component("FeatherIcon", FeatherIcon)
app.component("FormControl", FormControl)

app.provide("$session", session)
app.config.globalProperties.$toast = toast

async function mountApp() {
	if (import.meta.env.DEV) {
		const values = await frappeRequest({
			url: "/api/method/phamos.www.hr_spa.get_context_for_dev",
		})
		if (!window.frappe) window.frappe = {}
		window.frappe.boot = values
		if (!window.csrf_token && values?.csrf_token) {
			window.csrf_token = values.csrf_token
		}
	}

	app.mount("#app")
}

mountApp()
