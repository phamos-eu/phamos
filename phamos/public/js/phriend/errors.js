// Records what went wrong on the page before the user clicked Phriend: script errors,
// rejected promises, console.error and failed server calls. The last few go into the report.

import { without_query } from "./util";

// Short: error messages can name people, leave types or amounts (GDPR review of !1162).
const MAX_MESSAGE = 200;

const MAX_LOG = 20;

export class ErrorLog {
	constructor() {
		this.errors = [];
		this.failed_requests = [];
		this.listeners = [];
		this.watch();
	}

	on_failed_request(callback) {
		this.listeners.push(callback);
	}

	push(list, item) {
		list.push({ at: new Date().toISOString(), ...item });
		if (list.length > MAX_LOG) list.shift();
	}

	// Called by the host for every failed call: { url, method, status, message }. The URL is kept
	// without its query string, the message short.
	record_failed_request(item) {
		this.push(this.failed_requests, {
			...item,
			url: without_query(item.url),
			message: item.message ? String(item.message).slice(0, MAX_MESSAGE) : undefined,
		});
		this.listeners.forEach((callback) => callback(item));
	}

	watch() {
		window.addEventListener("error", (e) => {
			this.push(this.errors, {
				type: "error",
				message: String(e.message || e.error || "Unknown error").slice(0, MAX_MESSAGE),
				source: e.filename ? `${without_query(e.filename)}:${e.lineno}:${e.colno}` : undefined,
			});
		});

		window.addEventListener("unhandledrejection", (e) => {
			this.push(this.errors, {
				type: "unhandledrejection",
				message: String((e.reason && (e.reason.message || e.reason)) || "Unknown rejection").slice(0, MAX_MESSAGE),
			});
		});

		const original_error = console.error;
		console.error = (...args) => {
			try {
				this.push(this.errors, {
					type: "console.error",
					// text and error messages only: logged objects can be whole records
					message: args
						.map((a) => (a instanceof Error ? a.message : typeof a === "string" ? a : `[${typeof a}]`))
						.join(" ")
						.slice(0, MAX_MESSAGE),
				});
			} catch (e) {
				// never break console.error
			}
			return original_error.apply(console, args);
		};
	}

	snapshot() {
		return { recent_errors: this.errors.slice(), failed_requests: this.failed_requests.slice() };
	}
}
