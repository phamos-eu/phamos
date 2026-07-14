frappe.ui.form.on('Team Daily Schedule', {
	fetch_free_slots(frm, cdt, cdn) {
		const row = locals[cdt][cdn];
		show_free_slots_dialog_for_row(frm, row, cdt, cdn);
	},
});

function show_free_slots_dialog_for_row(frm, row, cdt, cdn) {
	if (!row.email_account) {
		frappe.msgprint(__('Please select Email Account first. It is required for fetching slots.'));
		return;
	}

	const today = frappe.datetime.get_today();

	const d = new frappe.ui.Dialog({
		title: __('Find Free Slots (Mailcow)'),
		fields: [
			{ fieldname: 'section_inputs', fieldtype: 'Section Break' },
			{ fieldname: 'day', fieldtype: 'Date', label: __('Day'), default: today, reqd: 1 },
			{ fieldname: 'col1', fieldtype: 'Column Break' },
			{ fieldname: 'duration', fieldtype: 'Int', label: __('Duration (minutes)'), default: 60, reqd: 1 },
			{ fieldname: 'col2', fieldtype: 'Column Break' },
			{ fieldname: 'time_from', fieldtype: 'Time', label: __('From (optional)'), default: '07:00:00' },
			{ fieldname: 'col3', fieldtype: 'Column Break' },
			{ fieldname: 'time_to', fieldtype: 'Time', label: __('To (optional)'), default: '18:00:00' },
			{ fieldname: 'section_results', fieldtype: 'Section Break' },
			{ fieldname: 'picked_slot', fieldtype: 'Data', hidden: 1 },
			{ fieldname: 'options_html', fieldtype: 'HTML' },
		],
		primary_action_label: __('Use Selected Slot'),
		primary_action() {
			const picked = d.get_value('picked_slot');
			if (!picked) {
				frappe.msgprint(__('Please pick a slot first.'));
				return;
			}

			const [start, end] = picked.split('|');
			frappe.model.set_value(cdt, cdn, 'start', start);
			frappe.model.set_value(cdt, cdn, 'end', end);
			frm.refresh_field('custom_team_daily_schedule');
			d.hide();
		},
	});

	const render_slots = (slots) => {
		const wrap = d.get_field('options_html').$wrapper;
		wrap.empty();

		if (!slots || !slots.length) {
			wrap.html(`<div class="text-muted">${__('No free slots found.')}</div>`);
			return;
		}

		const tabsId = `mailcow-free-slots-tabs-${frappe.utils.get_random(8)}`;
		const container = $('<div class="border rounded">');
		const nav = $(
			`<ul class="nav nav-tabs flex-nowrap" role="tablist" style="overflow-x:auto; overflow-y:hidden; flex-wrap:nowrap; white-space:nowrap; -webkit-overflow-scrolling:touch; gap:.25rem;"></ul>`
		);
		const content = $('<div class="tab-content border-top p-2"></div>');

		slots.forEach((slot, i) => {
			const label = slot.label || `${slot.start_local || slot.start} -> ${slot.end_local || slot.end}`;
			const tabId = `${tabsId}-tab-${i}`;
			const activeLink = i === 0 ? 'active' : '';
			const activePane = i === 0 ? 'show active' : '';

			nav.append(`
				<li class="nav-item" role="presentation" style="flex:0 0 auto;">
					<a class="nav-link ${activeLink}" data-slot-index="${i}" data-toggle="tab" data-bs-toggle="tab" data-target="#${tabId}" data-bs-target="#${tabId}" href="javascript:void(0)" role="tab" aria-controls="${tabId}" aria-selected="${i === 0 ? 'true' : 'false'}" style="white-space:nowrap;">${label}</a>
				</li>
			`);

			content.append(`
				<div class="tab-pane fade ${activePane}" id="${tabId}" role="tabpanel" style="padding: 6px;">
					<button class="btn btn-primary">${__('Pick this slot')}</button>
				</div>
			`);
		});

		if (slots.length > 3) {
			wrap.append(`<div class="text-muted small mb-1">${__('Scroll horizontally to see more slots')}</div>`);
		}

		container.append(nav);
		container.append(content);
		wrap.append(container);

		const setSelected = (idx) => {
			wrap.find('.tab-pane').removeClass('border border-2 border-success rounded mailcow-slot-selected');
			wrap.find('.nav-link').removeClass('text-success fw-bold');

			const selPaneId = `#${tabsId}-tab-${idx}`;
			wrap.find(selPaneId).addClass('border border-2 border-success rounded mailcow-slot-selected');
			wrap.find(`.nav-link[data-bs-target="${selPaneId}"], .nav-link[data-target="${selPaneId}"]`).addClass('text-success fw-bold');

			const s = slots[idx];
			if (s) {
				const startUse = s.start_local || s.start;
				const endUse = s.end_local || s.end;
				d.set_value('picked_slot', `${startUse}|${endUse}`);
			}
		};

		slots.forEach((slot, i) => {
			const tabId = `${tabsId}-tab-${i}`;
			wrap.find(`#${tabId} button`).on('click', () => {
				const startUse = slot.start_local || slot.start;
				const endUse = slot.end_local || slot.end;
				d.set_value('picked_slot', `${startUse}|${endUse}`);
				setSelected(i);
				frappe.show_alert({ message: __('Selected: {0} -> {1}', [startUse, endUse]), indicator: 'green' });
			});
		});

		wrap.on('shown.bs.tab', `.nav-link[data-target^="#${tabsId}-tab-"], .nav-link[data-bs-target^="#${tabsId}-tab-"]`, function () {
			const idx = $(this).data('slotIndex');
			if (idx !== undefined) {
				setSelected(idx);
			}
		});

		wrap.on('click', `.nav-link[data-target^="#${tabsId}-tab-"], .nav-link[data-bs-target^="#${tabsId}-tab-"]`, function (e) {
			e.preventDefault();
			const idx = $(this).data('slotIndex');
			try {
				if (window.bootstrap && bootstrap.Tab) {
					new bootstrap.Tab(this).show();
				} else if (typeof $(this).tab === 'function') {
					$(this).tab('show');
				}
			} catch (err) {
				// no-op
			}
			if (idx !== undefined) {
				setSelected(idx);
			}
		});

		setSelected(0);
	};

	const fetch_slots = () => {
		const values = d.get_values();
		if (!values) return;

		const time_from = values.time_from ? String(values.time_from).slice(0, 5) : undefined;
		const time_to = values.time_to ? String(values.time_to).slice(0, 5) : undefined;

		frappe.call({
			method: 'phamos.mailcow_integration.availability.next_free_slot.free_slots_for_day',
			args: {
				day: values.day,
				duration_minutes: values.duration,
				time_from,
				time_to,
			},
			freeze: true,
			freeze_message: __('Finding free slots...'),
			callback(r) {
				render_slots(r.message || []);
			},
		});
	};

	d.set_secondary_action(fetch_slots);
	d.set_secondary_action_label(__('Fetch Free Slots'));
	d.show();
	fetch_slots();
}
