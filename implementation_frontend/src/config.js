// Implementation Cockpit (#1670): scoped to one Implementation at a time, chosen in the sidebar
// picker. Customers and internal users use the same cockpit; the API decides what each may see.
export default {
	api: "phamos.api.implementation_cockpit",
	label: "Implementation Cockpit",
	slug: "implementation",
	basePath: "/implementation-cockpit",
	lastImplementationKey: "implementation-cockpit-last",
}
