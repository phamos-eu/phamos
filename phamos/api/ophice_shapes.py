# Copyright (c) 2026, phamos.eu and contributors
# For license information, please see license.txt

"""Shapes of Ophice's meeting areas (#2144): rectangle, ellipse, polygon.

Every area keeps x, y, width and height (in squares) as its box; an ellipse fills its box, a
polygon has corner points (half squares) and its box is computed from them. The same rules live in
ophice_frontend/src/utils/ophiceShapes.js, so the server and the map agree on who is inside.
"""

import json
import math

import frappe
from frappe import _

SHAPES = ("Rectangle", "Ellipse", "Polygon")
MAX_POINTS = 40
STEP = 0.5
# Overlap of two shapes: tested on a raster this fine (squares), inside both boxes.
OVERLAP_STEP = 0.25


def shape_of(area):
	shape = _get(area, "shape")
	return shape if shape in SHAPES else "Rectangle"


def points_of(area):
	"""The corner points of a polygon area as [(x, y), ...]; [] for other shapes or broken data."""
	if shape_of(area) != "Polygon":
		return []
	raw = _get(area, "points")
	if isinstance(raw, str):
		try:
			raw = json.loads(raw or "[]")
		except ValueError:
			return []
	if not isinstance(raw, list):
		return []
	points = []
	for point in raw:
		if isinstance(point, (list, tuple)) and len(point) == 2:
			x, y = _number(point[0]), _number(point[1])
			if x is not None and y is not None:
				points.append((x, y))
	return points if len(points) >= 3 else []


def _get(area, key):
	return area.get(key) if isinstance(area, dict) else getattr(area, key, None)


def _number(value):
	try:
		value = float(value)
	except (TypeError, ValueError):
		return None
	return value if math.isfinite(value) else None


def _box(area):
	return (
		frappe.utils.flt(_get(area, "x")),
		frappe.utils.flt(_get(area, "y")),
		frappe.utils.flt(_get(area, "width")),
		frappe.utils.flt(_get(area, "height")),
	)


def contains(area, px, py, slack=0.0):
	"""True when the point (squares) lies in the area, or within `slack` of its edge."""
	x, y, w, h = _box(area)
	shape = shape_of(area)
	points = points_of(area) if shape == "Polygon" else []
	if shape == "Polygon" and not points:
		shape = "Rectangle"
	if shape == "Rectangle":
		return x - slack <= px < x + w + slack and y - slack <= py < y + h + slack
	if not (x - slack <= px <= x + w + slack and y - slack <= py <= y + h + slack):
		return False
	if shape == "Ellipse":
		rx, ry = w / 2 + slack, h / 2 + slack
		if rx <= 0 or ry <= 0:
			return False
		return ((px - x - w / 2) / rx) ** 2 + ((py - y - h / 2) / ry) ** 2 <= 1
	if in_polygon(points, px, py):
		return True
	return bool(slack) and _edge_distance(points, px, py)[0] <= slack


def in_polygon(points, px, py):
	"""Even-odd ray casting."""
	inside = False
	n = len(points)
	for i in range(n):
		x1, y1 = points[i]
		x2, y2 = points[(i + 1) % n]
		if (y1 > py) != (y2 > py):
			cross = x1 + (py - y1) * (x2 - x1) / (y2 - y1)
			if px < cross:
				inside = not inside
	return inside


def _nearest_on_segment(ax, ay, bx, by, px, py):
	dx, dy = bx - ax, by - ay
	length = dx * dx + dy * dy
	t = 0.0 if not length else max(0.0, min(1.0, ((px - ax) * dx + (py - ay) * dy) / length))
	return ax + t * dx, ay + t * dy


def _edge_distance(points, px, py):
	"""(distance, (x, y)) of the nearest point on the polygon's edges."""
	best = (math.inf, (px, py))
	n = len(points)
	for i in range(n):
		qx, qy = _nearest_on_segment(*points[i], *points[(i + 1) % n], px, py)
		distance = math.hypot(px - qx, py - qy)
		if distance < best[0]:
			best = (distance, (qx, qy))
	return best


