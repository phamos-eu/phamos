frappe.ready(function () {
	var event_name = new URLSearchParams(window.location.search).get("event");
	if (!event_name) return;

	function isValidEmail(email) {
		return /^[A-Za-z0-9][A-Za-z0-9!#$%&'*+\/=?^_`{|}~-]*(?:\.[A-Za-z0-9!#$%&'*+\/=?^_`{|}~-]+)*@(?:[A-Za-z0-9](?:[A-Za-z0-9-]*[A-Za-z0-9])?\.)+[A-Za-z]{2,}$/i.test(email);
	}

	var form = document.querySelector(".web-form");
	if (form) {
		form.addEventListener(
			"submit",
			function (event) {
				var emailInput = form.querySelector('input[data-fieldname="email"]');
				if (emailInput) {
					var email = emailInput.value.trim();
					if (email && !isValidEmail(email)) {
						event.preventDefault();
						event.stopImmediatePropagation();
						frappe.msgprint("Please enter a valid email address");
						emailInput.focus();
						return false;
					}
				}
			},
			true
		);
	}

	// The "Submit another response" button is rendered on page load inside
	// the hidden success div — fix its href before the user ever sees it.
	var newBtn = document.querySelector(".new-btn");
	if (newBtn) {
		newBtn.href = "/event-registration/new?event=" + encodeURIComponent(event_name);
	}
});
