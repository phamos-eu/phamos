frappe.pages['implementation-dashb'].on_page_load = function (wrapper) {
    const page = frappe.ui.make_app_page({
        parent: wrapper,
        title: 'Implementation Dashboard',
        single_column: true
    });

    // Page Layout
    $(page.body).html(`
        <div class="container">
            <div class="row mb-3" id="filter-section"></div>
            <div class="row mb-3">
                <div class="col">
                    <button id="clear-filters-btn" class="btn btn-secondary btn-sm">Clear Filters</button>
                </div>
            </div>
            <div class="frappe-card p-4" id="chart-container">Chart will load here</div>
        </div>
    `);

    // Simple filter helper
    function create_filter(label, fieldtype, fieldname, parentSelector, options = null, link_to = null) {
        const df = { label, fieldname, fieldtype, options };
        if (link_to) df.options = link_to;

        if (fieldtype === "MultiSelectList" && link_to) {
            df.get_data = function(txt) {
                return frappe.db.get_link_options(link_to, txt);
            };
        }

        const control = frappe.ui.form.make_control({
            parent: $('<div class="col mb-2"></div>').appendTo(parentSelector),
            df: df,
        });
        control.refresh();
        return control;
    }

    // Create filters
    const filters = {};
    filters.from_date = create_filter('From Date', 'Date', 'from_date', '#filter-section');
    filters.to_date = create_filter('To Date', 'Date', 'to_date', '#filter-section');
    filters.team = create_filter('Team', 'Link', 'team', '#filter-section', null, 'Team');
    filters.implementation = create_filter('Implementation', 'MultiSelectList', 'implementation', '#filter-section', null, 'Implementation');
    // Clear Filters Button Handler
    $('#clear-filters-btn').on('click', () => {
        Object.values(filters).forEach(ctrl => ctrl.set_value(''));
        load_chart();
    });

    const implementationColorMap = {};
    const colorPairs = [
        ['#3399ff', '#99ccff'],
        ['#28a745', '#90ee90'],
        ['#ff9933', '#ffcc99'],
        ['#800080', '#d1b3ff'],
        ['#cc0000', '#ff6666']
    ];
    let globalColorIndex = 0;
    let currentDisplayMode = 'split'; // Default display mode: 'billable', 'nonBillable', 'split', 'combined'

    function load_chart() {
        let from_date = filters.from_date.get_value();
        let to_date = filters.to_date.get_value();

        if (!from_date && !to_date) {
            const today = frappe.datetime.get_today(); 
            const past6 = frappe.datetime.add_months(today, -6); 
            const future6 = frappe.datetime.add_months(today, 6);
            filters.from_date.set_value(past6);
            filters.to_date.set_value(future6);
        }
        const args = {
            from_date: filters.from_date.get_value(),
            to_date: filters.to_date.get_value(),
            team: filters.team.get_value(),
            implementation: filters.implementation.get_value() ? filters.implementation.get_value().join(',') : ''
        };

        frappe.call({
            method: 'phamos.phamos.page.implementation_dashb.implementation_dashb.get_chart_data',
            args: args,
            callback: function (r) {
                if (!r.message) {
                    $('#chart-container').html('<div class="text-muted p-3">No data found</div>');
                    return;
                }

                const planningData = r.message.planning || [];
                const predictionData = r.message.prediction || [];
                const addonData = r.message.addon || [];


                const categorySet = new Set();
                planningData.forEach(row => categorySet.add(row.month_and_year));
                predictionData.forEach(row => categorySet.add(row.month_and_year));
                addonData.forEach(row => categorySet.add(row.month_and_year));

                const categories = Array.from(categorySet).sort();
                const categoryIndexMap = {};
                categories.forEach((month, idx) => categoryIndexMap[month] = idx);

                const groupedData = {};

                planningData.forEach(row => {
                    let impl = row.implementation_name || 'Unknown';

                    if (!groupedData[impl]) {
                        groupedData[impl] = {
                            billable: new Array(categories.length).fill(0),
                            nonBillable: new Array(categories.length).fill(0)
                        };
                    }

                    const idx = categoryIndexMap[row.month_and_year];
                    groupedData[impl].billable[idx] += row.billable_time_spent || 0;
                    groupedData[impl].nonBillable[idx] += row.non_billable_time_spent || 0;
                });

                const series = [];
                Object.entries(groupedData).forEach(([impl, data]) => {
                    if (!implementationColorMap[impl]) {
                        implementationColorMap[impl] = colorPairs[globalColorIndex % colorPairs.length];
                        globalColorIndex++;
                    }

                    const colors = implementationColorMap[impl];
                    
                    // Generate series based on display mode
                    if (currentDisplayMode === 'billable') {
                        // Only Billable
                        series.push({
                            name: `${impl} - Billable`,
                            type: 'area',
                            data: data.billable,
                            color: colors[0],
                            stack: 'time_spent'
                        });
                    } else if (currentDisplayMode === 'nonBillable') {
                        // Only Non-Billable
                        series.push({
                            name: `${impl} - Non-Billable`,
                            type: 'area',
                            data: data.nonBillable,
                            color: colors[1],
                            stack: 'time_spent'
                        });
                    } else if (currentDisplayMode === 'combined') {
                        // Combined (billable + non-billable as single color)
                        const combinedData = data.billable.map((val, idx) => val + (data.nonBillable[idx] || 0));
                        series.push({
                            name: `${impl} - Total`,
                            type: 'area',
                            data: combinedData,
                            color: colors[0],
                            stack: 'time_spent'
                        });
                    } else {
                        // Split mode (default) - show both billable and non-billable separately
                        series.push({
                            name: `${impl} - Non-Billable`,
                            type: 'area',
                            data: data.nonBillable,
                            color: colors[1],
                            stack: 'time_spent'
                        });
                        series.push({
                            name: `${impl} - Billable`,
                            type: 'area',
                            data: data.billable,
                            color: colors[0],
                            stack: 'time_spent'
                        });
                    }
                });

                const addonSeries = categories.map(month => {
                    const found = addonData.find(row => row.month_and_year === month);
                    return found ? found.total_hours : 0;
                });

                series.push({
                    name: "Internal project hrs",
                    type: "line",
                    data: addonSeries,
                    color: "orange",
                    dashStyle: "ShortDot",
                    marker: { enabled: true, radius: 4 }
                });

                // ✅ Calculate total prediction line
                let allMonthMessages = "";
                const totalPredictionSeries = categories.map(month => {
                    const monthRows = predictionData.filter(r => r.month_and_year === month);
                    const grouped = {};
                    monthRows.forEach(r => {
                        if (!grouped[r.implementation_name]) grouped[r.implementation_name] = [];
                        grouped[r.implementation_name].push(r.prediction || 0);
                    });

                    const implAverages = {};
                    Object.entries(grouped).forEach(([impl, arr]) => {
                        const total = arr.reduce((a, b) => a + b, 0);
                        implAverages[impl] = arr.length ? (total / arr.length) : 0;
                    });

                    allMonthMessages += `<b>${month}</b><br>`;
                    for (let [impl, avg] of Object.entries(implAverages)) {
                        allMonthMessages += `${impl}: <b>${avg.toFixed(2)}</b><br>`;
                    }
                    allMonthMessages += `<hr/>`;

                    // Sum of averages = total prediction
                    return Object.values(implAverages).reduce((a, b) => a + b, 0);
                });

                // Push cumulative dotted line
                series.push({
                    name: "Total Prediction (Sum of Avg)",
                    type: "line",
                    data: totalPredictionSeries,
                    color: "#000000",
                    dashStyle: "Dot",
                    marker: { enabled: true, radius: 3 }
                });

                // Determine chart title based on display mode
                const chartTitles = {
                    'billable': 'Billable Time with Prediction',
                    'nonBillable': 'Non-Billable Time with Prediction',
                    'split': 'Billable vs Non-Billable Time with Prediction',
                    'combined': 'Total Time (Billable + Non-Billable) with Prediction'
                };

                // Chart rendering
                $('#chart-container').html(`
                    <div class="d-flex justify-content-between align-items-center mb-2 flex-wrap">
                        <div class="btn-group me-2 mb-1" role="group" aria-label="Display Mode">
                            <button type="button" class="btn btn-sm display-mode-btn ${currentDisplayMode === 'split' ? 'btn-primary' : 'btn-outline-primary'}" data-mode="split">
                                Split View
                            </button>
                            <button type="button" class="btn btn-sm display-mode-btn ${currentDisplayMode === 'billable' ? 'btn-primary' : 'btn-outline-primary'}" data-mode="billable">
                                Billable Only
                            </button>
                            <button type="button" class="btn btn-sm display-mode-btn ${currentDisplayMode === 'nonBillable' ? 'btn-primary' : 'btn-outline-primary'}" data-mode="nonBillable">
                                Non-Billable Only
                            </button>
                            <button type="button" class="btn btn-sm display-mode-btn ${currentDisplayMode === 'combined' ? 'btn-primary' : 'btn-outline-primary'}" data-mode="combined">
                                Combined
                            </button>
                        </div>
                        <button id="toggle-legend" class="btn btn-sm btn-outline-secondary mb-1">Show Legend</button>
                    </div>
                    <div id="implementation-chart" style="height:600px;"></div>
                `);

                // Display mode button click handlers
                $(document).off('click', '.display-mode-btn').on('click', '.display-mode-btn', function() {
                    currentDisplayMode = $(this).data('mode');
                    load_chart(); // Reload chart with new display mode
                });

                const chart = Highcharts.chart('implementation-chart', {
                    chart: { zoomType: 'xy' },
                    legend: { enabled: false },
                    title: { text: chartTitles[currentDisplayMode] || 'Time with Prediction' },
                    xAxis: { categories: categories },
                    yAxis: { title: { text: 'Time (hrs)' } },
                    tooltip: {
                        shared: false,
                        useHTML: true,
                        backgroundColor: 'rgba(255, 255, 255, 0.95)',
                        borderRadius: 8,
                        padding: 12,
                        formatter: function () {
                            const point = this.point;
                            const seriesName = this.series.name;
                            const month = this.x;
                            const pointIndex = this.point.index;
                            
                            // Extract implementation name from series name
                            let implName = seriesName;
                            let dataType = '';
                            if (seriesName.includes(' - Billable')) {
                                implName = seriesName.replace(' - Billable', '');
                                dataType = 'Billable';
                            } else if (seriesName.includes(' - Non-Billable')) {
                                implName = seriesName.replace(' - Non-Billable', '');
                                dataType = 'Non-Billable';
                            } else if (seriesName.includes(' - Total')) {
                                implName = seriesName.replace(' - Total', '');
                                dataType = 'Total';
                            }
                            
                            // For prediction lines, show simple tooltip
                            if (seriesName.includes('Prediction') || seriesName.includes('Internal project')) {
                                return `<div style="padding: 5px;">
                                    <strong>${month}</strong><br/>
                                    <span style="color:${this.color}">●</span> ${seriesName}: <b>${this.y.toFixed(1)} hrs</b>
                                </div>`;
                            }
                            
                            // Find the matching billable/non-billable data for this implementation
                            const implData = groupedData[implName];
                            if (!implData) {
                                return `<div style="padding: 5px;">
                                    <strong>${month}</strong><br/>
                                    <span style="color:${this.color}">●</span> ${seriesName}: <b>${this.y.toFixed(1)} hrs</b>
                                </div>`;
                            }
                            
                            const billableHrs = implData.billable[pointIndex] || 0;
                            const nonBillableHrs = implData.nonBillable[pointIndex] || 0;
                            const totalHrs = billableHrs + nonBillableHrs;
                            
                            // Calculate total across all months for this implementation
                            const implGrandTotal = implData.billable.reduce((sum, val, idx) => sum + val + (implData.nonBillable[idx] || 0), 0);
                            const percentOfImplTotal = implGrandTotal > 0 ? ((totalHrs / implGrandTotal) * 100).toFixed(1) : 0;
                            
                            // Calculate grand total across ALL implementations
                            let grandTotal = 0;
                            Object.values(groupedData).forEach(data => {
                                grandTotal += data.billable.reduce((sum, val, idx) => sum + val + (data.nonBillable[idx] || 0), 0);
                            });
                            const percentOfGrandTotal = grandTotal > 0 ? ((totalHrs / grandTotal) * 100).toFixed(1) : 0;
                            
                            // Get implementation color
                            const implColors = implementationColorMap[implName] || ['#3399ff', '#ff9933'];
                            
                            let tooltip = `<div style="min-width: 220px;">`;
                            tooltip += `<div style="font-size: 13px; font-weight: bold; color: #333; margin-bottom: 8px; border-bottom: 2px solid ${implColors[0]}; padding-bottom: 5px;">${implName}</div>`;
                            tooltip += `<div style="font-size: 12px; color: #666; margin-bottom: 8px;">${month}</div>`;
                            
                            tooltip += `<div style="padding: 8px; background: #f8f9fa; border-radius: 4px; margin-bottom: 8px;">`;
                            
                            // Mode-aware tooltip content
                            if (currentDisplayMode === 'billable') {
                                // Billable Only mode - emphasize billable, show non-billable as context
                                tooltip += `<div style="margin-bottom: 4px; font-size: 14px;"><span style="color: ${implColors[0]};">●</span> <strong>Billable: ${billableHrs.toFixed(1)} hrs</strong></div>`;
                                if (nonBillableHrs > 0) {
                                    tooltip += `<div style="margin-bottom: 4px; color: #888; font-size: 11px;"><span style="color: ${implColors[1]};">○</span> (Non-Billable: ${nonBillableHrs.toFixed(1)} hrs - not shown)</div>`;
                                }
                                const billablePercent = totalHrs > 0 ? ((billableHrs / totalHrs) * 100).toFixed(0) : 0;
                                tooltip += `<div style="border-top: 1px solid #ddd; padding-top: 4px; margin-top: 4px; font-size: 11px; color: #666;">Billable is <strong>${billablePercent}%</strong> of this month's total</div>`;
                            } else if (currentDisplayMode === 'nonBillable') {
                                // Non-Billable Only mode - emphasize non-billable, show billable as context
                                tooltip += `<div style="margin-bottom: 4px; font-size: 14px;"><span style="color: ${implColors[1]};">●</span> <strong>Non-Billable: ${nonBillableHrs.toFixed(1)} hrs</strong></div>`;
                                if (billableHrs > 0) {
                                    tooltip += `<div style="margin-bottom: 4px; color: #888; font-size: 11px;"><span style="color: ${implColors[0]};">○</span> (Billable: ${billableHrs.toFixed(1)} hrs - not shown)</div>`;
                                }
                                const nonBillablePercent = totalHrs > 0 ? ((nonBillableHrs / totalHrs) * 100).toFixed(0) : 0;
                                tooltip += `<div style="border-top: 1px solid #ddd; padding-top: 4px; margin-top: 4px; font-size: 11px; color: #666;">Non-Billable is <strong>${nonBillablePercent}%</strong> of this month's total</div>`;
                            } else if (currentDisplayMode === 'combined') {
                                // Combined mode - emphasize total, show breakdown as context
                                const billablePercent = totalHrs > 0 ? ((billableHrs / totalHrs) * 100).toFixed(0) : 0;
                                const nonBillablePercent = totalHrs > 0 ? ((nonBillableHrs / totalHrs) * 100).toFixed(0) : 0;
                                tooltip += `<div style="margin-bottom: 8px; font-size: 16px; text-align: center;"><span style="color: ${implColors[0]};">●</span> <strong>Total: ${totalHrs.toFixed(1)} hrs</strong></div>`;
                                tooltip += `<div style="border-top: 1px solid #ddd; padding-top: 6px; margin-top: 4px;">`;
                                tooltip += `<div style="display: flex; justify-content: space-between; margin-bottom: 3px; font-size: 11px;">`;
                                tooltip += `<span><span style="color: ${implColors[0]};">▪</span> Billable</span>`;
                                tooltip += `<span><strong>${billableHrs.toFixed(1)} hrs</strong> (${billablePercent}%)</span>`;
                                tooltip += `</div>`;
                                tooltip += `<div style="display: flex; justify-content: space-between; font-size: 11px;">`;
                                tooltip += `<span><span style="color: ${implColors[1]};">▪</span> Non-Billable</span>`;
                                tooltip += `<span><strong>${nonBillableHrs.toFixed(1)} hrs</strong> (${nonBillablePercent}%)</span>`;
                                tooltip += `</div>`;
                                tooltip += `</div>`;
                            } else {
                                // Split mode - show full breakdown equally
                                tooltip += `<div style="margin-bottom: 4px;"><span style="color: ${implColors[0]};">●</span> Billable: <strong>${billableHrs.toFixed(1)} hrs</strong></div>`;
                                tooltip += `<div style="margin-bottom: 4px;"><span style="color: ${implColors[1]};">●</span> Non-Billable: <strong>${nonBillableHrs.toFixed(1)} hrs</strong></div>`;
                                tooltip += `<div style="border-top: 1px solid #ddd; padding-top: 4px; margin-top: 4px;">Month Total: <strong>${totalHrs.toFixed(1)} hrs</strong></div>`;
                            }
                            tooltip += `</div>`;
                            
                            tooltip += `<div style="padding: 6px; background: #e3f2fd; border-radius: 4px; font-size: 11px;">`;
                            tooltip += `<div style="color: #555;">Implementation Total: <strong>${implGrandTotal.toFixed(1)} hrs</strong></div>`;
                            tooltip += `<div style="color: #555;">This month: <strong>${percentOfImplTotal}%</strong> of implementation</div>`;
                            tooltip += `<div style="color: #555; margin-top: 4px;">All Implementations: <strong>${grandTotal.toFixed(1)} hrs</strong></div>`;
                            tooltip += `<div style="color: #555;">This implementation: <strong>${percentOfGrandTotal}%</strong> of total</div>`;
                            tooltip += `</div>`;
                            
                            tooltip += `</div>`;
                            return tooltip;
                        }
                    },
                    plotOptions: {
                        area: { stacking: 'normal', marker: { enabled: false } },
                        line: { marker: { enabled: true, radius: 3 } }
                    },
                    series: series
                });

                let legendVisible = false;
                $(document).off('click', '#toggle-legend').on('click', '#toggle-legend', function () {
                    legendVisible = !legendVisible;
                    chart.update({ legend: { enabled: legendVisible } });
                    $(this).text(legendVisible ? "Hide Legend" : "Show Legend");
                });
            }
        });
    }

    load_chart();
    Object.values(filters).forEach(ctrl => { ctrl.df.onchange = () => load_chart(); });
};
