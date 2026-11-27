# Copyright (c) 2026, phamos.eu and contributors
# For license information, please see license.txt

"""Critical path and slack of an implementation's chapters (#2033, part of the Roadmap #1694).

One pure function, without database access, so the Roadmap, the Overview (#1681) and later
warnings all use the same numbers.

The method (finish-to-start, on the planned dates):
- A chapter runs from its `planned_start` to its `target_date`, both days included.
- A successor may start the day after its predecessor's target date.
- Backward pass: an end chapter (no successors) must finish by the deadline. Its latest start
  follows from its duration. A predecessor must finish the day before the earliest latest
  start of its successors.
- Slack = latest finish − planned target date, in calendar days. Zero or less is critical;
  below zero means the plan already misses the deadline or a successor's start.

The deadline is the latest planned target date of all chapters unless one is given; once
Implementation Key Dates exist (#1973), the Go-Live date is passed here.
"""

from datetime import date, timedelta

from frappe.utils import getdate


def dependency_conflict(predecessor, successor):
	"""True when a predecessor ends on or after the day its successor is planned to start.

	Both rows need `planned_start` and `target_date`; without them there is nothing to compare.
	Dates are whole days, so ending on the successor's first day already overlaps it.
	"""
	end, start = _date(predecessor.get("target_date")), _date(successor.get("planned_start"))
	if not end or not start:
		return False
	return end >= start


def critical_path(chapters, deadline=None):
	"""Critical flag and slack per chapter.

	`chapters`: rows (dicts) with `name`, `planned_start`, `target_date` and `depends_on` (the
	names of the chapters this one waits for). Dependencies on names not in `chapters` are
	ignored, so the caller decides which chapters count (for example no Draft ones).

	Returns `{"items": {name: {"critical", "slack_days", "cycle"}}, "dependencies": [...]}`:
	- `critical` / `slack_days` are None for a chapter without both dates, and for a chapter in
	  a dependency loop (`cycle` True). Neither blocks the others: their links are left out.
	- `dependencies`: every `{from, to, conflict}` between the given chapters.
	"""
	rows = {row["name"]: row for row in chapters}
	edges, self_loops = [], set()
	for row in chapters:
		# dict.fromkeys: the same predecessor listed twice is one dependency
		for predecessor in dict.fromkeys(row.get("depends_on") or []):
			if predecessor == row["name"]:
				self_loops.add(predecessor)
			elif predecessor in rows:
				edges.append((predecessor, row["name"]))
	dependencies = [
		{"from": a, "to": b, "conflict": dependency_conflict(rows[a], rows[b])} for a, b in edges
	]

	items = {name: {"critical": None, "slack_days": None, "cycle": False} for name in rows}
	in_cycle = _nodes_in_cycles(rows, edges) | self_loops
	for name in in_cycle:
		items[name]["cycle"] = True

	dated = {
		name: (_date(row.get("planned_start")), _date(row.get("target_date")))
		for name, row in rows.items()
		if name not in in_cycle and _date(row.get("planned_start")) and _date(row.get("target_date"))
	}
	if not dated:
		return {"items": items, "dependencies": dependencies}

	successors = {name: [] for name in dated}
	for a, b in edges:
		if a in dated and b in dated:
			successors[a].append(b)

	end = _date(deadline) or max(target for _start, target in dated.values())
	latest_finish = {}
	for name in _reverse_topological(successors):
		latest_start_of_successors = [
			latest_finish[s] - (dated[s][1] - dated[s][0]) for s in successors[name]
		]
		latest_finish[name] = (
			min(latest_start_of_successors) - timedelta(days=1) if latest_start_of_successors else end
		)
		slack = (latest_finish[name] - dated[name][1]).days
		items[name]["slack_days"] = slack
		items[name]["critical"] = slack <= 0

	return {"items": items, "dependencies": dependencies}


def _date(value):
	if not value:
		return None
	return value if isinstance(value, date) else getdate(value)


def _reverse_topological(successors):
	"""Names ordered so that every chapter comes after all of its successors (graph without loops)."""
	remaining = {name: len(succ) for name, succ in successors.items()}
	predecessors = {name: [] for name in successors}
	for name, succ in successors.items():
		for s in succ:
			predecessors[s].append(name)
	ready = sorted(name for name, count in remaining.items() if count == 0)
	order = []
	while ready:
		name = ready.pop()
		order.append(name)
		for p in predecessors[name]:
			remaining[p] -= 1
			if remaining[p] == 0:
				ready.append(p)
	return order


def _nodes_in_cycles(rows, edges):
	"""Names that sit in a dependency loop (strongly connected component of more than one chapter).

	Chapter validation already refuses loops (`validate_planning_links`), but old data or a
	direct database edit can still hold one; the Roadmap must not break on it.
	"""
	graph = {name: [] for name in rows}
	for a, b in edges:
		graph[a].append(b)

	index, low, on_stack, stack, found = {}, {}, set(), [], set()
	counter = [0]

	def visit(start):
		# iterative Tarjan, so a long chain of chapters cannot hit Python's recursion limit
		work = [(start, iter(graph[start]))]
		index[start] = low[start] = counter[0]
		counter[0] += 1
		stack.append(start)
		on_stack.add(start)
		while work:
			node, children = work[-1]
			child = next(children, None)
			if child is not None:
				if child not in index:
					index[child] = low[child] = counter[0]
					counter[0] += 1
					stack.append(child)
					on_stack.add(child)
					work.append((child, iter(graph[child])))
				elif child in on_stack:
					low[node] = min(low[node], index[child])
				continue
			work.pop()
			if work:
				parent = work[-1][0]
				low[parent] = min(low[parent], low[node])
			if low[node] == index[node]:
				component = []
				while True:
					member = stack.pop()
					on_stack.discard(member)
					component.append(member)
					if member == node:
						break
				if len(component) > 1:
					found.update(component)

	for name in graph:
		if name not in index:
			visit(name)
	return found
