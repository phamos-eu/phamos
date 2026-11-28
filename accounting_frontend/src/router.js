import { createSpaRouter } from "@spa/router.js"
import spaConfig from "./config"
import MonthlyImplementationSummariesInbox from "./views/MonthlyImplementationSummariesInbox.vue"
import ReceiptsInbox from "./views/ReceiptsInbox.vue"
import Receivables from "./views/Receivables.vue"

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
		{
			path: "/receivables",
			name: "Receivables",
			component: Receivables,
		},
		{
			path: "/monthly-implementation-summaries",
			name: "MisList",
			component: MonthlyImplementationSummariesInbox,
		},
		{
			path: "/monthly-implementation-summaries/:name",
			name: "MisDetail",
			component: MonthlyImplementationSummariesInbox,
			props: true,
		},
	],
})
