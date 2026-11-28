// Whether a scroll box hides content above or below its visible part, with a small tolerance so
// rounding does not leave a hint showing at the very end.
export function scrollOverflow({ scrollTop = 0, clientHeight = 0, scrollHeight = 0 } = {}, tolerance = 2) {
	return {
		above: scrollTop > tolerance,
		below: scrollTop + clientHeight < scrollHeight - tolerance,
	}
}
