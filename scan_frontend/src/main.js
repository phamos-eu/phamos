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
import { IonicVue } from "@ionic/vue"
import App from "./App.vue"
import router from "./router"
import { session } from "./session"
import getIonicConfig from "./utils/ionicConfig"

setConfig("resourceFetcher", frappeRequest)

const app = createApp(App)
app.use(FrappeUI)
app.use(router)
app.use(IonicVue, getIonicConfig())

app.component("Button", Button)
app.component("Dialog", Dialog)
app.component("ErrorMessage", ErrorMessage)
app.component("FeatherIcon", FeatherIcon)
app.component("FormControl", FormControl)

app.provide("$session", session)
app.provide("$toast", toast)

async function mountApp() {
	if (import.meta.env.DEV) {
		const values = await frappeRequest({
			url: "/api/method/phamos.www.scan.get_context_for_dev",
		})
		if (!window.frappe) window.frappe = {}
		window.frappe.boot = values
		if (!window.csrf_token && values?.csrf_token) {
			window.csrf_token = values.csrf_token
		}
	}

	await router.isReady()
	app.mount("#app")
}

mountApp()
