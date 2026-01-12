frappe.provide('erpnext.utils');

// Save a reference to the original class
erpnext.utils.OriginalCRMActivities = erpnext.utils.CRMActivities;

// Define the new class that extends the original
erpnext.utils.CRMActivities = class CustomCRMActivities extends erpnext.utils.OriginalCRMActivities {
    
    create_event() {
        let me = this;
        let _create_event = () => {
            let custom_dialog = new frappe.ui.Dialog({
                title: __('New Event'),
                fields: [
                    {
                        fieldname: 'subject',
                        label: __('Subject'),
                        fieldtype: 'Small Text',
                        reqd: 1,
                        max_height: 70,
                        default: `Meeting with ${me.frm.doc.lead_name || me.frm.doc.customer_name || me.frm.doc.name}`
                    },
                    {
                        fieldname: 'column_break_1',
                        fieldtype: 'Column Break'
                    },
                    {
                        fieldname: 'event_type',
                        label: __('Event Type'),
                        fieldtype: 'Select',
                        options: ['Public', 'Private'],
                        default: 'Private',
                        reqd: 1
                    },
                    {
                        fieldname: 'section_break_1',
                        fieldtype: 'Section Break',
                        label: __('Fetch Free Slots (Mailcow)'),
                        collapsible: 1
                    },
                    {
                        fieldname: 'day',
                        label: __('Day to Fetch Slots'),
                        fieldtype: 'Date',
                        default: frappe.datetime.get_today(),
                    },
                    {
                        fieldname: 'column_break_2',
                        fieldtype: 'Column Break'
                    },
                    {
                        fieldname: 'duration',
                        label: __('Duration (minutes)'),
                        fieldtype: 'Select',
                        options: ['15', '30', '60', '90', '120'],
                        default: '60',
                    },
                    {
                        fieldname: 'column_break_3',
                        fieldtype: 'Column Break'
                    },
                    {
                    fieldname: 'fetch_slots',
                    label: __('Fetch Available Slots'),
                    fieldtype: 'Button',
                    click: function() {
                        // Get values individually to avoid validation of Start/End Date
                        let day = custom_dialog.get_value('day');
                        let duration = custom_dialog.get_value('duration');
                        let time_from = custom_dialog.get_value('time_from');
                        let time_to = custom_dialog.get_value('time_to');

                        // Validate only the required fields for fetching slots
                        if (!day) {
                            frappe.msgprint(__('Please select a day to fetch slots.'));
                            return;
                        }
                        if (!duration) {
                            frappe.msgprint(__('Please select duration.'));
                            return;
                        }

                        // Show a loading indicator
                        let slotsContainer = custom_dialog.fields_dict.slots_container.$wrapper;
                        slotsContainer.html('<div class="text-muted text-center">Fetching slots...</div>');

                        // Convert Time control to HH:MM if provided
                        if (time_from) time_from = String(time_from).slice(0, 5);
                        if (time_to) time_to = String(time_to).slice(0, 5);

                        // Call the Mailcow Sogo API to fetch available slots
                        frappe.call({
                            method: 'phamos.mailcow_integration.availability.next_free_slot.free_slots_for_day',
                            args: {
                                day: day,
                                duration_minutes: duration,
                                time_from: time_from,
                                time_to: time_to,
                            },
                            callback: function(r) {
                                if (!r.exc && r.message) {
                                    console.log('[Mailcow] Free slots response:', r.message);
                                    me.displaySlots(r.message, slotsContainer, custom_dialog);
                                } else {
                                    let errorMsg = r.exc ? __('Error fetching slots: {0}', [r.exc]) : __('No slots available.');
                                    slotsContainer.html(`<div class="text-danger text-center">${errorMsg}</div>`);
                                }
                            }
                        });
                    }
                },
                {
                    fieldname: 'section_break_2',
                    fieldtype: 'Section Break',
                },
                {
                    fieldname: 'slots_container', 
                    fieldtype: 'HTML',
                    options: `<div class="slots-container" style="margin-top: 10px; min-height: 80px;">
                                <div class="text-muted text-center" style="padding: 20px;">
                                    Slots will appear here after fetching.
                                </div>
                            </div>`
                },
                    {
                        fieldname: 'section_break_3',
                        fieldtype: 'Section Break',
                        label: __('Event Timing')
                    },
                    {
                        fieldname: 'starts_on',
                        label: __('Start Date'),
                        fieldtype: 'Datetime',
                        reqd: 1  // Required only for final submission
                    },
                    {
                        fieldname: 'column_break_4',
                        fieldtype: 'Column Break'
                    },
                    {
                        fieldname: 'ends_on', 
                        label: __('End Date'),
                        fieldtype: 'Datetime',
                        reqd: 1  // Required only for final submission
                    },
                    {
                        fieldname: 'section_break_4',
                        fieldtype: 'Section Break'
                    },
                    {
                        fieldname: 'description',
                        label: __('Description'),
                        fieldtype: 'Text Editor',
                        max_height: 150
                    },
                    
                ],
                primary_action: function(values) {
                    // Validate that start and end dates are filled before creating event
                    if (!values.starts_on || !values.ends_on) {
                        frappe.msgprint(__('Please fill Start Date and End Date before creating the event.'));
                        return;
                    }

                    console.log('Event details:', me.frm.doc.doctype, me.frm.doc.name);
                    

                    // Create the event document directly
                    let event_doc = {
                        doctype: 'Event',
                        subject: values.subject,
                        starts_on: values.starts_on,
                        ends_on: values.ends_on,
                        description: values.description || '',
                        event_participants: [
                            {
                                reference_doctype: me.frm.doc.doctype,
                                reference_docname: me.frm.doc.name,
                                email_id: me.frm.doc.email || me.frm.doc.contact_email || '',
                            },
                            {
                                reference_doctype: 'Prospect',
                                reference_docname: me.frm.doc.company,
                                email_id: me.frm.doc.lead_owner || '',

                            }
                        ],
                        event_type: values.event_type,
                        
                    };

                    // Save the event
                    frappe.call({
                        method: 'frappe.client.insert',
                        args: {
                            doc: event_doc
                        },
                        callback: function(r) {
                            if (!r.exc) {
                                frappe.show_alert({ 
                                    message: __('Event Created Successfully'), 
                                    indicator: 'green' 
                                });
                                custom_dialog.hide();
                                
                                // Create a communication entry (like the original does)
                                let communication_doc = {
                                    doctype: 'Communication',
                                    subject: values.subject,
                                    content: values.description || `Event: ${values.subject}`,
                                    communication_type: 'Communication',
                                    reference_doctype: me.frm.doc.doctype,
                                    reference_name: me.frm.doc.name,
                                    sent_or_received: 'Sent',
                                    communication_date: frappe.datetime.now_datetime()
                                };

                                frappe.call({
                                    method: 'frappe.client.insert',
                                    args: {
                                        doc: communication_doc
                                    },
                                    callback: function(r2) {
                                        if (!r2.exc) {
                                            // Refresh everything
                                            me.refresh();
                                            if (me.frm) {
                                                me.frm.refresh();
                                            }
                                        }
                                    }
                                });
                            } else {
                                frappe.msgprint(__('Error creating event: {0}', [r.exc]));
                            }
                        }
                    });
                },
                primary_action_label: __('Create')
            });

            custom_dialog.show();
            custom_dialog.$wrapper.find('.modal-dialog').css({
                'width': '50vw',
                'max-width': '50vw',
                'max-height': '90vh',
                'overflow-y': 'auto'
            });

            $('.frappe-control[data-fieldname="fetch_slots"] .control-input-wrapper').css({
                'display': 'flex',
                'align-items': 'center'
            });

            let styleTag = `
                <style>
                    .slots-scroll-wrapper {
                        width: 100%;
                        overflow-x: auto; 
                        white-space: nowrap;       
                        padding: 5px 0;
                    }
                    .slot-item {
                        display: inline-block; 
                        margin: 5px;
                        padding: 10px 15px;
                        background: #f0f7ff;
                        border: 1px solid #c2d9ff;
                        border-radius: 4px;
                        white-space: nowrap;
                        cursor: pointer; 
                    }
                    .slot-item:hover {
                        background: #e1edff; 
                    }
                    .frappe-control[data-fieldname="column_break_3"] form {
                        display: flex !important;
                        justify-content: center;
                        align-items: center;
                    }
                </style>
            `;
            custom_dialog.$wrapper.append(styleTag);
        };
        
        $(".new-event-btn").click(_create_event);
    }

    displaySlots(slots, container, custom_dialog) {
        if (!slots || slots.length === 0) {
            container.html('<div class="text-muted text-center">No available slots found.</div>');
            return;
        }

        // Track currently selected slot
        let selectedSlot = null;

        // Create HTML for slots with enhanced display
        let slotsHTML = slots.map((slot, index) => {
            // slot.start_local / slot.end_local are 'YYYY-MM-DD HH:MM:SS' in site/user TZ (backend provided)
            // We'll parse them with moment to avoid timezone shifts, then format for display and data attributes.
            let mStart = moment(slot.start_local, 'YYYY-MM-DD HH:mm:ss');
            let mEnd = moment(slot.end_local, 'YYYY-MM-DD HH:mm:ss');

            // Fallback if moment missing
            if (!mStart || !mStart.isValid()) mStart = moment(new Date(slot.start_local));
            if (!mEnd || !mEnd.isValid()) mEnd = moment(new Date(slot.end_local));

            let dateDisplay = mStart.format('ddd DD'); // e.g., Thu 19
            let startTime = mStart.format('HH:mm');
            let endTime = mEnd.format('HH:mm');

            // Data attributes hold the original local strings so no UTC conversion occurs
            const startLocalRaw = mStart.format('YYYY-MM-DD HH:mm:ss');
            const endLocalRaw = mEnd.format('YYYY-MM-DD HH:mm:ss');

            return `
                <div class="slot-item" id="slot-${index}" 
                     style="display: inline-block; margin: 8px; padding: 12px 16px; background: #f0f7ff; border: 2px solid #c2d9ff; border-radius: 8px; white-space: nowrap; cursor: pointer; text-align: center; min-width: 120px; transition: all 0.3s ease;" 
                     data-starts-on="${startLocalRaw}" 
                     data-ends-on="${endLocalRaw}">
                    <div style="font-size: 12px; color: #666; margin-bottom: 4px;">${dateDisplay}</div>
                    <strong style="font-size: 14px; display: block;">${startTime} - ${endTime}</strong>
                </div>`;
        }).join('');

        // Wrap the slots in a centered, scrollable div
        container.html(`
            <div class="slots-scroll-wrapper" style="width: 100%; overflow-x: auto; white-space: nowrap; padding: 10px 0; text-align: center;">
                <div style="display: inline-block; margin: 0 auto;">
                    ${slotsHTML}
                </div>
            </div>
            <div class="text-center" style="margin-top: 10px;">
                <small class="text-muted">Click on a time slot to auto-fill the Start and End dates</small>
            </div>
        `);

        // Add click event listeners to each slot
        slots.forEach((slot, index) => {
            let slotElement = container.find(`#slot-${index}`);
            
            slotElement.on('click', function() {
                // Remove highlight from previously selected slot
                if (selectedSlot) {
                    selectedSlot.css({
                        'background': '#f0f7ff',
                        'border-color': '#c2d9ff',
                        'transform': 'scale(1)'
                    });
                }
                
                // Highlight current slot
                $(this).css({
                    'background': '#e8f5e8',
                    'border-color': '#4CAF50',
                    'transform': 'scale(1.02)',
                    'box-shadow': '0 4px 8px rgba(76, 175, 80, 0.2)'
                });
                
                selectedSlot = $(this);
                console.log('[Mailcow] Selected slot:', $(this).data());
                
                const starts_on_raw = $(this).attr('data-starts-on');
                const ends_on_raw = $(this).attr('data-ends-on');
                
                // Parse using moment to avoid timezone shift; fall back gracefully
                let mStart = moment(starts_on_raw, 'YYYY-MM-DD HH:mm:ss', true);
                if (!mStart.isValid()) mStart = moment(starts_on_raw);
                let mEnd = moment(ends_on_raw, 'YYYY-MM-DD HH:mm:ss', true);
                if (!mEnd.isValid()) mEnd = moment(ends_on_raw);

                // DB safe values (what Frappe Datetime fields expect)
                const start_db = mStart.isValid() ? mStart.format('YYYY-MM-DD HH:mm:ss') : starts_on_raw;
                const end_db = mEnd.isValid() ? mEnd.format('YYYY-MM-DD HH:mm:ss') : ends_on_raw;

                // Human readable for notification only
                const start_human = mStart.isValid() ? mStart.format('DD.MM.YYYY HH:mm') : starts_on_raw;
                const end_human = mEnd.isValid() ? mEnd.format('DD.MM.YYYY HH:mm') : ends_on_raw;
                console.log('[Mailcow] Raw Testing selected times:', { start_db, end_db });
                // Set dialog fields with DB format (avoid validation error expecting system format)
                custom_dialog.set_value('starts_on', start_db);
                custom_dialog.set_value('ends_on', end_db);
                
                // Show confirmation
                frappe.show_alert({
                    message: __('Selected slot: {0} → {1}', [start_human, end_human]),
                    indicator: 'green'
                });
            });
        });
    }
};