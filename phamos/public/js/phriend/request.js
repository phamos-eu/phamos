// The one server call the report flow makes, with the failure sorted into what the user
// can do about it. Plain fetch, so Desk shows no message box of its own and the cockpits
// need no frappe-ui here.

export class RequestError extends Error {
	// kind: offline | network | session | stale | forbidden | server
	constructor(kind, message, status) {
		super(message || kind);
		this.kind = kind;
		this.status = status;
	}
}

// Text of an HTML server message, parsed in an inert document: an element created in the
// live page would load images (and run their onerror) even without being attached.
export function text_of(html) {
	const doc = new DOMParser().parseFromString(String(html ?? ""), "text/html");
	return (doc.body.textContent || "").trim();
}

function server_message(body) {
	try {
		if (body._server_messages) {
			return JSON.parse(body._server_messages)
				.map((m) => {
					try {
						return JSON.parse(m).message;
					} catch (e) {
						return m;
					}
				})
				.map(text_of)
				.join(" ");
		}
	} catch (e) {
		// fall through
	}
	return body.exception ? text_of(String(body.exception).split("\n").pop()) : "";
}

async function is_logged_in() {
	try {
		const r = await fetch("/api/method/frappe.auth.get_logged_user", { credentials: "same-origin" });
		return !(r.status === 401 || r.status === 403);
	} catch (e) {
		return true; // can't tell; don't send them to log in for nothing
	}
}

export async function call(method, args, csrf_token) {
	let response;
	try {
		response = await fetch(`/api/method/${method}`, {
			method: "POST",
			credentials: "same-origin",
			headers: {
				"Content-Type": "application/json",
				Accept: "application/json",
				"X-Frappe-CSRF-Token": csrf_token || "",
			},
			body: JSON.stringify(args),
		});
	} catch (e) {
		throw new RequestError(navigator.onLine === false ? "offline" : "network");
	}

	let body = {};
	try {
		body = await response.json();
	} catch (e) {
		// an HTML error page or nothing
	}
	if (response.ok) return body.message;

	const message = server_message(body);
	if (body.exc_type === "CSRFTokenError") {
		// logged out, or logged in again in another tab: this page's token is old either way
		const kind = (await is_logged_in()) ? "stale" : "session";
		throw new RequestError(kind, message, response.status);
	}
	if (response.status === 401 || response.status === 403) {
		const kind = (await is_logged_in()) ? "forbidden" : "session";
		throw new RequestError(kind, message, response.status);
	}
	throw new RequestError("server", message, response.status);
}
