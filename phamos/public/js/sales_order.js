// Copyright (c) 2025, phamos.eu and contributors
// Sales Order KPI Enhancements
// Multiple visualization options for per_delivered and per_billed

console.log('Phamos Sales Order KPI Enhancement - Script Loaded');

frappe.ui.form.on('Sales Order', {
    refresh: function(frm) {
        console.log('Sales Order refresh event triggered', frm.doc.name, 'docstatus:', frm.doc.docstatus);
        
        // Always cleanup first to handle duplicated records
        cleanup_kpi_displays();
        
        if (frm.doc.docstatus === 1 && !frm.doc.__islocal) {
            console.log('Loading KPI preferences for', frm.doc.name);
            // Load user preference and display KPIs
            frappe.call({
                method: 'phamos.api.get_sales_order_kpi_preference',
                callback: function(r) {
                    console.log('KPI preference loaded:', r.message);
                    const display_mode = r.message || 'all';
                    render_kpi_display(frm, display_mode);
                }
            });
        }
    },
    
    onload: function(frm) {
        // Add style preference button in toolbar
        if (!frm.is_new() && frm.doc.docstatus === 1) {
            add_style_selector_button(frm);
        }
    }
});

// Cleanup function to remove all KPI visualizations
function cleanup_kpi_displays() {
    $('.so-progress-bars').remove();
    $('.so-kpi-cards').remove();
    $('.so-kpi-container').remove();
}

function render_kpi_display(frm, display_mode) {
    // Get the KPI values
    const per_delivered = flt(frm.doc.per_delivered, 2);
    const per_billed = flt(frm.doc.per_billed, 2);
    
    
    if (display_mode === 'all' || display_mode === 'html_section') {
        add_html_kpi_section(frm, per_delivered, per_billed);
    }
    
    if (display_mode === 'all' || display_mode === 'progress_bars') {
        add_progress_bar_section(frm, per_delivered, per_billed);
    }
    
    if (display_mode === 'all' || display_mode === 'cards') {
        add_kpi_cards(frm, per_delivered, per_billed);
    }
    
    // Show current mode indicator
    if (display_mode !== 'all') {
        add_display_mode_toggle(frm, display_mode);
    }
}

// OPTION 2: HTML Section with custom styling
function add_html_kpi_section(frm, per_delivered, per_billed) {
    // Check if field exists, if not we'll add it programmatically
    if (!frm.fields_dict.kpi_html_section) {
        const html = get_html_kpi_content(per_delivered, per_billed);
        
        // Insert after customer section
        frm.set_df_property('customer_section', 'description', html);
    }
}

function get_html_kpi_content(per_delivered, per_billed) {
    const delivery_color = get_delivery_color(per_delivered);
    const billing_color = get_billing_color(per_billed);
    
    return `
        <div class="so-kpi-container" style="
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            padding: 20px;
            border-radius: 8px;
            margin: 15px 0;
            box-shadow: 0 4px 6px rgba(0,0,0,0.1);
        ">
            <div style="display: flex; justify-content: space-around; gap: 20px;">
                <div class="kpi-item" style="
                    flex: 1;
                    background: var(--card-bg);
                    padding: 15px;
                    border-radius: 6px;
                    text-align: center;
                    box-shadow: 0 2px 4px rgba(0,0,0,0.1);
                ">
                    <div style="font-size: 12px; color: var(--text-muted); text-transform: uppercase; margin-bottom: 8px;">
                        Delivery Status
                    </div>
                    <div style="font-size: 32px; font-weight: bold; color: ${get_hex_color(delivery_color)}; margin-bottom: 5px;">
                        ${per_delivered.toFixed(1)}%
                    </div>
                    <div style="font-size: 11px; color: var(--text-light);">
                        ${get_status_text(per_delivered)}
                    </div>
                </div>
                
                <div class="kpi-item" style="
                    flex: 1;
                    background: var(--card-bg);
                    padding: 15px;
                    border-radius: 6px;
                    text-align: center;
                    box-shadow: 0 2px 4px rgba(0,0,0,0.1);
                ">
                    <div style="font-size: 12px; color: var(--text-muted); text-transform: uppercase; margin-bottom: 8px;">
                        Billing Status
                    </div>
                    <div style="font-size: 32px; font-weight: bold; color: ${get_hex_color(billing_color)}; margin-bottom: 5px;">
                        ${per_billed.toFixed(1)}%
                    </div>
                    <div style="font-size: 11px; color: var(--text-light);">
                        ${get_status_text(per_billed)}
                    </div>
                </div>
            </div>
        </div>
    `;
}

