/**
 * Attendees of an appointment (#1949): two sections, required and optional, of email addresses.
 * Pure helpers for AttendeePicker.vue, kept free of Vue and the DOM so they can be unit-tested.
 * Every helper returns a new { required, optional } and never mutates its input.
 */

export const SECTIONS = ["required", "optional"]

const key = (email) => String(email || "").trim().toLowerCase()

/** Both sections as given, without duplicates (an address in both counts as required). */
export function normalizeAttendees({ required = [], optional = [] } = {}) {
	const seen = new Set()
	const unique = (list) =>
		list.filter((email) => {
			const k = key(email)
			if (!k || seen.has(k)) return false
			seen.add(k)
			return true
		})
	const req = unique(required)
	return { required: req, optional: unique(optional) }
}

export function isPicked(attendees, email) {
	const k = key(email)
	return [...attendees.required, ...attendees.optional].some((e) => key(e) === k)
}

/** Add addresses that aren't picked yet to `section` (required by default). */
export function addAttendees(attendees, emails, section = "required") {
	const fresh = emails.filter((email) => key(email) && !isPicked(attendees, email))
	return normalizeAttendees({ ...attendees, [section]: [...attendees[section], ...fresh] })
}

/** Add a whole department: its people that aren't picked yet go to required. */
export function addDepartment(attendees, group) {
	return addAttendees(attendees, (group.people || []).map((person) => person.email))
}

export function removeAttendee(attendees, email) {
	const k = key(email)
	return {
		required: attendees.required.filter((e) => key(e) !== k),
		optional: attendees.optional.filter((e) => key(e) !== k),
	}
}

/** Move an address to `section` (drag and drop); at the end of that section. */
export function moveAttendee(attendees, email, section) {
	if (!SECTIONS.includes(section) || !isPicked(attendees, email)) return attendees
	const rest = removeAttendee(attendees, email)
	return { ...rest, [section]: [...rest[section], email] }
}

/** "all", "some" or "none" of a department's people are picked: for the department button. */
export function departmentState(attendees, group) {
	const people = group.people || []
	const picked = people.filter((person) => isPicked(attendees, person.email)).length
	if (!people.length || !picked) return "none"
	return picked === people.length ? "all" : "some"
}

/** email -> person, so chips show names; addresses without a person (external guests) stay as text. */
export function peopleIndex(departments) {
	const index = new Map()
	for (const group of departments || []) {
		for (const person of group.people || []) index.set(key(person.email), person)
	}
	return index
}

export function personFor(index, email) {
	return index.get(key(email)) || { email, name: email, image: null }
}
