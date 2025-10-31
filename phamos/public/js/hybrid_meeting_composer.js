frappe.provide('erpnext.utils');

(function() {
    // Launcher function
    erpnext.utils.launch_hybrid_meeting_composer = function(opts) {
        new erpnext.utils.HybridMeetingComposer(opts || {});
    };

    erpnext.utils.HybridMeetingComposer = class HybridMeetingComposer {
        constructor(opts) {
            // persist context
            this.opts = opts || {};
            this.doc = this.opts.doc || null;
            this.frm = this.opts.frm || null;
            this.reference_doctype = this.opts.reference_doctype || (this.doc ? this.doc.doctype : '');
            this.reference_name = this.opts.reference_name || (this.doc ? this.doc.name : '');
            this.proposals = [];
            this._proposalKeys = new Set();

            this.dialog = new frappe.ui.Dialog({
                title: __('Schedule Meeting & Email'),
                size: 'large',
                minimizable: true,
                fields: [
                    // Hidden meta fields
                    { fieldname: 'reference_doctype', fieldtype: 'Data', hidden: 1 },
                    { fieldname: 'reference_name', fieldtype: 'Data', hidden: 1 },
                    { fieldname: 'created_event_name', fieldtype: 'Data', hidden: 1 },

                    // Single section + two columns
                    { fieldtype: 'Section Break', fieldname: 'main_section', label: __('Schedule Details') },

                    // EMAIL LEFT COLUMN
                    { fieldtype: 'HTML', fieldname: 'email_heading', options: '<div style="font-weight:600; margin-bottom:8px;">'+__('Email')+'</div>' },
                    { label: __('From'), fieldtype: 'Data', fieldname: 'sender', read_only: 1, hidden: 1 },
                    { label: __('To'), fieldtype: 'MultiSelect', fieldname: 'recipients', default: this._default_recipients('recipients') },
                    // { fieldtype: 'Column Break', fieldname: 'cb_1', },
                    {
                        fieldtype: 'Button', fieldname: 'option_toggle_button', label: frappe.utils.icon('down', 'xs'),
                        click: () => {
                            const ccHidden = this.dialog.fields_dict.cc.df.hidden;
                            const newHidden = !ccHidden;
                            ['cc','bcc','email_template','clear_and_add_template','send_after'].forEach(fn => this.dialog.set_df_property(fn, 'hidden', newHidden));
                            this.dialog.get_field('option_toggle_button').set_label(
                                frappe.utils.icon(newHidden ? 'down' : 'up-line', 'xs')
                            );
                        }
                    },
                    
                    { label: __('CC'), fieldtype: 'MultiSelect', fieldname: 'cc', default: this._default_recipients('cc'), hidden: 1 },
                    { label: __('BCC'), fieldtype: 'MultiSelect', fieldname: 'bcc', default: this._default_recipients('bcc'), hidden: 1 },
                    { label: __('Email Template'), fieldtype: 'Link', options: 'Email Template', fieldname: 'email_template', hidden: 1 },
                    { fieldtype: 'HTML', label: __('Template Actions'), fieldname: 'clear_and_add_template', hidden: 1 },
                    { label: __('Schedule Send At'), fieldtype: 'Datetime', fieldname: 'send_after', hidden: 1 },

                    { label: __('Subject'), fieldtype: 'Data', fieldname: 'email_subject' },
                    { label: __('Message'), fieldtype: 'Text Editor', fieldname: 'email_body' },
                    { label: __('Select Attachments'), fieldtype: 'HTML', fieldname: 'select_attachments' },

                    // SWITCH TO RIGHT COLUMN
                    { fieldtype: 'Column Break' },

                    // EVENT RIGHT COLUMN
                    { fieldtype: 'HTML', fieldname: 'event_heading', options: '<div style="font-weight:600; margin-bottom:8px;">'+__('Event')+'</div>' },
                    { label: __('Meeting Subject'), fieldtype: 'Small Text', fieldname: 'subject', reqd: 1, max_height: 70 },
                    { label: __('Event Type'), fieldtype: 'Select', fieldname: 'event_type', options: ['Public', 'Private'], default: 'Private', reqd: 1, hidden: 1 },
                    { label: __('Day to Fetch Slots'), fieldtype: 'Date', fieldname: 'day', default: frappe.datetime.get_today() },
                    { label: __('Duration (minutes)'), fieldtype: 'Select', fieldname: 'duration_minutes', options: ['15', '30', '60', '90', '120'], default: '60' },
                    { fieldname: 'fetch_slots', label: __('Fetch Available Slots'), fieldtype: 'Button' },
                    { fieldname: 'slots_html', fieldtype: 'HTML', options: '<div class="slots-container" style="margin-top: 10px; min-height: 80px;"><div class="hybrid-slots-placeholder text-muted text-center" style="padding: 20px;">'+__('Slots will appear here after fetching.')+'</div></div>' },
                    { fieldtype: 'HTML', fieldname: 'proposals_table', options: `
                        <div class="hybrid-proposals" style="margin-top: 8px;">
                            <div class="text-right" data-role="proposal-toolbar" style="margin-bottom:6px;">
                                <button class="btn btn-xs btn-primary" data-action="add-all-proposals" disabled>${__('Add All')}</button>
                            </div>
                            <table class="table table-bordered" style="border-radius:6px; overflow:hidden;">
                                <thead class="thead-default">
                                    <tr>
                                            <th style="width:34%">${__('Date')}</th>
                                            <th style="width:33%">${__('Start')}</th>
                                            <th style="width:33%">${__('End')}</th>
                                            <th style="width:0%" class="text-right">${__('Add')}</th>
                                    </tr>
                                </thead>
                                <tbody data-role="proposal-rows">
                                </tbody>
                            </table>
                            <div class="text-muted small" data-role="proposal-empty" style="padding: 4px 2px;">${__('No entries yet')}</div>
                        </div>
                    ` },
                    { label: __('Include proposals in email'), fieldtype: 'Check', fieldname: 'include_proposals_in_email', default: 0, hidden: 1 },
                    { label: __('Location'), fieldtype: 'Data', fieldname: 'location' },
                    { label: __('Description'), fieldtype: 'Text Editor', fieldname: 'description', max_height: 150 }
                ],
                primary_action_label: __('Create Event & Send Email'),
                primary_action: () => this._submit()
            });

            this.dialog.show();
            // set hidden meta fields now
            if (this.reference_doctype) this.dialog.set_value('reference_doctype', this.reference_doctype);
            if (this.reference_name) this.dialog.set_value('reference_name', this.reference_name);
            this.apply_layout();
            this._init_email_sender_options();
            this._init_email_template_actions();
            this._init_email_multiselect_queries();
            this.bind_field_events();
            this._prefill_to_from_lead();
            this._init_attachments_uploader();
        }

        _get_selected_attachments() {
            const wrap = $(this.dialog.fields_dict.select_attachments.wrapper);
            const selected = [];
            wrap.find('input[type="checkbox"][data-file-name]:checked').each((i, el) => {
                const fid = $(el).attr('data-file-name');
                if (fid) selected.push(fid);
            });
            return selected;
        }

        _submit() {
            const d = this.dialog;
            const recipients = (d.get_value('recipients') || '').trim();
            const subject = (d.get_value('subject') || '').trim();
            const email_subject = (d.get_value('email_subject') || '').trim();
            const email_body = d.get_value('email_body') || '';
            const cc = (d.get_value('cc') || '').trim();
            const bcc = (d.get_value('bcc') || '').trim();
            const sender = (d.get_value('sender') || '').trim();
            const send_after = d.get_value('send_after') || null;
            const location = d.get_value('location') || '';

            if (!recipients) { frappe.msgprint(__('Please add at least one recipient.')); return; }
            if (!subject && !email_subject) { frappe.msgprint(__('Please add a subject.')); return; }
            if (!this.proposals || !this.proposals.length) { frappe.msgprint(__('Please select at least one time slot as a proposal.')); return; }

            const payload = {
                reference_doctype: this.reference_doctype,
                reference_name: this.reference_name,
                subject,
                location,
                email_subject: email_subject || subject,
                email_body,
                recipients,
                cc,
                bcc,
                sender,
                send_after,
                proposals: this.proposals,
                include_proposals_in_email: this.dialog.get_value('include_proposals_in_email') ? 1 : 0,
                attachments: this._get_selected_attachments(),
            };

            const btn = this.dialog.get_primary_btn();
            btn.prop('disabled', true).text(__('Submitting...'));
            frappe.call({
                method: 'phamos.mailcow_integration.hybrid_meeting.create_proposals_and_send_email',
                args: { payload: JSON.stringify(payload) },
                callback: (r) => {
                    if (r.exc) return;
                    frappe.show_alert({ message: __('Proposals sent and tentative events created.'), indicator: 'green' });
                    this.dialog.hide();
                },
                always: () => {
                    btn.prop('disabled', false).text(__('Create Event & Send Email'));
                }
            });
        }

        apply_layout() {
            // Just set wide width and allow vertical scrolling; use native Column Breaks for layout
            const $dialog = this.dialog.$wrapper.find('.modal-dialog');
            $dialog.css({ width: '88vw', 'max-width': '88vw' });
            const $body = this.dialog.$wrapper.find('.modal-body');
            $body.css({ 'max-height':'80vh', 'overflow-y':'auto', 'overflow-x':'hidden' });

            // Inline toggle button with the To field
            const toWrapper = $(this.dialog.fields_dict.recipients?.wrapper);
            const toggleFieldWrapper = $(this.dialog.fields_dict.option_toggle_button?.wrapper);
            if (toWrapper.length && toggleFieldWrapper.length) {
                const $inputArea = toWrapper.find('.control-input');
                const $btn = toggleFieldWrapper.find('button');
                // hide button label and remove wrapper margins to avoid vertical offset
                toggleFieldWrapper.find('.control-label').css('display','none');
                toggleFieldWrapper.css({ margin: 0, padding: 0 });

                if ($inputArea.length && $btn.length) {
                    $inputArea.css({ display: 'flex', 'align-items': 'center', gap: '3px' });
                    // primary input flexes to fill
                    const firstChild = $inputArea.children().first();
                    firstChild.css({ flex: '1 1 auto' });
                    // create (or reuse) a slim inline container for the button
                    let $inline = $inputArea.find('.toggle-inline-container');
                    if (!$inline.length) {
                        $inline = $('<div class="toggle-inline-container"></div>').css({ flex: '0 0 8%', 'min-width': '36px', display: 'flex', 'justify-content': 'flex-end', 'align-items': 'center' });
                        $inputArea.append($inline);
                    }
                    // move the button into the inline container
                    $inline.empty().append($btn.css({ width: '32px', height: '28px', padding: '2px 4px', margin: 0 }));
                }
            }

            // Align slot controls on one line and center
            const dayW = $(this.dialog.fields_dict.day?.wrapper);
            const durW = $(this.dialog.fields_dict.duration_minutes?.wrapper);
            const fetchW = $(this.dialog.fields_dict.fetch_slots?.wrapper);
            if (dayW.length && durW.length && fetchW.length) {
                const row = $('<div class="form-grid three-col" style="display:flex; gap:8px; justify-content:center; align-items:flex-end; margin-top:4px;"></div>');
                dayW.css({ width: 'auto', flex: '0 1 200px' });
                durW.css({ width: 'auto', flex: '0 1 160px' });
                fetchW.css({ width: 'auto', flex: '0 0 auto' });
                row.append(dayW).append(durW).append(fetchW);
                // insert before slots_html
                $(this.dialog.fields_dict.slots_html.wrapper).before(row);
            }

            // Start/End side-by-side
            const startW = $(this.dialog.fields_dict.starts_on?.wrapper);
            const endW = $(this.dialog.fields_dict.ends_on?.wrapper);
            if (startW.length && endW.length && !startW.parent().is('.start-end-row')) {
                const row2 = $('<div class="start-end-row" style="display:flex; gap:8px; align-items:flex-end; margin-top:8px;"></div>');
                startW.css({ width: 'auto', flex: '1 1 50%' });
                endW.css({ width: 'auto', flex: '1 1 50%' });
                row2.append(startW).append(endW);
                $(this.dialog.fields_dict.description.wrapper).before(row2);
            }

            // Email Template + actions on one row with actions on the right
            const templateW = $(this.dialog.fields_dict.email_template?.wrapper);
            const actionsW = $(this.dialog.fields_dict.clear_and_add_template?.wrapper);
            if (templateW.length && actionsW.length && !templateW.parent().is('.template-row')) {
                const row3 = $('<div class="template-row" style="display:flex; gap:8px; align-items:center; margin-top:8px;"></div>');
                // hide labels to align inputs and actions perfectly on a single baseline
                templateW.find('.control-label').css('display','none');
                actionsW.find('.control-label').css('display','none');
                templateW.css({ width: 'auto', flex: '1 1 70%', 'margin-top': 0, padding: 0 });
                actionsW.css({ width: 'auto', flex: '0 0 auto', 'margin-left': 'auto', display: 'flex', 'align-items': 'center', 'margin-top': 0, padding: 0 });
                row3.append(templateW).append(actionsW);
                // place before Subject field to keep group together
                $(this.dialog.fields_dict.email_subject.wrapper).before(row3);
            }
        }

        bind_field_events() {
            const d = this.dialog;
            // Keep email_subject synced if user hasn't manually changed it yet
            let emailSubjectTouched = false;
            d.get_field('email_subject').df.onchange = () => { emailSubjectTouched = true; };
            d.get_field('subject').df.onchange = () => {
                if (!emailSubjectTouched) {
                    d.set_value('email_subject', d.get_value('subject'));
                }
            };

            // Fetch slots button: call backend and render slots
            d.get_field('fetch_slots').df.click = () => {
                const day = d.get_value('day');
                const duration = d.get_value('duration_minutes');
                const $container = d.get_field('slots_html').$wrapper.find('.slots-container');
                if (!day) { frappe.msgprint(__('Please select a day to fetch slots.')); return; }
                if (!duration) { frappe.msgprint(__('Please select duration.')); return; }

                $container.html('<div class="text-muted text-center" style="padding: 20px;">'+__('Fetching slots...')+'</div>');

                frappe.call({
                    method: 'phamos.mailcow_integration.availability.next_free_slot.free_slots_for_day',
                    args: {
                        day: day,
                        duration_minutes: duration
                    },
                    callback: (r) => {
                        if (!r.exc && r.message) {
                            this._render_slots(r.message);
                        } else {
                            const err = r && r.exc ? r.exc : __('No slots available.');
                            $container.html(`<div class="text-danger text-center" style="padding: 20px;">${err}</div>`);
                        }
                    }
                });
            };

            // proposal rows: Add to email content
            const table_wrap = $(d.fields_dict.proposals_table.wrapper);
            table_wrap.off('.proposal-actions');
            table_wrap.on('click.proposal-actions', '[data-action="add-proposal"]', (e) => {
                const $tr = $(e.currentTarget).closest('tr');
                const start = $tr.data('start');
                const end = $tr.data('end');
                if (!start || !end) return;

                // Use System Settings date format for Date and HH:mm for times
                let mStart = window.moment ? moment(start, 'YYYY-MM-DD HH:mm:ss', true) : null;
                let mEnd = window.moment ? moment(end, 'YYYY-MM-DD HH:mm:ss', true) : null;
                if (!mStart || !mStart.isValid()) mStart = window.moment ? moment(start) : null;
                if (!mEnd || !mEnd.isValid()) mEnd = window.moment ? moment(end) : null;
                const sysFmt = (frappe.sys_defaults && frappe.sys_defaults.date_format) || (frappe.boot && frappe.boot.sysdefaults && frappe.boot.sysdefaults.date_format) || '';
                const toMomentFmt = (fmt) => {
                    if (!fmt) return 'MMM D, YYYY';
                    return fmt
                        .replace(/yyyy/g, 'YYYY')
                        .replace(/yy/g, 'YY')
                        .replace(/mm/g, 'MM')
                        .replace(/m/g, 'M')
                        .replace(/dd/g, 'DD')
                        .replace(/d/g, 'D');
                };
                const dateFmt = toMomentFmt(sysFmt);
                const dateStr = mStart && mStart.isValid() ? mStart.format(dateFmt) : start;
                const startStr = mStart && mStart.isValid() ? mStart.format('HH:mm') : start;
                const endStr = mEnd && mEnd.isValid() ? mEnd.format('HH:mm') : end;

                // Insert into a proposals table in the email body (create if missing)
                const current = d.get_value('email_body') || '';
                const $dom = $('<div></div>').html(current);
                const $existing = $dom.find('table[data-proposals-table="1"]');
                const rowHtml = `<tr><td>${frappe.utils.escape_html(dateStr)}</td><td>${frappe.utils.escape_html(startStr)}</td><td>${frappe.utils.escape_html(endStr)}</td></tr>`;
                if ($existing.length) {
                    const $tbody = $existing.find('tbody').first();
                    $tbody.append(rowHtml);
                    d.set_value('email_body', $dom.html());
                } else {
                    const header = `
                        <table class="table table-bordered" data-proposals-table="1" style="margin-top:8px; width:100%; border-collapse: collapse;">
                            <tbody>
                                <tr>
                                    <td><strong>${__('Date')}</strong></td>
                                    <td><strong>${__('Start')}</strong></td>
                                    <td><strong>${__('End')}</strong></td>
                                </tr>
                            </tbody>
                        </table>
                    `;
                    const tableHtml = header.replace('</tbody>', `${rowHtml}</tbody>`);
                    const sep = current && !current.endsWith('\n') ? '<br>' : '';
                    d.set_value('email_body', `${current}${sep}${tableHtml}`);
                }
            });

            // Add All -> insert/merge a table in the email body
            table_wrap.on('click.proposal-actions', '[data-action="add-all-proposals"]', (e) => {
                e.preventDefault();
                if (!this.proposals || !this.proposals.length) return;

                // Build display entries
                const sysFmt = (frappe.sys_defaults && frappe.sys_defaults.date_format) || (frappe.boot && frappe.boot.sysdefaults && frappe.boot.sysdefaults.date_format) || '';
                const toMomentFmt = (fmt) => {
                    if (!fmt) return 'MMM D, YYYY';
                    return fmt
                        .replace(/yyyy/g, 'YYYY')
                        .replace(/yy/g, 'YY')
                        .replace(/mm/g, 'MM')
                        .replace(/m/g, 'M')
                        .replace(/dd/g, 'DD')
                        .replace(/d/g, 'D');
                };
                const dateFmt = toMomentFmt(sysFmt);
                const displayRows = this.proposals.map(r => {
                    let mStart = window.moment ? moment(r.start, 'YYYY-MM-DD HH:mm:ss', true) : null;
                    let mEnd = window.moment ? moment(r.end, 'YYYY-MM-DD HH:mm:ss', true) : null;
                    if (!mStart || !mStart.isValid()) mStart = window.moment ? moment(r.start) : null;
                    if (!mEnd || !mEnd.isValid()) mEnd = window.moment ? moment(r.end) : null;
                    const dateStr = mStart && mStart.isValid() ? mStart.format(dateFmt) : (r.start || '').slice(0, 10);
                    const startStr = mStart && mStart.isValid() ? mStart.format('HH:mm') : (r.start || '');
                    const endStr = mEnd && mEnd.isValid() ? mEnd.format('HH:mm') : (r.end || '');
                    return { dateStr, startStr, endStr };
                });

                let current = d.get_value('email_body') || '';
                const $dom = $('<div></div>').html(current);
                const $existing = $dom.find('table[data-proposals-table="1"]');
                if ($existing.length) {
                    // Rebuild the entire proposals table to normalize date format
                    const header = `
                        <table class="table table-bordered" data-proposals-table="1" style="margin-top:8px; width:100%; border-collapse: collapse;">
                            <tbody>
                                <tr>
                                    <td><strong>${__('Date')}</strong></td>
                                    <td><strong>${__('Start')}</strong></td>
                                    <td><strong>${__('End')}</strong></td>
                                </tr>
                            </tbody>
                        </table>
                    `;
                    const rowsHtml = displayRows.map(r => `<tr><td>${frappe.utils.escape_html(r.dateStr)}</td><td>${frappe.utils.escape_html(r.startStr)}</td><td>${frappe.utils.escape_html(r.endStr)}</td></tr>`).join('');
                    const tableHtml = header.replace('</tbody>', `${rowsHtml}</tbody>`);
                    $existing.replaceWith(tableHtml);
                    d.set_value('email_body', $dom.html());
                } else {
                    // build a simple table with a bold header row in tbody for better editor compatibility
                    const header = `
                        <table class="table table-bordered" data-proposals-table="1" style="margin-top:8px; width:100%; border-collapse: collapse;">
                            <tbody>
                                <tr>
                                    <td><strong>${__('Date')}</strong></td>
                                    <td><strong>${__('Start')}</strong></td>
                                    <td><strong>${__('End')}</strong></td>
                                </tr>
                            </tbody>
                        </table>
                    `;
                    const rowsHtml = displayRows.map(r => `<tr><td>${frappe.utils.escape_html(r.dateStr)}</td><td>${frappe.utils.escape_html(r.startStr)}</td><td>${frappe.utils.escape_html(r.endStr)}</td></tr>`).join('');
                    const tableHtml = header.replace('</tbody>', `${rowsHtml}</tbody>`);
                    const sep = current && !current.endsWith('\n') ? '<br>' : '';
                    d.set_value('email_body', `${current}${sep}${tableHtml}`);
                }
            });
        }

        _default_email_body() {
            const name = (frappe.boot?.user?.first_name || '').trim();
            return (
                __("Hello,") +
                "<br><br>" +
                __("I'd like to schedule a meeting. Please see the details below (and attached calendar invite).") +
                "<br><br>" +
                __("Regards,") +
                "<br>" + frappe.utils.escape_html(name)
            );
        }

        _default_recipients(fieldname) {
            if (this.frm?.events?.get_email_recipients) {
                return (this.frm.events.get_email_recipients(this.frm, fieldname) || []).join(', ');
            }
            return '';
        }

        _prefill_to_from_lead() {
            const to =
                this.doc?.email_id ||
                this.doc?.email ||
                this.doc?.contact_email ||
                this.doc?.lead_email ||
                '';
            if (to) this.dialog.set_value('recipients', to);
        }

        _init_email_sender_options() {
            // Prefill read-only sender from lead_owner or session user
            let sender_email = '';
            const owner = this.doc?.lead_owner || this.doc?.owner;
            const contacts = (frappe.boot?.user_info) || {};
            if (owner && contacts[owner]?.email) sender_email = contacts[owner].email;
            if (!sender_email) sender_email = frappe.session.user_email || '';
            this.dialog.set_value('sender', sender_email);
        }

        _init_email_template_actions() {
            const $wrap = $(this.dialog.fields_dict.clear_and_add_template.wrapper);
            $wrap.empty();

            const add_template = () => {
                const template = this.dialog.get_value('email_template');
                if (!template) return;
                frappe.call({
                    method: 'frappe.email.doctype.email_template.email_template.get_email_template',
                    args: { template_name: template, doc: this.doc },
                    callback: (r) => {
                        if (!r.message) return;
                        const current = this.dialog.get_value('email_body') || '';
                        this.dialog.set_value('email_body', `${r.message.message}<br>${current}`);
                        this.dialog.set_value('email_subject', r.message.subject || this.dialog.get_value('email_subject'));
                    }
                });
            };

            const actions = [
                {
                    label: __('Add Template'),
                    description: __('Prepend the template to the email message'),
                    action: () => add_template(),
                },
                {
                    label: __('Clear & Add Template'),
                    description: __('Clear the email message and add the template'),
                    action: () => { this.dialog.set_value('email_body', ''); add_template(); },
                }
            ];

            frappe.utils.add_select_group_button($wrap, actions);
        }

        _init_email_multiselect_queries() {
            ['recipients', 'cc', 'bcc'].forEach((field) => {
                const ctrl = this.dialog.fields_dict[field];
                if (!ctrl) return;
                ctrl.get_data = () => {
                    const data = ctrl.get_value();
                    const match = data ? data.match(/[^,\s*]*$/) : null;
                    const txt = (match && match[0]) || '';
                    const args = { txt };
                    if (this.frm?.events?.get_email_recipient_filters) {
                        args.extra_filters = this.frm.events.get_email_recipient_filters(this.frm, field);
                    }
                    frappe.call({
                        method: 'frappe.email.get_contact_list',
                        args,
                        callback: (r) => ctrl.set_data(r.message || [])
                    });
                };
            });

            // If any of the optional fields have values, show them
            const showOptions = ['cc','bcc','email_template','send_after'].some(fn => !!this.dialog.get_value(fn));
            if (showOptions) {
                ['cc','bcc','email_template','clear_and_add_template','send_after'].forEach(fn => this.dialog.set_df_property(fn, 'hidden', 0));
                this.dialog.get_field('option_toggle_button').set_label(frappe.utils.icon('up-line','xs'));
            }
        }

        _init_attachments_uploader() {
            const field = this.dialog.fields_dict.select_attachments;
            const wrap = $(field.wrapper);
            wrap.empty().append(`
                <label class="control-label">${__('Select Attachments')}</label>
                <div class="attach-list"></div>
                <p class='add-more-attachments'>
                    <button class='btn btn-xs btn-default'>
                        ${frappe.utils.icon('small-add', 'xs')}&nbsp;${__('Add Attachment')}
                    </button>
                </p>
            `);

            const on_success = (attachment) => {
                if (this.frm && this.frm.attachments) {
                    this.frm.attachments.attachment_uploaded(attachment);
                } else {
                    if (!this.attachments) this.attachments = [];
                    this.attachments.push(attachment);
                }
                this._render_attachment_rows(attachment);
            };

            const args = this.frm
                ? { doctype: this.frm.doctype, docname: this.frm.docname, folder: 'Home/Attachments', on_success }
                : { folder: 'Home/Attachments', on_success };

            wrap.find('.add-more-attachments button').on('click', () => new frappe.ui.FileUploader(args));
            this._render_attachment_rows();
        }

        _render_attachment_rows(attachment) {
            const attach_wrap = $(this.dialog.fields_dict.select_attachments.wrapper).find('.attach-list');
            const add_row = (a, checked) => {
                attach_wrap.append($(
                    `<p class="checkbox flex">
                        <label title="${a.file_name}" style="max-width: 100%">
                            <input type="checkbox" data-file-name="${a.name}" ${checked ? 'checked' : ''}>
                            <span class="ellipsis" style="max-width: calc(100% - var(--checkbox-size) - var(--checkbox-right-margin) - var(--padding-xs) - 16px)">
                                ${a.file_name}
                            </span>
                            <a href="${frappe.urllib.get_full_url(a.file_url)}" target="_blank" class="btn-link" style="padding-left: var(--padding-xs)">
                                ${frappe.utils.icon('link-url', 'sm')}
                            </a>
                        </label>
                    </p>`
                ));
            };

            if (attachment) { add_row(attachment, true); return; }

            let files = [];
            if (this.attachments?.length) files = files.concat(this.attachments);
            if (this.frm) files = files.concat(this.frm.get_files());
            files.forEach((f) => {
                if (!f.file_name) return;
                if (!attach_wrap.find(`[data-file-name="${f.name}"]`).length) add_row(f, false);
            });
        }

        // Render slots horizontally and enable multi-select (Phase 2)
        _render_slots(slots) {
            const d = this.dialog;
            const $container = d.get_field('slots_html').$wrapper.find('.slots-container');

            if (!slots || !slots.length) {
                $container.html('<div class="text-muted text-center" style="padding: 20px;">'+__('No available slots found.')+'</div>');
                return;
            }

            const slotHtml = slots.map((slot, idx) => {
                // prefer local strings from backend
                let mStart = window.moment ? moment(slot.start_local, 'YYYY-MM-DD HH:mm:ss', true) : null;
                let mEnd = window.moment ? moment(slot.end_local, 'YYYY-MM-DD HH:mm:ss', true) : null;
                if (!mStart || !mStart.isValid()) mStart = window.moment ? moment(slot.start_local) : null;
                if (!mEnd || !mEnd.isValid()) mEnd = window.moment ? moment(slot.end_local) : null;
                const start_db = mStart && mStart.isValid() ? mStart.format('YYYY-MM-DD HH:mm:ss') : (slot.start_local || slot.start);
                const end_db = mEnd && mEnd.isValid() ? mEnd.format('YYYY-MM-DD HH:mm:ss') : (slot.end_local || slot.end);
                const dateDisp = mStart && mStart.isValid() ? mStart.format('ddd DD') : '';
                const rangeDisp = mStart && mEnd && mStart.isValid() && mEnd.isValid()
                    ? `${mStart.format('HH:mm')} - ${mEnd.format('HH:mm')}`
                    : `${frappe.utils.escape_html(start_db)} → ${frappe.utils.escape_html(end_db)}`;
                return `
                    <div class="slot-chip" data-index="${idx}" data-start="${start_db}" data-end="${end_db}"
                        style="display:inline-block; margin:6px; padding:10px 14px; background:#f0f7ff; border:1px solid #c2d9ff; border-radius:6px; white-space:nowrap; cursor:pointer; text-align:center; min-width:120px;">
                        <div style="font-size:12px; color:#666; margin-bottom:2px;">${dateDisp}</div>
                        <strong style="font-size:13px; display:block;">${rangeDisp}</strong>
                    </div>`;
            }).join('');

            $container.html(`
                <div class="slots-scroll" style="width:100%; overflow-x:auto; white-space:nowrap; padding:6px 0; text-align:center;">
                    <div style="display:inline-block;">${slotHtml}</div>
                </div>
                <div class="text-center" style="margin-top:6px;"><small class="text-muted">${__('Click to add/remove from proposals')}</small></div>
            `);

            const toggleSelected = ($el, add) => {
                $el.css({ background: add ? '#e8f5e8' : '#f0f7ff', borderColor: add ? '#4CAF50' : '#c2d9ff' });
            };

            $container.find('.slot-chip').on('click', (e) => {
                const $el = $(e.currentTarget);
                const start = $el.attr('data-start');
                const end = $el.attr('data-end');
                const key = `${start}__${end}`;
                if (this._proposalKeys.has(key)) {
                    // remove
                    this._remove_proposal(start, end);
                    toggleSelected($el, false);
                } else {
                    // add
                    this._add_proposal(start, end);
                    toggleSelected($el, true);
                }
            });
        }

        _add_proposal(start, end) {
            const key = `${start}__${end}`;
            if (this._proposalKeys.has(key)) return;
            this._proposalKeys.add(key);
            this.proposals.push({ start, end });
            this._render_proposals(this.proposals);
            // show include checkbox if proposals exist
            this.dialog.set_df_property('include_proposals_in_email', 'hidden', this.proposals.length ? 0 : 1);
        }

        _remove_proposal(start, end) {
            const key = `${start}__${end}`;
            if (!this._proposalKeys.has(key)) return;
            this._proposalKeys.delete(key);
            this.proposals = this.proposals.filter(r => !(r.start === start && r.end === end));
            this._render_proposals(this.proposals);
            this.dialog.set_df_property('include_proposals_in_email', 'hidden', this.proposals.length ? 0 : 1);
        }

        // helper to render proposal rows with Add action (Phase 2)
        _render_proposals(rows) {
            const wrap = $(this.dialog.fields_dict.proposals_table.wrapper);
            const tbody = wrap.find('[data-role="proposal-rows"]').empty();
            const empty = wrap.find('[data-role="proposal-empty"]');
            const addAllBtn = wrap.find('[data-action="add-all-proposals"]');
            // derive user/system date format for display in the dialog table only
            const sysFmt = (frappe.sys_defaults && frappe.sys_defaults.date_format) || (frappe.boot && frappe.boot.sysdefaults && frappe.boot.sysdefaults.date_format) || '';
            const toMomentFmt = (fmt) => {
                if (!fmt) return 'MMM D, YYYY';
                return fmt
                    .replace(/yyyy/g, 'YYYY')
                    .replace(/yy/g, 'YY')
                    .replace(/mm/g, 'MM')
                    .replace(/m/g, 'M')
                    .replace(/dd/g, 'DD')
                    .replace(/d/g, 'D');
            };
            const dateFmt = toMomentFmt(sysFmt);
            if (!rows || !rows.length) {
                empty.show();
                addAllBtn.prop('disabled', true);
                this.dialog.set_df_property('include_proposals_in_email', 'hidden', 1);
                return;
            }
            empty.hide();
            addAllBtn.prop('disabled', false);
            this.dialog.set_df_property('include_proposals_in_email', 'hidden', 0);
            rows.forEach(r => {
                // Format: Date col = 'MMM D, YYYY'; Start/End = 'HH:mm'
                const mStart = window.moment ? moment(r.start, 'YYYY-MM-DD HH:mm:ss', true) : null;
                const mEnd = window.moment ? moment(r.end, 'YYYY-MM-DD HH:mm:ss', true) : null;
                const startValid = mStart && mStart.isValid();
                const endValid = mEnd && mEnd.isValid();
                const dateDisp = startValid ? mStart.format(dateFmt) : frappe.utils.escape_html(r.start);
                const startDisp = startValid ? mStart.format('HH:mm') : frappe.utils.escape_html(r.start);
                const endDisp = endValid ? mEnd.format('HH:mm') : frappe.utils.escape_html(r.end);

                const tr = $(`
                    <tr data-start="${r.start}" data-end="${r.end}">
                        <td>${dateDisp}</td>
                        <td>${startDisp}</td>
                        <td>${endDisp}</td>
                        <td class="text-right">
                            <button class="btn btn-xs btn-primary" data-action="add-proposal">${__('Add')}</button>
                        </td>
                    </tr>
                `);
                tbody.append(tr);
            });
        }
    };

    // Lead button injection (basic)
    frappe.ui.form.on('Lead', {
        refresh(frm) {
            if (frm.is_new()) return;
            if (!frm.custom_hybrid_button_added) {
                frm.add_custom_button(__('Schedule Meeting & Email'), () => {
                    erpnext.utils.launch_hybrid_meeting_composer({ doc: frm.doc, frm: frm });
                });
                frm.custom_hybrid_button_added = true;
            }
        }
    });

    // Opportunity button injection
    frappe.ui.form.on('Opportunity', {
        refresh(frm) {
            if (frm.is_new()) return;
            if (!frm.custom_hybrid_button_added) {
                frm.add_custom_button(__('Schedule Meeting & Email'), () => {
                    erpnext.utils.launch_hybrid_meeting_composer({ doc: frm.doc, frm: frm });
                });
                frm.custom_hybrid_button_added = true;
            }
        }
    });
})();