// OPTION 3: Progress Bars
function add_progress_bar_section(frm, per_delivered, per_billed) {
    const html = get_progress_bar_html(per_delivered, per_billed);
    
    // Remove existing if any
    $('.so-progress-bars').remove();
    
    // Try multiple locations in order of preference
    let $target = frm.fields_dict.currency_and_price_list?.$wrapper;
    
    if (!$target || !$target.length) {
        $target = frm.fields_dict.currency?.$wrapper.closest('.form-section');
    }
    
    if (!$target || !$target.length) {
        $target = frm.fields_dict.items?.$wrapper;
    }
    
    if ($target && $target.length) {
        // Add before the target section
        $target.before(`
            <div class="so-progress-bars" style="margin: 15px 15px 20px 15px;">
                ${html}
            </div>
        `);
    } else {
        // Fallback: add after customer section
        const $customerSection = frm.fields_dict.customer_section?.$wrapper;
        if ($customerSection) {
            $customerSection.after(`
                <div class="so-progress-bars" style="margin: 15px 15px 20px 15px;">
                    ${html}
                </div>
            `);
        }
    }
}

function get_progress_bar_html(per_delivered, per_billed) {
    const delivery_color = get_delivery_color(per_delivered);
    const billing_color = get_billing_color(per_billed);
    
    return `
        <div style="background: var(--control-bg); padding: 12px 16px; border-radius: 6px; border: 1px solid var(--border-color);">
            <div style="display: flex; gap: 20px; align-items: center;">
                <!-- Delivery Progress -->
                <div style="flex: 1; display: flex; align-items: center; gap: 10px;">
                    <span style="font-size: 13px; font-weight: 600; color: var(--text-color); white-space: nowrap; min-width: 85px;">
                        <i class="fa fa-truck"></i> Delivery
                    </span>
                    <div style="flex: 1; position: relative;">
                        <div style="
                            background: var(--subtle-fg);
                            border-radius: 9999px;
                            height: 12px;
                            overflow: hidden;
                            position: relative;
                        ">
                            <div style="
                                background: ${get_gradient_color(delivery_color)};
                                height: 100%;
                                width: ${per_delivered}%;
                                transition: width 0.5s ease-in-out;
                            "></div>
                        </div>
                    </div>
                    <span style="font-size: 13px; font-weight: bold; color: ${get_hex_color(delivery_color)}; min-width: 45px; text-align: right;">
                        ${per_delivered.toFixed(1)}%
                    </span>
                </div>
                
                <!-- Separator -->
                <div style="width: 1px; height: 24px; background: var(--border-color);"></div>
                
                <!-- Billing Progress -->
                <div style="flex: 1; display: flex; align-items: center; gap: 10px;">
                    <span style="font-size: 13px; font-weight: 600; color: var(--text-color); white-space: nowrap; min-width: 75px;">
                        <i class="fa fa-money"></i> Billing
                    </span>
                    <div style="flex: 1; position: relative;">
                        <div style="
                            background: var(--subtle-fg);
                            border-radius: 9999px;
                            height: 12px;
                            overflow: hidden;
                            position: relative;
                        ">
                            <div style="
                                background: ${get_gradient_color(billing_color)};
                                height: 100%;
                                width: ${per_billed}%;
                                transition: width 0.5s ease-in-out;
                            "></div>
                        </div>
                    </div>
                    <span style="font-size: 13px; font-weight: bold; color: ${get_hex_color(billing_color)}; min-width: 45px; text-align: right;">
                        ${per_billed.toFixed(1)}%
                    </span>
                </div>
            </div>
        </div>
    `;
}

