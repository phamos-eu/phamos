import { createApp } from "vue";
import App from "./App.vue";

class DevActionPanel {
	constructor({ page, wrapper }) {
		this.$wrapper = $(wrapper);
		this.page = page;
		this.init();
	}

	init() {
		this.setup_page_actions();
		this.setup_app();
	}

	setup_page_actions() {
		this.page.set_title(__("Developer Action Panel"));
		this.page.set_indicator(__("Active"), "green");
	}

	setup_app() {
		let app = createApp(App);
		this.$dev_action_panel = app.mount(this.$wrapper.get(0));
	}
}

frappe.provide("frappe.ui");
frappe.ui.DevActionPanel = DevActionPanel;
export default DevActionPanel;
