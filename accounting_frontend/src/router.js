import { createSpaRouter } from "@spa/router.js"
import spaConfig from "./config"
import ReceiptsInbox from "./views/ReceiptsInbox.vue"

export default createSpaRouter({
	config: spaConfig,
	rootRedirect: "/receipts",
	routes: [
		{
			path: "/receipts",
			name: "Receipts",
			component: ReceiptsInbox,
		},
		{
			path: "/receipts/:name",
			name: "ReceiptDetail",
			component: ReceiptsInbox,
			props: true,
		},
	],
})
