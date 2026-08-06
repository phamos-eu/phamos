// Copyright (c) 2025, phamos.eu and contributors
// Sales Order KPI Enhancements
// Multiple visualization options for per_delivered and per_billed

console.log('Phamos Sales Order KPI Enhancement - Script Loaded');

frappe.ui.form.on('Sales Order', {
    refresh: function(frm) {
        console.log('Sales Order refresh event triggered', frm.doc.name, 'docstatus:', frm.doc.docstatus);
        
        // Always cleanup first to handle duplicated records
        cleanup_kpi_displays(frm);
        
        if (frm.doc.docstatus === 1 && !frm.doc.__islocal) {
            render_kpi_display(frm, 'progress_bars');
        }
    }
});

// Cleanup function to remove all KPI visualizations
function cleanup_kpi_displays(frm) {
    const $scope = frm?.$wrapper || $(document);
    $scope.find('.so-progress-bars').remove();
    $scope.find('.so-kpi-cards').remove();
    $scope.find('.so-kpi-container').remove();
    $scope.find('.so-kpi-host').remove();
}

function render_kpi_display(frm, display_mode) {
    // Get the KPI values
    const per_delivered = flt(frm.doc.per_delivered, 2);
    const per_billed = flt(frm.doc.per_billed, 2);
    const $host_content = ensure_kpi_host(frm);
    
    
    if (display_mode === 'all' || display_mode === 'html_section') {
        add_html_kpi_section(frm, per_delivered, per_billed, $host_content);
    }
    
    if (display_mode === 'all' || display_mode === 'progress_bars') {
        add_progress_bar_section(frm, per_delivered, per_billed, $host_content);
    }
    
    if (display_mode === 'all' || display_mode === 'cards') {
        add_kpi_cards(frm, per_delivered, per_billed, $host_content);
    }
}

function ensure_kpi_host(frm) {
    const $existing = frm.$wrapper.find('.so-kpi-host');
    if ($existing.length) {
        return $existing.find('.so-kpi-content');
    }

    const $host = $(`
        <div class="so-kpi-host" style="margin: 6px 0 10px 0;">
            <div class="so-kpi-content"></div>
        </div>
    `);

    const $tabs = frm.$wrapper.find('.form-tabs-list').first();
    if ($tabs.length) {
        $tabs.before($host);
    } else {
        const $first_section = frm.$wrapper.find('.layout-main-section .form-section').first();
        if ($first_section.length) {
            $first_section.before($host);
        } else {
            const $fallback = frm.$wrapper.find('.layout-main-section').first();
            if ($fallback.length) {
                $fallback.prepend($host);
            }
        }
    }

    return $host.find('.so-kpi-content');
}

// OPTION 2: HTML Section with custom styling
function add_html_kpi_section(frm, per_delivered, per_billed, $host_content) {
    const html = get_html_kpi_content(per_delivered, per_billed);
    $host_content.append(html);
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
function add_progress_bar_section(frm, per_delivered, per_billed, $host_content) {
    const html = get_progress_bar_html(per_delivered, per_billed);

    $host_content.append(`
        <div class="so-progress-bars" style="margin: 10px 0 14px 0;">
            ${html}
        </div>
    `);
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
function add_kpi_cards(frm, per_delivered, per_billed, $host_content) {
    const html = get_kpi_cards_html(per_delivered, per_billed);

    $host_content.append(`
        <div class="so-kpi-cards" style="margin: 0 0 12px 0;">
            ${html}
        </div>
    `);
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

