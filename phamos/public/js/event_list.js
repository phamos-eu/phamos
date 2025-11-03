function add_mailcow_pull_button(listview) {
    // Avoid duplicate button
    const group_label = __('Mailcow');
    const btn_label = __('Pull Events');
    const already = listview.page.inner_toolbar && listview.page.inner_toolbar.find(`.btn-group:contains(${group_label}) button:contains(${btn_label})`).length;
    if (already) return;

    listview.page.add_inner_button(btn_label, () => {
            const today = frappe.datetime.get_today();
            const default_end = frappe.datetime.add_days(today, 30);

            const d = new frappe.ui.Dialog({
                title: __('Pull Mailcow Events'),
                fields: [
                    {
                        fieldname: 'start',
                        fieldtype: 'Date',
                        reqd: 1,
                        label: __('Start Date'),
                        default: today
                    },
                    {
                        fieldname: 'end',
                        fieldtype: 'Date',
                        reqd: 1,
                        label: __('End Date'),
                        default: default_end
                    }
                ],
                primary_action_label: __('Pull'),
                primary_action(values) {
                    if (frappe.datetime.get_diff(values.end, values.start) > 90) {
                        frappe.msgprint(__('Range too large (max 90 days).'));
                        return;
                    }
                    d.hide();
                    frappe.call({
                        method: 'phamos.mailcow_integration.caldav.sync_event.pull_events',
                        args: {
                            start: values.start + 'T00:00:00',
                            end: values.end + 'T23:59:59',
                            selected_events: (listview.get_checked_items() || []).map(e => e.name)
                        },
                        freeze: true,
                        freeze_message: __('Pulling Mailcow events...'),
                        callback(r) {
                            if (r.message) {
                                frappe.show_alert({
                                    message: __('Pulled {0} events from Mailcow', [r.message.length || r.message.count || 0]),
                                    indicator: 'green'
                                });
                                listview.refresh();
                            } else {
                                frappe.msgprint(__('No events were returned.'));
                            }
                        }
                    });
                }
            });
            d.show();
    }, group_label);
}

frappe.listview_settings['Event'] = {
    onload(listview) {
        add_mailcow_pull_button(listview);
    },
    refresh(listview) {
        add_mailcow_pull_button(listview);
    }
};