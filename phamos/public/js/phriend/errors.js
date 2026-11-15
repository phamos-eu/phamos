// Records what went wrong on the page before the user clicked Phriend: script errors,
// rejected promises, console.error and failed server calls. The last few go into the report.

import { safe_json } from "./util";

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

	// Called by the host for every failed call: { url, method, status, message }
	record_failed_request(item) {
		this.push(this.failed_requests, {
			...item,
			message: item.message ? String(item.message).slice(0, 1000) : undefined,
		});
		this.listeners.forEach((callback) => callback(item));
	}

	watch() {
		window.addEventListener("error", (e) => {
			this.push(this.errors, {
				type: "error",
				message: String(e.message || e.error || "Unknown error"),
				source: e.filename ? `${e.filename}:${e.lineno}:${e.colno}` : undefined,
			});
		});

		window.addEventListener("unhandledrejection", (e) => {
			this.push(this.errors, {
				type: "unhandledrejection",
				message: String((e.reason && (e.reason.message || e.reason)) || "Unknown rejection"),
			});
		});

		const original_error = console.error;
		console.error = (...args) => {
			try {
				this.push(this.errors, {
					type: "console.error",
					message: args
						.map((a) => (a instanceof Error ? a.message : typeof a === "string" ? a : safe_json(a)))
						.join(" ")
						.slice(0, 1000),
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
