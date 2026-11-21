// Rating a fix (#2014): the question in the bubble. Step 1: thumbs (bugs) or 1-5 stars
// (improvements); step 2: an optional comment, then Send. Closing with × puts it off to another
// day (at most 3 times); "No thanks" declines it (PM, 2026-11-21). Goes through the one voice as
// a question (phamos/phriend/feedback.py keeps it on the server until answered).

import { call } from "./request";
import { escape_html } from "./util";

const API = "phamos.phriend.api.";
export const LATER = "Battle tested";

// The question for a request { name, kind, round, title, subject }; the title is escaped here.
export function question_text(__, req) {
	const title = `“${escape_html(req.title || req.subject || "")}”`;
	const later = req.round === LATER;
	if (req.kind === "Stars")
		return later
			? __("{0} has been live for a while. How do you like it now?", [title])
			: __("{0} is live. How do you like it?", [title]);
	return later ? __("{0} has been live for a while. Still fixed?", [title]) : __("{0} is live. Did it fix it?", [title]);
}

// The rating buttons: thumbs up (1) / down (-1), or stars 1-5.
export function picks_html(__, kind) {
	if (kind === "Stars")
		return `<div class="rate-row stars">${[1, 2, 3, 4, 5]
			.map((n) => `<button type="button" class="pick" data-r="${n}" aria-label="${escape_html(__("{0} of 5 stars", [n]))}">★</button>`)
			.join("")}</div>`;
	return `<div class="rate-row">
		<button type="button" class="pick" data-r="1" aria-label="${escape_html(__("Yes, fixed"))}">👍</button>
		<button type="button" class="pick" data-r="-1" aria-label="${escape_html(__("No, not fixed"))}">👎</button></div>`;
}

// The voice item for a request: shows step 1, binds both steps.
export function rating_item(phriend, req) {
	const __ = phriend.__;
	const csrf = () => phriend.host.csrf_token();
	const html = `<div class="rate-q">${question_text(__, req)}</div>${picks_html(__, req.kind)}
		<div class="rate-foot"><button type="button" class="link" data-decline>${escape_html(__("No thanks"))}</button></div>`;

	const send = async (rating, comment) => {
		try {
			await call(`${API}answer_feedback`, { name: req.name, rating, comment }, csrf());
			phriend.ball.say(escape_html(__("Thank you! The team will see it.")), 3500, "thanks");
		} catch (e) {
			const text = e.message && e.message !== e.kind ? e.message : __("That didn't work. Please try again.");
			phriend.ball.say(escape_html(text), 6000, "point_up");
		}
	};

	const comment_step = (rating) => {
		const bubble = phriend.ball.refill_bubble(`<div class="rate-q">${escape_html(__("Thanks! Anything to add?"))}</div>
			<textarea class="rate-comment" rows="2" maxlength="2000" placeholder="${escape_html(__("Optional"))}"></textarea>
			<div class="rate-row"><button type="button" class="rate-send">${escape_html(__("Send"))}</button></div>`);
		const box = bubble.querySelector(".rate-comment");
		box.focus();
		bubble.querySelector(".rate-send").addEventListener("click", () => send(rating, box.value));
	};

	const bind = (bubble) => {
		const stars = [...bubble.querySelectorAll(".rate-row.stars .pick")];
		for (const button of bubble.querySelectorAll(".pick")) {
			const rating = Number(button.dataset.r);
			button.addEventListener("click", () => comment_step(rating));
			// stars light up to the one under the pointer
			if (stars.length) button.addEventListener("pointerenter", () => stars.forEach((s) => s.classList.toggle("on", Number(s.dataset.r) <= rating)));
		}
		const decline = bubble.querySelector("[data-decline]");
		if (decline)
			decline.addEventListener("click", () => {
				phriend.ball.hide_bubble();
				call(`${API}decline_feedback`, { name: req.name }, csrf()).catch(() => {});
			});
	};

	return {
		html,
		ms: 0, // stays until answered, declined or closed
		bind,
		// × : another day (the server counts it, at most 3 times)
		on_close: () => call(`${API}defer_feedback`, { name: req.name }, csrf()).catch(() => {}),
	};
}