// OPTION 4: Card-based KPI Display
function add_kpi_cards(frm, per_delivered, per_billed) {
    const html = get_kpi_cards_html(per_delivered, per_billed);
    
    // Add to form layout
    const $wrapper = frm.fields_dict.customer_section?.$wrapper;
    if ($wrapper) {
        $wrapper.find('.so-kpi-cards').remove();
        $wrapper.after(`
            <div class="so-kpi-cards" style="margin: 20px 0;">
                ${html}
            </div>
        `);
    }
}

function get_kpi_cards_html(per_delivered, per_billed) {
    const delivery_color = get_delivery_color(per_delivered);
    const billing_color = get_billing_color(per_billed);
    
    return `
        <div style="display: grid; grid-template-columns: 1fr 1fr; gap: 20px;">
            <!-- Delivery Card -->
            <div style="
                background: var(--card-bg);
                border-left: 4px solid ${get_hex_color(delivery_color)};
                border-radius: 8px;
                padding: 20px;
                box-shadow: 0 2px 8px var(--shadow-base);
                transition: transform 0.2s;
            " onmouseover="this.style.transform='translateY(-4px)'" onmouseout="this.style.transform='translateY(0)'">
                <div style="display: flex; justify-content: space-between; align-items: flex-start; margin-bottom: 15px;">
                    <div>
                        <div style="color: var(--text-muted); font-size: 13px; text-transform: uppercase; letter-spacing: 0.5px;">
                            Delivery Status
                        </div>
                        <div style="font-size: 36px; font-weight: bold; color: ${get_hex_color(delivery_color)}; margin-top: 8px;">
                            ${per_delivered.toFixed(1)}%
                        </div>
                    </div>
                    <div style="
                        background: ${get_hex_color(delivery_color)};
                        color: white;
                        width: 48px;
                        height: 48px;
                        border-radius: 50%;
                        display: flex;
                        align-items: center;
                        justify-content: center;
                        font-size: 20px;
                    ">
                        <i class="fa fa-truck"></i>
                    </div>
                </div>
                <div style="
                    background: linear-gradient(to right, ${get_hex_color(delivery_color)}22, ${get_hex_color(delivery_color)}44);
                    padding: 8px 12px;
                    border-radius: 4px;
                    font-size: 12px;
                    font-weight: 500;
                    color: ${get_hex_color(delivery_color)};
                ">
                    ${get_status_text(per_delivered)}
                </div>
            </div>
            
            <!-- Billing Card -->
            <div style="
                background: var(--card-bg);
                border-left: 4px solid ${get_hex_color(billing_color)};
                border-radius: 8px;
                padding: 20px;
                box-shadow: 0 2px 8px var(--shadow-base);
                transition: transform 0.2s;
            " onmouseover="this.style.transform='translateY(-4px)'" onmouseout="this.style.transform='translateY(0)'">
                <div style="display: flex; justify-content: space-between; align-items: flex-start; margin-bottom: 15px;">
                    <div>
                        <div style="color: var(--text-muted); font-size: 13px; text-transform: uppercase; letter-spacing: 0.5px;">
                            Billing Status
                        </div>
                        <div style="font-size: 36px; font-weight: bold; color: ${get_hex_color(billing_color)}; margin-top: 8px;">
                            ${per_billed.toFixed(1)}%
                        </div>
                    </div>
                    <div style="
                        background: ${get_hex_color(billing_color)};
                        color: white;
                        width: 48px;
                        height: 48px;
                        border-radius: 50%;
                        display: flex;
                        align-items: center;
                        justify-content: center;
                        font-size: 20px;
                    ">
                        <i class="fa fa-money"></i>
                    </div>
                </div>
                <div style="
                    background: linear-gradient(to right, ${get_hex_color(billing_color)}22, ${get_hex_color(billing_color)}44);
                    padding: 8px 12px;
                    border-radius: 4px;
                    font-size: 12px;
                    font-weight: 500;
                    color: ${get_hex_color(billing_color)};
                ">
                    ${get_status_text(per_billed)}
                </div>
            </div>
        </div>
    `;
}

