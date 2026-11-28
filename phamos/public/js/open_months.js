// Open months in hours charts (phamos/phamos#2199).
// An open month is a month after the current month: nobody could book hours in it yet.
// Charts show it as "no value" (null), not as 0, so an area ends at the current month
// instead of sloping down to zero.

// values[i] belongs to months[i] ("YYYY-MM"). today is "YYYY-MM-DD" in the site's timezone.
export function blankOpenMonths(values, months, today) {
	return values.map((value, i) => (isOpenMonth(months[i], today) ? null : value));
}

export function isOpenMonth(month, today) {
	return month > today.slice(0, 7);
}
