frappe.ready(function () {
	var event_name = new URLSearchParams(window.location.search).get("event");
	if (!event_name) return;

	// The "Submit another response" button is rendered on page load inside
	// the hidden success div — fix its href before the user ever sees it.
	var newBtn = document.querySelector(".new-btn");
	if (newBtn) {
		newBtn.href = "/event-registration/new?event=" + encodeURIComponent(event_name);
	}
});