// Helper Functions
function get_delivery_color(percent) {
    if (percent >= 100) return 'green';
    if (percent >= 75) return 'blue';
    if (percent >= 50) return 'yellow';
    if (percent >= 25) return 'orange';
    return 'red';
}

function get_billing_color(percent) {
    if (percent >= 100) return 'green';
    if (percent >= 75) return 'blue';
    if (percent >= 50) return 'yellow';
    if (percent >= 25) return 'orange';
    return 'red';
}

function get_hex_color(color_name) {
    const colors = {
        'red': '#dc2626',
        'orange': '#ea580c',
        'yellow': '#ca8a04',
        'blue': '#2563eb',
        'green': '#16a34a'
    };
    return colors[color_name] || '#6b7280';
}

function get_gradient_color(color_name) {
    const gradients = {
        'red': 'linear-gradient(135deg, #dc2626 0%, #991b1b 100%)',
        'orange': 'linear-gradient(135deg, #ea580c 0%, #c2410c 100%)',
        'yellow': 'linear-gradient(135deg, #eab308 0%, #a16207 100%)',
        'blue': 'linear-gradient(135deg, #3b82f6 0%, #1d4ed8 100%)',
        'green': 'linear-gradient(135deg, #22c55e 0%, #15803d 100%)'
    };
    return gradients[color_name] || '#6b7280';
}

function get_status_text(percent) {
    if (percent >= 100) return '✓ Complete';
    if (percent >= 75) return '⚡ Almost Done';
    if (percent >= 50) return '⏳ In Progress';
    if (percent >= 25) return '⚠️ Getting Started';
    return '🔴 Urgent - Just Started';
}

// Display Mode Toggle
function add_style_selector_button(frm) {
    // Add a custom button to switch between display modes
    frm.add_custom_button(__('KPI Display Style'), function() {
        const d = new frappe.ui.Dialog({
            title: __('Select KPI Display Style'),
            fields: [
                {
                    fieldname: 'display_mode',
                    fieldtype: 'Select',
                    label: __('Display Mode'),
                    options: [
                        'All Styles',
                        'Progress Bars Only',
                        'Cards Only',
                        'HTML Section Only'
                    ],
                    default: 'All Styles'
                },
                {
                    fieldname: 'preview',
                    fieldtype: 'HTML',
                    options: `
                        <div style="margin-top: 15px; padding: 15px; background: var(--control-bg); border-radius: 6px; border: 1px solid var(--border-color);">
                            <h4 style="color: var(--text-color);">Preview Options:</h4>
                            <ul style="margin-left: 20px; line-height: 1.8; color: var(--text-color);">
                                <li><strong>All Styles:</strong> Shows all visualization options at once</li>
                                <li><strong>Progress Bars:</strong> Animated progress bars with gradients</li>
                                <li><strong>Cards:</strong> Modern card-based design with icons</li>
                                <li><strong>HTML Section:</strong> Compact inline display</li>
                            </ul>
                        </div>
                    `
                }
            ],
            primary_action_label: __('Apply'),
            primary_action: function(values) {
                const mode_map = {
                    'All Styles': 'all',
                    'Progress Bars Only': 'progress_bars',
                    'Cards Only': 'cards',
                    'HTML Section Only': 'html_section'
                };
                
                const selected_mode = mode_map[values.display_mode];
                
                // Save preference via API
                frappe.call({
                    method: 'phamos.api.set_sales_order_kpi_preference',
                    args: {
                        mode: selected_mode
                    },
                    callback: function(r) {
                        if (r.message && r.message.success) {
                            frappe.show_alert({
                                message: __('Display preference saved'),
                                indicator: 'green'
                            });
                            d.hide();
                            frm.reload_doc();
                        }
                    }
                });
            }
        });
        d.show();
    }, __('View'));
}

function add_display_mode_toggle(frm, current_mode) {
    // Show current mode
    const mode_names = {
        'progress_bars': 'Progress Bars',
        'cards': 'Cards',
        'html_section': 'HTML Section'
    };
    
    const mode_name = mode_names[current_mode] || 'All Styles';
    
    frm.set_intro(__('Current KPI Display: {0}', [mode_name]), 'blue');
}
