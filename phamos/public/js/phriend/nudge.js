// When Phriend waves "Click me!" (#1990): to users who never opened it, and to users who have
// not opened it for 10 to 20 days (drawn anew after every opening). Until they open it, once a day
// for the first nudges, then once a week. Kept in this browser only, with the user it belongs to;
// no server call. Pure functions apart from read() and write(), so they can be tested.

import { storage_get, storage_set } from "./util";

export const NUDGE_KEY = "phriend:nudge";
export const MIN_IDLE_DAYS = 10;
export const MAX_IDLE_DAYS = 20;
export const DAILY_NUDGES = 3; // then weekly
const DAY = 24 * 60 * 60 * 1000;

export function fresh(user) {
	return { user: user || "", clicked_at: null, idle_days: null, nudged_at: null, nudges: 0 };
}

const is_time = (value) => typeof value === "number" && Number.isFinite(value) && value > 0;

// The stored text as a state for this user; anything broken or someone else's starts fresh.
export function parse(text, user) {
	let raw;
	try {
		raw = JSON.parse(text || "null");
	} catch (e) {
		raw = null;
	}
	if (!raw || typeof raw !== "object" || raw.user !== (user || "")) return fresh(user);
	const state = fresh(user);
	if (is_time(raw.clicked_at)) {
		state.clicked_at = raw.clicked_at;
		const days = Number(raw.idle_days);
		state.idle_days = days >= MIN_IDLE_DAYS && days <= MAX_IDLE_DAYS ? days : MIN_IDLE_DAYS;
	}
	if (is_time(raw.nudged_at)) state.nudged_at = raw.nudged_at;
	state.nudges = Number.isInteger(raw.nudges) && raw.nudges > 0 ? raw.nudges : 0;
	return state;
}

export function read(user) {
	return parse(storage_get(NUDGE_KEY), user);
}

export function write(state) {
	storage_set(NUDGE_KEY, JSON.stringify(state));
}

function same_day(a, b) {
	return new Date(a).toDateString() === new Date(b).toDateString();
}

export function is_due(state, now) {
	if (state.clicked_at && now - state.clicked_at < state.idle_days * DAY) return false;
	if (!state.nudged_at) return true;
	if (state.nudges < DAILY_NUDGES) return now > state.nudged_at && !same_day(state.nudged_at, now);
	return now - state.nudged_at >= 7 * DAY;
}

export function after_nudge(state, now) {
	return { ...state, nudged_at: now, nudges: state.nudges + 1 };
}

// Opening Phriend: no nudges for a new idle time of 10 to 20 days.
export function after_click(state, now, random = Math.random) {
	const span = MAX_IDLE_DAYS - MIN_IDLE_DAYS + 1;
	const idle_days = Math.min(MAX_IDLE_DAYS, MIN_IDLE_DAYS + Math.floor(random() * span));
	return { ...state, clicked_at: now, idle_days, nudged_at: null, nudges: 0 };
}
