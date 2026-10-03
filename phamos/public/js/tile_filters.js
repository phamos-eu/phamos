// Copyright (c) 2026, phamos.eu and contributors
// For license information, please see license.txt

frappe.provide("phamos.tile_filters");

(function () {
	function parseRange(value) {
		const [min, max] = value.split("-").map(Number);
		return { min, max };
	}

	function getFilterState($root) {
		const state = { search: "", facets: {} };
		const search = $root.find("[data-tile-search]").val();
		if (search) state.search = search.toLowerCase().trim();
		$root.find("[data-tile-facet]").each(function () {
			const $input = $(this);
			if (!$input.is(":checked")) return;
			const key = $input.data("tile-facet");
			const value = $input.val();
			if ($input.attr("type") === "radio") {
				state.facets[key] = value;
			} else {
				(state.facets[key] = state.facets[key] || []).push(value);
			}
		});
		return state;
	}

	function matchesFacets($item, facets) {
		for (const key in facets) {
			const value = String($item.data(key) || "");
			if (Array.isArray(facets[key])) {
				if (!facets[key].includes(value)) return false;
			} else if (key === "years") {
				const { min, max } = parseRange(facets[key]);
				const years = Number($item.data("years") || 0);
				if (years < min || years > max) return false;
			}
		}
		return true;
	}

	function applyFilters($root) {
		const state = getFilterState($root);
		const $items = $root.find("[data-tile-item]");
		let visible = 0;
		$items.each(function () {
			const $item = $(this);
			const name = String($item.data("name") || "").toLowerCase();
			const matches =
				(!state.search || name.includes(state.search)) &&
				matchesFacets($item, state.facets);
			$item.toggle(matches);
			if (matches) visible++;
		});
		$root.find("[data-tile-result-count]").text(visible + " " + __("Ergebnisse"));
		$root
			.closest(".tile-grid-layout")
			.find("[data-tile-grid-no-results]")
			.toggle(visible === 0);
	}

	function clearFilters($root) {
		$root.find("[data-tile-search]").val("");
		$root.find("[data-tile-facet]").prop("checked", false);
		applyFilters($root);
	}

	phamos.tile_filters.init = function () {
		$("[data-tile-filters]").each(function () {
			const $root = $(this);
			$root.on("input", "[data-tile-search]", () => applyFilters($root));
			$root.on("change", "[data-tile-facet]", () => applyFilters($root));
			$root.on("click", "[data-tile-filters-clear]", () => clearFilters($root));
		});
	};

	$(document).ready(function () {
		phamos.tile_filters.init();
	});
})();
