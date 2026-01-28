// Copyright (c) 2025, Phamos GmbH and contributors

frappe.ui.form.on('Lead', {
    onload: function(frm) {
        // Track if dialog was shown during this form load
        frm._dnc_dialog_shown_on_load = false;
        // Store initial status comment to detect changes
        frm._initial_status_comment = frm.doc.custom_status_comment;
    },
    
    refresh: function(frm) {
        // Set field visibility and mandatory state
        if (frm.doc.status === 'Do Not Contact') {
            frm.set_df_property('custom_status_comment', 'reqd', 1);
        } else {
            frm.set_df_property('custom_status_comment', 'reqd', 0);
        }
        
        // Show dialog only once per load and only if comment exists
        // Don't show after saves (user is editing)
        if (frm.doc.status === 'Do Not Contact' && 
            frm.doc.custom_status_comment && 
            !frm.is_new() && 
            !frm._dnc_dialog_shown_on_load && 
            !frm._suppress_dnc_dialog_after_save) {
            
            // Mark as shown for this load
            frm._dnc_dialog_shown_on_load = true;
            
            // Use requestAnimationFrame to ensure DOM is fully ready, then add minimal delay
            requestAnimationFrame(() => {
                setTimeout(() => {
                    // Double-check the form is still in the right state
                    if (frm.doc.status === 'Do Not Contact' && frm.doc.custom_status_comment) {
                        show_do_not_contact_dialog(frm);
                    }
                }, 100);
            });
        }
        
        // Clear the suppress flag after save (it's only for one refresh cycle)
        if (frm._suppress_dnc_dialog_after_save) {
            frm._suppress_dnc_dialog_after_save = false;
        }
    },
    
    status: function(frm) {
        // When status is changed to "Do Not Contact", prompt for a reason.
        if (frm.doc.status === 'Do Not Contact') {
            frm.set_df_property('custom_status_comment', 'reqd', 1);
            
            // Always prompt for a reason, pre-filling with existing comment if any
            prompt_for_do_not_contact_reason(frm, frm.doc.custom_status_comment);
        } else {
            // Not mandatory for other statuses
            frm.set_df_property('custom_status_comment', 'reqd', 0);
        }
    },
    
    custom_status_comment: function(frm) {
        // Update modified_by and modified_date when comment changes
        if (frm.doc.custom_status_comment && frm.doc.status === 'Do Not Contact') {
            frm.set_value('custom_status_comment_modified_by', frappe.session.user);
            frm.set_value('custom_status_comment_modified_date', frappe.datetime.now_datetime());
        }
    },
    
    before_save: function(frm) {
        // Suppress dialog after any save operation
        if (frm.doc.status === 'Do Not Contact' && frm.doc.custom_status_comment) {
            frm._suppress_dnc_dialog_after_save = true;
        }
    },
});

function prompt_for_do_not_contact_reason(frm, existing_reason) {
    const dialog = new frappe.ui.Dialog({
        title: __('Reason for "Do Not Contact"'),
        indicator: 'orange',
        fields: [
            {
                label: __('Please provide a reason for setting this Lead to "Do Not Contact". This is mandatory.'),
                fieldname: 'reason',
                fieldtype: 'Text',
                reqd: 1,
                default: existing_reason || ''
            }
        ],
        primary_action_label: __('Save Reason'),
        primary_action: function(values) {
            frm.set_value('custom_status_comment', values.reason);
            dialog.hide();
            // Suppress the Do Not Contact info dialog after saving
            frm._suppress_dnc_dialog_after_save = true;
            frm.save()
                .then(() => {
                    frappe.show_alert({
                        message: __('Lead status updated and reason saved.'),
                        indicator: 'green'
                    });
                })
                .catch(() => {
                    frappe.show_alert({
                        message: __('Could not save the Lead. Please try again.'),
                        indicator: 'red'
                    });
                });
        }
    });
    dialog.show();
    dialog.get_field('reason').$wrapper.find('textarea').css('height', '80px');
}

function show_do_not_contact_dialog(frm) {
    
    const modified_by = frm.doc.custom_status_comment_modified_by || frm.doc.modified_by;
    const modified_date = frm.doc.custom_status_comment_modified_date || frm.doc.modified;
    
    // Format the date
    const formatted_date = frappe.datetime.str_to_user(modified_date);
    const relative_date = frappe.datetime.comment_when(modified_date);
    
    // Get user full name
    frappe.call({
        method: 'frappe.client.get_value',
        args: {
            doctype: 'User',
            filters: { name: modified_by },
            fieldname: 'full_name'
        },
        callback: function(r) {
            const full_name = r.message ? r.message.full_name : modified_by;
            
            show_dialog_with_content(frm, full_name, formatted_date, relative_date);
        },
        error: function(err) {
            console.error('Error fetching user name:', err);
            // Show dialog anyway with modified_by as fallback
            show_dialog_with_content(frm, modified_by, formatted_date, relative_date);
        }
    });
}

function show_dialog_with_content(frm, full_name, formatted_date, relative_date) {
    const dialog = new frappe.ui.Dialog({
                title: __('⚠️ Do Not Contact - Status Comment'),
                indicator: 'red',
                fields: [
                    {
                        fieldtype: 'HTML',
                        fieldname: 'status_info',
                        options: `
                            <div style="padding: 15px;">
                                <div style="background: #fef2f2; border-left: 4px solid #dc2626; padding: 15px; border-radius: 6px; margin-bottom: 15px;">
                                    <div style="font-weight: 600; color: #dc2626; margin-bottom: 10px; font-size: 14px;">
                                        <i class="fa fa-ban"></i> This lead is marked as "Do Not Contact"
                                    </div>
                                    <div style="color: #991b1b; font-size: 13px; line-height: 1.6;">
                                        Please review the reason below before proceeding with any actions on this lead.
                                    </div>
                                </div>
                                
                                <div style="background: #f9fafb; padding: 15px; border-radius: 6px; border: 1px solid #e5e7eb;">
                                    <div style="font-weight: 600; color: #374151; margin-bottom: 8px; font-size: 13px;">
                                        Reason:
                                    </div>
                                    <div style="background: white; padding: 12px; border-radius: 4px; border: 1px solid #d1d5db; white-space: pre-wrap; font-size: 14px; color: #1f2937; line-height: 1.6;">
                                        ${frappe.utils.escape_html(frm.doc.custom_status_comment || 'No comment provided')}
                                    </div>
                                </div>
                                
                                <div style="margin-top: 15px; padding-top: 12px; border-top: 1px solid #e5e7eb;">
                                    <div style="display: flex; align-items: center; gap: 8px; color: #6b7280; font-size: 12px;">
                                        <i class="fa fa-user"></i>
                                        <span style="font-weight: 500;">Last updated by:</span>
                                        <span style="color: #374151;">${full_name}</span>
                                    </div>
                                    <div style="display: flex; align-items: center; gap: 8px; color: #6b7280; font-size: 12px; margin-top: 6px;">
                                        <i class="fa fa-clock-o"></i>
                                        <span style="font-weight: 500;">On:</span>
                                        <span style="color: #374151;">${formatted_date}</span>
                                        <span style="color: #9ca3af;">(${relative_date})</span>
                                    </div>
                                </div>
                            </div>
                        `
                    }
                ],
                primary_action_label: __('I Understand'),
                primary_action: function() {
                    dialog.hide();
                },
                secondary_action_label: __('Edit Comment'),
                secondary_action: function() {
                    dialog.hide();
                    frm.scroll_to_field('custom_status_comment');
                }
            });
            
            dialog.show();
}
