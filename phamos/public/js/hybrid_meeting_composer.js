frappe.provide('erpnext.utils');

(function() {
    // Launcher function
    erpnext.utils.launch_hybrid_meeting_composer = function(opts) {
        new erpnext.utils.HybridMeetingComposer(opts || {});
    };

    erpnext.utils.HybridMeetingComposer = class HybridMeetingComposer {
        constructor(opts) {
            this.doc = opts.doc;
            this.frm = opts.frm;
            this.reference_doctype = this.doc ? this.doc.doctype : opts.reference_doctype;
            this.reference_name = this.doc ? this.doc.name : opts.reference_name;
            this.make_dialog();
        }

        make_dialog() {
            const me = this;
            const default_subject = this._derive_default_subject();

            this.dialog = new frappe.ui.Dialog({
                title: __('Schedule Meeting & Email'),
                fields: [
                    // Hidden meta fields
                    { fieldname: 'reference_doctype', fieldtype: 'Data', default: me.reference_doctype, hidden: 1 },
                    { fieldname: 'reference_name', fieldtype: 'Data', default: me.reference_name, hidden: 1 },
                    { fieldname: 'created_event_name', fieldtype: 'Data', hidden: 1 },

                    // Event Section
                    { fieldname: 'section_event', fieldtype: 'Section Break', label: __('Event Details') },
                    { fieldname: 'subject', fieldtype: 'Data', label: __('Subject'), reqd: 1, default: default_subject },
                    { fieldname: 'event_type', fieldtype: 'Select', label: __('Event Type'), options: 'Private\nPublic', default: 'Private' },
                    { fieldname: 'starts_on', fieldtype: 'Datetime', label: __('Starts On'), reqd: 1 },
                    { fieldname: 'ends_on', fieldtype: 'Datetime', label: __('Ends On'), reqd: 1 },
                    { fieldname: 'duration', fieldtype: 'Select', label: __('Duration (mins)'), options: '15\n30\n45\n60\n90\n120', default: '60' },
                    { fieldname: 'description', fieldtype: 'Text Editor', label: __('Description') },
                    { fieldname: 'sb_slots', fieldtype: 'Section Break', label: __('Fetch Free Slots (Mailcow)'), collapsible: 1 },
                    { fieldname: 'day', fieldtype: 'Date', label: __('Day'), default: frappe.datetime.get_today() },
                    { fieldname: 'duration_minutes', fieldtype: 'Select', label: __('Slot Duration (mins)'), options: '15\n30\n45\n60\n90\n120', default: '60' },
                    { fieldname: 'fetch_slots', fieldtype: 'Button', label: __('Fetch Available Slots') },
                    { fieldname: 'slots_html', fieldtype: 'HTML', options: '<div class="hybrid-slots-placeholder text-muted" style="padding:12px;">'+__('No slots fetched yet.')+'</div>' },

                    // Email Section
                    { fieldname: 'section_email', fieldtype: 'Section Break', label: __('Email Details') },
                    { fieldname: 'to', fieldtype: 'Data', label: __('To (comma separated)'), reqd: 1 },
                    { fieldname: 'cc', fieldtype: 'Data', label: __('CC') },
                    { fieldname: 'bcc', fieldtype: 'Data', label: __('BCC') },
                    { fieldname: 'from', fieldtype: 'Data', label: __('From'), default: (frappe.boot && frappe.boot.user && frappe.boot.user.email) || '' },
                    { fieldname: 'email_subject', fieldtype: 'Data', label: __('Email Subject'), reqd: 1, default: default_subject },
                    { fieldname: 'body', fieldtype: 'Text Editor', label: __('Body'), default: me._default_email_body(default_subject) },
                    { fieldname: 'include_event_details', fieldtype: 'Check', label: __('Append Meeting Details Table'), default: 1 },
                    { fieldname: 'add_signature', fieldtype: 'Check', label: __('Add Signature'), default: 1 },
                ],
                primary_action_label: __('Create Event & Send Email'),
                primary_action: () => {
                    // Placeholder primary action for Phase 1 skeleton
                    frappe.msgprint(__('Primary action logic not yet implemented.'));
                }
            });

            this.dialog.show();
            this.apply_layout();
            this.bind_field_events();
        }

        apply_layout() {
            // Turn dialog wide & create two-column layout by moving DOM nodes
            const $dialog = this.dialog.$wrapper.find('.modal-dialog');
            $dialog.css({ width: '88vw', 'max-width': '88vw' });
            const $body = this.dialog.$wrapper.find('.modal-body');

            // Wrap existing form content
            const $form = $body.find('form');
            const $fields = $form.children('.form-section, .frappe-control');

            const wrapper_html = `
                <div class="hybrid-wrapper" style="display:flex; gap:24px; align-items:stretch;">
                    <div class="hybrid-left" style="flex:1 1 0; min-width:0; display:flex; flex-direction:column; gap:12px;"></div>
                    <div class="hybrid-divider" style="width:1px; background:var(--border-color,#d1d8dd);"></div>
                    <div class="hybrid-right" style="flex:1 1 0; min-width:0; display:flex; flex-direction:column; gap:12px;"></div>
                </div>`;
            // Allow vertical scrolling so email body editing doesn't hide earlier fields
            $body.css({ 'max-height':'80vh', 'overflow-y':'auto', 'overflow-x':'hidden' });
            $form.before(wrapper_html);

            const $left = $body.find('.hybrid-left');
            const $right = $body.find('.hybrid-right');

            // Decide which fields go left vs right by fieldname order
            const eventFieldnames = new Set(['section_event','subject','event_type','starts_on','ends_on','duration','description','sb_slots','day','duration_minutes','fetch_slots','slots_html']);

            $fields.each((i, el) => {
                const $el = $(el);
                const fieldname = $el.attr('data-fieldname');
                if (!fieldname) return;
                if (eventFieldnames.has(fieldname)) {
                    $left.append($el);
                } else {
                    $right.append($el);
                }
            });

            // Add panel headings styling
            this.dialog.$wrapper.append(`
                <style>
                    .hybrid-left .form-section:first-of-type .section-head { font-size:14px; }
                    .hybrid-right .form-section:first-of-type .section-head { font-size:14px; }
                    .hybrid-wrapper .form-section { margin:0; padding:12px 12px 4px; background:#fff; border:1px solid var(--border-color,#d1d8dd); border-radius:4px; }
                    .hybrid-wrapper .frappe-control { margin:0; }
                    .hybrid-wrapper .frappe-control + .frappe-control { margin-top:8px; }
                    .hybrid-wrapper .form-section + .frappe-control { margin-top:8px; }
                    .hybrid-wrapper .form-section + .form-section { margin-top:12px; }
                    .hybrid-wrapper [data-fieldname="body"] .ql-editor { min-height:140px; }
                    .hybrid-slots-badges { display:flex; flex-wrap:wrap; gap:8px; }
                    .hybrid-slot-badge { cursor:pointer; background:#f0f7ff; border:1px solid #c2d9ff; padding:6px 10px; border-radius:16px; font-size:12px; } 
                    .hybrid-slot-badge.active { background:#e1edff; border-color:#94b8ff; }
                </style>
            `);
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

            // Fetch slots button placeholder (no backend call yet)
            d.get_field('fetch_slots').df.click = () => {
                const placeholder = d.get_field('slots_html').$wrapper.find('.hybrid-slots-placeholder');
                if (placeholder.length) {
                    placeholder.html(__('(Slot fetching not wired yet in Phase 1 skeleton)'));
                }
            };
        }

        _derive_default_subject() {
            if (!this.doc) return __('New Meeting');
            return __('Meeting with {0}', [
                this.doc.lead_name || this.doc.customer_name || this.doc.company_name || this.doc.name
            ]);
        }

        _default_email_body(subject) {
            return __("Hello,\n\nI'd like to schedule a meeting. Please see the details below (and attached calendar invite).\n\nRegards,\n") + (frappe.boot && frappe.boot.user && frappe.boot.user.first_name || '');
        }
    };

    // Lead button injection (basic)
    frappe.ui.form.on('Lead', {
        refresh(frm) {
            if (frm.is_new()) return;
            if (!frm.custom_hybrid_button_added) {
                frm.add_custom_button(__('Schedule Meeting & Email'), () => {
                    erpnext.utils.launch_hybrid_meeting_composer({ doc: frm.doc, frm: frm });
                }, __('Create'));
                frm.custom_hybrid_button_added = true;
            }
        }
    });
})();

