import { createSpaRouter } from "@spa/router.js"
import spaConfig from "./config"
import MonthlyImplementationSummariesInbox from "./views/MonthlyImplementationSummariesInbox.vue"
import PaymentsCalendar from "./views/PaymentsCalendar.vue"
import ReceiptReview from "./views/ReceiptReview.vue"
import ReceiptsList from "./views/ReceiptsList.vue"
import ReceiptsQueue from "./views/ReceiptsQueue.vue"
import ReceiptStatistics from "./views/ReceiptStatistics.vue"

export default createSpaRouter({
	config: spaConfig,
	rootRedirect: "/receipts",
	routes: [
		{
			path: "/receipts",
			name: "Receipts",
			component: ReceiptsQueue,
		},
		{
			path: "/receipts/all",
			name: "ReceiptsAll",
			component: ReceiptsList,
		},
		{
			path: "/receipts/calendar",
			name: "PaymentsCalendar",
			component: PaymentsCalendar,
		},
		{
			path: "/statistics",
			name: "ReceiptStatistics",
			component: ReceiptStatistics,
		},
		{
			path: "/receipts/:name",
			name: "ReceiptDetail",
			component: ReceiptReview,
			props: true,
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