def nearest_inside(area, px, py):
	"""The point of the area nearest to (px, py) (itself when inside): where a guest is kept."""
	if contains(area, px, py):
		return px, py
	x, y, w, h = _box(area)
	shape = shape_of(area)
	points = points_of(area)
	if shape == "Ellipse" and w > 0 and h > 0:
		cx, cy, rx, ry = x + w / 2, y + h / 2, w / 2, h / 2
		dx, dy = px - cx, py - cy
		scale = math.hypot(dx / rx, dy / ry)
		if scale:
			# Along the line to the middle, just inside the edge.
			return cx + dx / scale * 0.999, cy + dy / scale * 0.999
		return cx, cy
	if shape == "Polygon" and points:
		qx, qy = _edge_distance(points, px, py)[1]
		# A hair off the edge, to whichever side is inside.
		for angle in range(0, 360, 45):
			nx = qx + 0.01 * math.cos(math.radians(angle))
			ny = qy + 0.01 * math.sin(math.radians(angle))
			if in_polygon(points, nx, ny):
				return nx, ny
		return qx, qy
	return min(max(px, x), x + w - 1e-6), min(max(py, y), y + h - 1e-6)


def overlaps(a, b):
	"""True when two areas share some ground."""
	ax, ay, aw, ah = _box(a)
	bx, by, bw, bh = _box(b)
	left, right = max(ax, bx), min(ax + aw, bx + bw)
	top, bottom = max(ay, by), min(ay + ah, by + bh)
	if left >= right or top >= bottom:
		return False
	if shape_of(a) == "Rectangle" and shape_of(b) == "Rectangle":
		return True
	y = top + OVERLAP_STEP / 2
	while y < bottom:
		x = left + OVERLAP_STEP / 2
		while x < right:
			if contains(a, x, y) and contains(b, x, y):
				return True
			x += OVERLAP_STEP
		y += OVERLAP_STEP
	return False


def _cross(o, a, b):
	return (a[0] - o[0]) * (b[1] - o[1]) - (a[1] - o[1]) * (b[0] - o[0])


def _segments_cross(p1, p2, q1, q2):
	d1, d2 = _cross(q1, q2, p1), _cross(q1, q2, p2)
	d3, d4 = _cross(p1, p2, q1), _cross(p1, p2, q2)
	return ((d1 > 0) != (d2 > 0)) and ((d3 > 0) != (d4 > 0)) and d1 and d2 and d3 and d4


def clean_points(raw, cols, rows):
	"""Corner points from the page: half squares, inside the grid, 3 to MAX_POINTS, a real area,
	no crossing edges. Returns [[x, y], ...]."""
	if isinstance(raw, str):
		try:
			raw = json.loads(raw or "[]")
		except ValueError:
			raw = None
	if not isinstance(raw, list):
		frappe.throw(_("A polygon needs its corner points."))
	points = []
	for point in raw[: MAX_POINTS + 1]:
		x = _number(point[0]) if isinstance(point, (list, tuple)) and len(point) == 2 else None
		y = _number(point[1]) if x is not None else None
		if x is None or y is None:
			frappe.throw(_("A corner point is not a number."))
		x = max(0.0, min(float(cols), round(x / STEP) * STEP))
		y = max(0.0, min(float(rows), round(y / STEP) * STEP))
		if not points or points[-1] != [x, y]:
			points.append([x, y])
	if len(points) > 1 and points[0] == points[-1]:
		points.pop()
	if len(points) < 3:
		frappe.throw(_("A polygon needs at least 3 corners."))
	if len(points) > MAX_POINTS:
		frappe.throw(_("A polygon can have at most {0} corners.").format(MAX_POINTS))
	area = sum(points[i][0] * points[(i + 1) % len(points)][1] - points[(i + 1) % len(points)][0] * points[i][1] for i in range(len(points))) / 2
	if abs(area) < STEP * STEP:
		frappe.throw(_("The polygon is too small."))
	n = len(points)
	for i in range(n):
		for j in range(i + 1, n):
			if j == i + 1 or (i == 0 and j == n - 1):
				continue  # neighbours share a corner
			if _segments_cross(points[i], points[(i + 1) % n], points[j], points[(j + 1) % n]):
				frappe.throw(_("The edges of the polygon cross each other."))
	return points


def box_of(points):
	xs = [p[0] for p in points]
	ys = [p[1] for p in points]
	return min(xs), min(ys), max(xs) - min(xs), max(ys) - min(ys)
