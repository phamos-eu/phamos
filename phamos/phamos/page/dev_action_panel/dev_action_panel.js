frappe.pages["dev-action-panel"].on_page_load = function (wrapper) {
	frappe.ui.make_app_page({
		parent: wrapper,
		title: __("Developer Action Panel"),
		single_column: true,
	});

	load_desk_page(wrapper);   
};

frappe.pages["dev-action-panel"].on_page_show = function (wrapper) {
	frappe.dev_action_panel?.refresh?.();   
};

function load_desk_page(wrapper) {
	let $parent = $(wrapper).find(".layout-main-section");
	$parent.empty();

	frappe.require("dev_action_panel.bundle.js").then(() => {
		frappe.dev_action_panel = new frappe.ui.DevActionPanel({
			wrapper: $parent,
			page: wrapper.page,
		});
	});
}