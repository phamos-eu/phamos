import { computed, reactive } from "vue"
import { createResource } from "frappe-ui"

export function sessionUser() {
	const cookies = new URLSearchParams(document.cookie.split("; ").join("&"))
	let user = cookies.get("user_id")
	if (user === "Guest") user = null
	return user
}

export const session = reactive({
	user: sessionUser(),
	isLoggedIn: computed(() => !!session.user),
	fullName: computed(
		() => window.frappe?.boot?.user?.full_name || session.user || ""
	),
	logout: createResource({
		url: "logout",
		onSuccess() {
			session.user = null
			window.location.href = "/login"
		},
	}),
})
