frappe.pages["sales-action-panel"].on_page_load = function (wrapper) {
	frappe.ui.make_app_page({
		parent: wrapper,
		title: __("Sales Action Panel"),
		single_column: true,
	});

	load_desk_page(wrapper);
};

frappe.pages["sales-action-panel"].on_page_show = function (wrapper) {
	frappe.sales_action_panel?.refresh?.();
};

function load_desk_page(wrapper) {
	let $parent = $(wrapper).find(".layout-main-section");
	$parent.empty();

	frappe.require("sales_action_panel.bundle.js").then(() => {
		frappe.sales_action_panel = new frappe.ui.SalesActionPanel({
			wrapper: $parent,
			page: wrapper.page,
		});
	});
}
