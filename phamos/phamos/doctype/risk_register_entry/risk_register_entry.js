// Copyright (c) 2026, phamos.eu and contributors
// For license information, please see license.txt

frappe.listview_settings['Risk Register Entry'] = {
	get_indicator(doc) {
		const map = {
			'Low':      ['Low',      'green'],
			'Moderate': ['Moderate', 'yellow'],
			'High':     ['High',     'orange'],
			'Extreme':  ['Extreme',  'red'],
		};
		const entry = map[doc.risk_rating];
		if (entry) return [entry[0], entry[1], 'risk_rating,=,' + doc.risk_rating];
	},
};

frappe.ui.form.on('Risk Register Entry', {
	implementation_severity(frm) { _update_risk(frm); },
	company_severity(frm)        { _update_risk(frm); },
	likelihood(frm)              { _update_risk(frm); },
});

function _parse_level(value) {
	if (!value) return 0;
	const n = parseInt(value[0], 10);
	return isNaN(n) ? 0 : n;
}

function _rating_label(score) {
	if (score >= 16) return 'Extreme';
	if (score >= 10) return 'High';
	if (score >= 5)  return 'Moderate';
	if (score > 0)   return 'Low';
	return '';
}

const _COLOR_MAP = {
	'Extreme':  '#d9534f',
	'High':     '#f0a500',
	'Moderate': '#f0e442',
	'Low':      '#5cb85c',
};

function _update_risk(frm) {
	const likelihood = _parse_level(frm.doc.likelihood);
	const impl_level = _parse_level(frm.doc.implementation_severity) * likelihood;
	const comp_level = _parse_level(frm.doc.company_severity) * likelihood;
	const rating = _rating_label(Math.max(impl_level, comp_level));

	frm.set_value('implementation_risk_level', impl_level);
	frm.set_value('company_risk_level', comp_level);
	frm.set_value('risk_rating', rating);

	_apply_color(frm, 'implementation_risk_level', impl_level);
	_apply_color(frm, 'company_risk_level', comp_level);
	_apply_rating_color(frm, rating);
}

function _apply_color(frm, fieldname, level) {
	const rating = _rating_label(level);
	const color = _COLOR_MAP[rating] || '';
	const $f = frm.get_field(fieldname);
	if ($f && $f.$input) $f.$input.css('background-color', color);
}

function _apply_rating_color(frm, rating) {
	const color = _COLOR_MAP[rating] || '';
	const $f = frm.get_field('risk_rating');
	if ($f && $f.$input) $f.$input.css('background-color', color);
}
