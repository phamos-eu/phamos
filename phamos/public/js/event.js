frappe.ui.form.on('Event', {
	onload(frm) {
		// Show dialog only for new, unsaved Events
		if (frm.is_new()) {
			show_free_slots_dialog(frm, { auto: true });
		}

		// Add manual button as well
		frm.add_custom_button(__('Fetch Free Slots'), () => show_free_slots_dialog(frm), __('Mailcow'));
	},
	refresh(frm) {
		// Ensure button exists on refresh too
		if (!frm.custom_buttons || !frm.custom_buttons['Mailcow']) {
			frm.add_custom_button(__('Fetch Free Slots'), () => show_free_slots_dialog(frm), __('Mailcow'));
		}
	}
});

function show_free_slots_dialog(frm, opts = {}) {
	const today = frappe.datetime.get_today();
	const default_end = frappe.datetime.add_days(today, 14);

	// Helper: format ISO datetime into 'YYYY-MM-DD HH:mm:ss' preferably in user TZ
	const format_dt_for_field = (value) => {
		if (!value) return value;
		try {
			const m = frappe.datetime.convert_to_user_tz(value);
			if (m && typeof m.format === 'function') {
				return m.format('YYYY-MM-DD HH:mm:ss');
			}
		} catch (e) { }
		try {
			const d = new Date(value);
			const pad = (n) => String(n).padStart(2, '0');
			const s = `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())} ${pad(d.getHours())}:${pad(d.getMinutes())}:${pad(d.getSeconds())}`;
			return s;
		} catch (e) { }
		return value;
	};

	const d = new frappe.ui.Dialog({
		title: __('Find Free Slots (Mailcow)'),
		fields: [
			{ fieldname: 'section_inputs', fieldtype: 'Section Break' },
			{ fieldname: 'day', fieldtype: 'Date', label: __('Day'), default: today, reqd: 1 },
			{ fieldname: 'col1', fieldtype: 'Column Break' },
			{ fieldname: 'duration', fieldtype: 'Int', label: __('Duration (minutes)'), default: 60, reqd: 1 },
			{ fieldname: 'col2', fieldtype: 'Column Break' },
			// Optional time range (search window within the day)
			{ fieldname: 'time_from', fieldtype: 'Time', label: __('From (optional)'), default: '07:00:00' },
			{ fieldname: 'col3', fieldtype: 'Column Break' },
			{ fieldname: 'time_to', fieldtype: 'Time', label: __('To (optional)'), default: '18:00:00' },
			{ fieldname: 'section_results', fieldtype: 'Section Break' },
			{ fieldname: 'picked_slot', fieldtype: 'Data', hidden: 1 },
			{ fieldname: 'options_html', fieldtype: 'HTML' }
		],
		primary_action_label: __('Use Selected Slot'),
		primary_action(values) {
			const picked = d.get_value('picked_slot');
			if (!picked) {
				frappe.msgprint(__('Please pick a slot first.'));
				return;
			}
			const [start, end] = picked.split('|');
			try {
				console.log('[Mailcow] Applying picked slot to form:', { start_iso: start, end_iso: end, doctype: frm.doctype, name: frm.docname });
			} catch (e) { }
			// const start_str = format_dt_for_field(start);
			// const end_str = format_dt_for_field(end);
			try { console.log('[Mailcow] Formatted for field:', { start, end }); } catch (e) { }
			// Set both fields together for reliability and refresh UI
			frm.set_value({ starts_on: start, ends_on: end }).then(() => {
				frm.refresh_field('starts_on');
				frm.refresh_field('ends_on');
				d.hide();
			});
		}
	});

	// hidden field to hold selection is defined in fields above

	const render_slots = (slots) => {
		const wrap = d.get_field('options_html').$wrapper;
		wrap.empty();

		if (!slots || !slots.length) {
			wrap.html(`<div class="text-muted">${__('No free slots found.')}</div>`);
			return;
		}

		const tabsId = 'mailcow-free-slots-tabs-' + frappe.utils.get_random(8);
		const container = $(`<div class="border rounded">`);
		// Horizontally scrollable tabs (nowrap) with smooth scrolling
		const nav = $(`
	  <ul class="nav nav-tabs flex-nowrap" role="tablist"
		  style="overflow-x:auto; overflow-y:hidden; flex-wrap:nowrap; white-space:nowrap; -webkit-overflow-scrolling:touch; gap:.25rem;">
	  </ul>`);
		const content = $(`<div class="tab-content border-top p-2"></div>`);

		console.log('[Mailcow] Free slots response:', slots);

		slots.forEach((slot, i) => {
			const label = slot.label || `${frappe.datetime.user_to_str(slot.start)} → ${frappe.datetime.user_to_str(slot.end)}`;
			const tabId = `${tabsId}-tab-${i}`;
			const activeLink = i === 0 ? 'active' : '';
			const activePane = i === 0 ? 'show active' : '';

			nav.append(`
		<li class="nav-item" role="presentation" style="flex:0 0 auto;">
		  <a class="nav-link ${activeLink}" data-slot-index="${i}" data-toggle="tab" data-bs-toggle="tab" data-target="#${tabId}" data-bs-target="#${tabId}" href="javascript:void(0)" role="tab" aria-controls="${tabId}" aria-selected="${i === 0 ? 'true' : 'false'}" style="white-space:nowrap;">${label}</a>
		</li>`);

			content.append(`
		<div class="tab-pane fade ${activePane}" id="${tabId}" role="tabpanel" style="padding: 6px;">
		  <button class="btn btn-primary">${__('Pick this slot')}</button>
		</div>`);
		});

		if (slots.length > 3) {
			wrap.append(`<div class="text-muted small mb-1">${__('Scroll horizontally to see more slots')}</div>`);
		}
		container.append(nav);
		container.append(content);
		wrap.append(container);

		// hook click handlers
		const setSelected = (idx) => {
			// clear all
			wrap.find('.tab-pane').removeClass('border border-2 border-success rounded mailcow-slot-selected');
			wrap.find('.nav-link').removeClass('text-success fw-bold');
			// apply to selected pane and its tab link
			const selPaneId = `#${tabsId}-tab-${idx}`;
			wrap.find(selPaneId).addClass('border border-2 border-success rounded mailcow-slot-selected');
			wrap.find(`.nav-link[data-bs-target="${selPaneId}"], .nav-link[data-target="${selPaneId}"]`).addClass('text-success fw-bold');
			// store selection for primary action (prefer local when provided)
			const s = slots[idx];
			if (s) {
				const startUse = s.start_local || s.start;
				const endUse = s.end_local || s.end;
				d.set_value('picked_slot', `${startUse}|${endUse}`);
				try {
					console.log('[Mailcow] Selected slot (tab):', {
						idx,
						start_used: startUse,
						end_used: endUse,
					});
				} catch (e) { }
			}
		};

		slots.forEach((slot, i) => {
			const tabId = `${tabsId}-tab-${i}`;
			wrap.find(`#${tabId} button`).on('click', () => {
				// Prefer local strings from backend when available
				const startUse = slot.start_local || slot.start;
				const endUse = slot.end_local || slot.end;
				d.set_value('picked_slot', `${startUse}|${endUse}`);
				setSelected(i);
				frappe.show_alert({ message: __('Selected: {0} → {1}', [startUse, endUse]), indicator: 'green' });
				try {
					console.log('[Mailcow] Pick button clicked:', {
						idx: i,
						start_used: startUse,
						end_used: endUse,
					});
				} catch (e) { }
			});
		});

		// Selecting a tab also selects the slot
		wrap.on('shown.bs.tab', `.nav-link[data-target^="#${tabsId}-tab-"], .nav-link[data-bs-target^="#${tabsId}-tab-"]`, function () {
			const idx = $(this).data('slotIndex');
			if (idx !== undefined) {
				setSelected(idx);
			}
		});

		// Fallback: ensure selection updates on click even if BS event doesn't fire
		wrap.on('click', `.nav-link[data-target^="#${tabsId}-tab-"], .nav-link[data-bs-target^="#${tabsId}-tab-"]`, function (e) {
			e.preventDefault();
			const idx = $(this).data('slotIndex');
			// Show the tab (Bootstrap 5 or 4)
			try {
				if (window.bootstrap && bootstrap.Tab) {
					new bootstrap.Tab(this).show();
				} else if (typeof $(this).tab === 'function') {
					$(this).tab('show');
				}
			} catch (err) {
				// ignore
			}
			if (idx !== undefined) {
				setSelected(idx);
			}
		});

		// Default select first slot explicitly to ensure highlight applies
		setSelected(0);
	};

	const fetch_slots = () => {
		const v = d.get_values();
		if (!v) return;
		// Convert Time control to HH:MM if provided
		const time_from = v.time_from ? String(v.time_from).slice(0, 5) : undefined;
		const time_to = v.time_to ? String(v.time_to).slice(0, 5) : undefined;
		frappe.call({
			method: 'phamos.mailcow_integration.availability.next_free_slot.free_slots_for_day',
			args: {
				day: v.day,
				duration_minutes: v.duration,
				time_from,
				time_to,
			},
			freeze: true,
			freeze_message: __('Finding free slots...'),
			callback(r) {
				// console.log('[Mailcow] Free slots response:', r.message);
				render_slots(r.message || []);
			}
		});
	};

	// add a secondary button into dialog footer
	d.set_secondary_action(fetch_slots);
	d.set_secondary_action_label(__('Fetch Free Slots'));

	d.show();
	// Auto fetch on open if requested
	if (opts.auto) fetch_slots();
}
