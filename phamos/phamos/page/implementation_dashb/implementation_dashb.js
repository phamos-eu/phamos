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

    function generateMonthRange(fromDate, toDate) {
        const result = [];
        let current = moment(fromDate).startOf('month');
        const end = moment(toDate).startOf('month');

        while (current <= end) {
            result.push(current.format('YYYY-MM'));
            current.add(1, 'month');
        }
        return result;
    }


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
    filters.team = create_filter('Team', 'MultiSelectList', 'team', '#filter-section', null, 'Team');
    filters.implementation = create_filter('Implementation', 'MultiSelectList', 'implementation', '#filter-section', null, 'Implementation');
    filters.department = create_filter('Department', 'MultiSelectList', 'department', '#filter-section', null, 'Department');
    // Clear Filters Button Handler
    $('#clear-filters-btn').on('click', () => {
        Object.values(filters).forEach(ctrl => ctrl.set_value(''));
        load_chart();
    });

    // Resolve the chart's colors from the ERP's own theme setting (document's
    // resolved data-theme, set by Frappe's User "Desk Theme" preference),
    // never from the browser/OS prefers-color-scheme directly. This also lets
    // us declare an explicit color-scheme + background so browsers with
    // "force dark mode for web content" stop auto-inverting the chart canvas.
    function get_chart_theme() {
        const theme = document.documentElement.getAttribute('data-theme') === 'dark' ? 'dark' : 'light';
        const css_var = (name, fallback) => {
            const val = getComputedStyle(document.documentElement).getPropertyValue(name).trim();
            return val || fallback;
        };
        if (theme === 'dark') {
            return {
                mode: 'dark',
                background: css_var('--fg-color', '#242629'),
                text: css_var('--text-on-gray', '#d2d6da'),
                gridLine: css_var('--dark-border-color', '#4a5258')
            };
        }
        return {
            mode: 'light',
            background: css_var('--fg-color', '#ffffff'),
            text: css_var('--text-color', '#36414c'),
            gridLine: css_var('--border-color', '#e0e0e0')
        };
    }

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
    let internalProjectsVisible = true; // Toggle for internal projects visibility

    // Set dedicated color for Internal Projects
    implementationColorMap['Internal Projects'] = ['#ff9933', '#ffcc99']; // Orange theme

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
            team: filters.team.get_value() ? filters.team.get_value().join(',') : '',
            implementation: filters.implementation.get_value() ? filters.implementation.get_value().join(',') : '',
            department: filters.department.get_value() ? filters.department.get_value().join(',') : ''
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
                const internalProjectsData = r.message.internal_projects || [];
                const teamCapacityAvg = r.message.team_capacity_avg || [];
                const implementationTeams = r.message.implementation_teams || {};


                const categories = generateMonthRange(
                    filters.from_date.get_value(),
                    filters.to_date.get_value()
                );

                const categoryIndexMap = {};
                categories.forEach((month, idx) => categoryIndexMap[month] = idx);
                const capacityMap = {};
                    teamCapacityAvg.forEach(row => {
                        capacityMap[row.month_and_year] = row.avg_capacity || 0;
                    });

                const groupedData = {};

                planningData.forEach(row => {
                    let impl = row.implementation_name || 'Unknown';

                    if (!groupedData[impl]) {
                        groupedData[impl] = {
                            billable: new Array(categories.length).fill(0),
                            nonBillable: new Array(categories.length).fill(0),
                            team: implementationTeams[impl] || 'Unassigned'
                        };
                    }

                    const idx = categoryIndexMap[row.month_and_year];
                    groupedData[impl].billable[idx] += row.billable_time_spent || 0;
                    groupedData[impl].nonBillable[idx] += row.non_billable_time_spent || 0;
                });

                // Add Internal Projects to groupedData (treat same as regular implementations)
                internalProjectsData.forEach(row => {
                    const impl = 'Internal Projects';

                    if (!groupedData[impl]) {
                        groupedData[impl] = {
                            billable: new Array(categories.length).fill(0),
                            nonBillable: new Array(categories.length).fill(0),
                            team: 'Internal Projects'
                        };
                    }

                    const idx = categoryIndexMap[row.month_and_year];
                    groupedData[impl].billable[idx] += row.billable_time_spent || 0;
                    groupedData[impl].nonBillable[idx] += row.non_billable_time_spent || 0;
                });

                const series = [];
                Object.entries(groupedData).forEach(([impl, data]) => {
                    // Skip Internal Projects if hidden
                    if (impl === 'Internal Projects' && !internalProjectsVisible) {
                        return;
                    }

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
                let lastCapacity = null;

                const teamCapacitySeries = categories.map(month => {
                    if (capacityMap.hasOwnProperty(month)) {
                        lastCapacity = capacityMap[month];
                        return lastCapacity;
                    }
                    // carry forward
                    return lastCapacity !== null ? lastCapacity : 0;
                });


                const selectedTeams = filters.team.get_value() || [];
                series.push({
                    name: selectedTeams.length
                        ? `Team Capacity (${selectedTeams.join(', ')})`
                        : "Overall Team Capacity",
                    type: "line",
                    data: teamCapacitySeries,
                    color: "#2c3e50",
                    lineWidth: 3,
                    dashStyle: "Solid",
                    marker: {
                        enabled: true,
                        radius: 4
                    },
                    zIndex: 20
                });

                // Determine chart title based on display mode
                const chartTitles = {
                    'billable': 'Billable Time with Prediction',
                    'nonBillable': 'Non-Billable Time with Prediction',
                    'split': 'Billable vs Non-Billable Time with Prediction',
                    'combined': 'Total Time (Billable + Non-Billable) with Prediction'
                };

                // Chart rendering
                const chartTheme = get_chart_theme();
                $('#chart-container').html(`
                    <style>
                        #implementation-chart {
                            color-scheme: ${chartTheme.mode};
                            background-color: ${chartTheme.background};
                        }
                        .display-mode-btn:not(.btn-primary) {
                            background-color: var(--fg-color, #fff);
                            color: var(--text-color, #000);
                            border-color: var(--border-color, #d1d8dd);
                        }
                        .display-mode-btn:not(.btn-primary):hover {
                            background-color: var(--control-bg-on-gray, #f5f5f5);
                            color: var(--text-color, #000);
                            border-color: var(--border-color, #d1d8dd);
                        }
                        html[data-theme="dark"] .display-mode-btn:not(.btn-primary) {
                            background-color: var(--control-bg, #2e3338);
                            color: var(--text-on-gray, #d2d6da);
                            border-color: var(--dark-border-color, #4a5258);
                        }
                        html[data-theme="dark"] .display-mode-btn:not(.btn-primary):hover {
                            background-color: var(--control-bg-on-gray, #3a4048);
                            color: var(--text-on-gray, #fff);
                            border-color: var(--dark-border-color, #5a6268);
                        }
                        .toggle-btn {
                            background-color: var(--fg-color, #fff);
                            color: var(--text-color, #000);
                            border-color: var(--border-color, #d1d8dd);
                        }
                        .toggle-btn:hover {
                            background-color: var(--control-bg-on-gray, #f5f5f5);
                            color: var(--text-color, #000);
                        }
                        html[data-theme="dark"] .toggle-btn {
                            background-color: var(--control-bg, #2e3338);
                            color: var(--text-on-gray, #d2d6da);
                            border-color: var(--dark-border-color, #4a5258);
                        }
                        html[data-theme="dark"] .toggle-btn:hover {
                            background-color: var(--control-bg-on-gray, #3a4048);
                            color: var(--text-on-gray, #fff);
                        }
                    </style>
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
                        <div>
                            <button id="toggle-internal-projects" class="btn btn-sm toggle-btn mb-1 me-2">
                                ${internalProjectsVisible ? '🟠 Hide' : '⚪ Show'} Internal Projects
                            </button>
                            <button id="toggle-legend" class="btn btn-sm toggle-btn mb-1">Show Legend</button>
                        </div>
                    </div>
                    <div id="implementation-chart" style="height:600px;"></div>
                    <div id="custom-legend-container" style="display: none;"></div>
                `);

                // Display mode button click handlers
                $(document).off('click', '.display-mode-btn').on('click', '.display-mode-btn', function() {
                    currentDisplayMode = $(this).data('mode');
                    load_chart(); // Reload chart with new display mode
                });

                // Internal projects toggle handler
                $(document).off('click', '#toggle-internal-projects').on('click', '#toggle-internal-projects', function() {
                    internalProjectsVisible = !internalProjectsVisible;
                    load_chart(); // Reload chart
                });

                const chart = Highcharts.chart('implementation-chart', {
                    chart: { zoomType: 'xy', backgroundColor: chartTheme.background, style: { color: chartTheme.text } },
                    legend: { enabled: false },
                    title: { text: chartTitles[currentDisplayMode] || 'Time with Prediction', style: { color: chartTheme.text } },
                    xAxis: {
                        categories: categories,
                        labels: { style: { color: chartTheme.text } },
                        lineColor: chartTheme.gridLine,
                        tickColor: chartTheme.gridLine
                    },
                    yAxis: {
                        title: { text: 'Time (hrs)', style: { color: chartTheme.text } },
                        labels: { style: { color: chartTheme.text } },
                        gridLineColor: chartTheme.gridLine
                    },
                    tooltip: {
                        shared: false,
                        useHTML: true,
                        backgroundColor: 'rgba(255, 255, 255, 0.95)',
                        borderRadius: 8,
                        padding: 12,
                        formatter: function () {
                            const point = this.point;
                            const seriesName = this.series.name;
                            const pointIndex = this.point.index;

                            const monthRaw = categories[this.point.index]; // Get actual month from categories array
                            // Format month to readable format (e.g., "2025-04" -> "Apr 2025")
                            let month = monthRaw;
                            if (monthRaw && monthRaw.match(/^\d{4}-\d{2}$/)) {
                                const momentMonth = moment(monthRaw, 'YYYY-MM');
                                month = momentMonth.format('MMM YYYY'); // e.g., "Apr 2025"
                            }

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
                            if (seriesName.includes('Prediction') || seriesName.includes('Capacity')) {
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

                            // Calculate month total for ALL implementations (for this specific month)
                            let monthTotalAllImplementations = 0;
                            Object.values(groupedData).forEach(data => {
                                monthTotalAllImplementations += (data.billable[pointIndex] || 0) + (data.nonBillable[pointIndex] || 0);
                            });
                            const percentOfMonthTotal = monthTotalAllImplementations > 0 ? ((totalHrs / monthTotalAllImplementations) * 100).toFixed(1) : 0;

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
                            tooltip += `<div style="color: #555; font-weight: 600; margin-bottom: 4px;">${month} (All Implementations):</div>`;
                            tooltip += `<div style="color: #555; margin-left: 8px;">Month Total: <strong>${monthTotalAllImplementations.toFixed(1)} hrs</strong></div>`;
                            tooltip += `<div style="color: #555; margin-left: 8px; margin-bottom: 8px;">This Month is <strong>${percentOfMonthTotal}%</strong> of ${month} total</div>`;

                            tooltip += `<div style="color: #555; font-weight: 600; margin-bottom: 4px; padding-top: 6px; border-top: 1px solid #b3d9f2;">This Implementation:</div>`;
                            tooltip += `<div style="color: #555; margin-left: 8px;">All Time Total: <strong>${implGrandTotal.toFixed(1)} hrs</strong></div>`;
                            tooltip += `<div style="color: #555; margin-left: 8px; margin-bottom: 8px;">This Month is <strong>${percentOfImplTotal}%</strong></div>`;

                            tooltip += `<div style="color: #555; font-weight: 600; margin-bottom: 4px; padding-top: 6px; border-top: 1px solid #b3d9f2;">All Implementations (All Time):</div>`;
                            tooltip += `<div style="color: #555; margin-left: 8px;">Portfolio Total: <strong>${grandTotal.toFixed(1)} hrs</strong></div>`;
                            tooltip += `<div style="color: #555; margin-left: 8px;">This Month (${month}) is <strong>${percentOfGrandTotal}%</strong> of portfolio</div>`;
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
                    if (legendVisible) {
                        // Shrink chart with smooth transition
                        $('#implementation-chart').css({
                            'transition': 'height 0.4s ease-in-out',
                            'height': '380px'
                        });
                        setTimeout(() => {
                            chart.setSize(null, 380, { duration: 400 });
                        }, 50);
                        buildCustomLegend(groupedData, implementationColorMap, currentDisplayMode, chart);
                        $('#custom-legend-container').css('opacity', 0).show().animate({ opacity: 1 }, 300);
                    } else {
                        // Restore chart height with smooth transition
                        $('#implementation-chart').css({
                            'transition': 'height 0.4s ease-in-out',
                            'height': '600px'
                        });
                        setTimeout(() => {
                            chart.setSize(null, 600, { duration: 400 });
                        }, 50);
                        $('#custom-legend-container').animate({ opacity: 0 }, 200, function() {
                            $(this).hide();
                        });
                    }
                    $(this).text(legendVisible ? "Hide Legend" : "Show Legend");
                });
            }
        });
    }

    // Build custom legend grouped by team with pagination
    function buildCustomLegend(groupedData, colorMap, displayMode, chart) {
        // Group implementations by team, filtering out those with 0 total hours
        const teamGroups = {};
        let grandTotalBillable = 0;
        let grandTotalNonBillable = 0;

        Object.entries(groupedData).forEach(([impl, data]) => {
            const totalBillable = data.billable.reduce((sum, val) => sum + val, 0);
            const totalNonBillable = data.nonBillable.reduce((sum, val) => sum + val, 0);
            const totalHours = totalBillable + totalNonBillable;

            // Only include implementations with actual hours
            if (totalHours > 0) {
                const team = data.team || 'Unassigned';
                if (!teamGroups[team]) {
                    teamGroups[team] = {
                        implementations: [],
                        totalBillable: 0,
                        totalNonBillable: 0
                    };
                }
                teamGroups[team].implementations.push({
                    name: impl,
                    billable: totalBillable,
                    nonBillable: totalNonBillable,
                    total: totalHours,
                    colors: colorMap[impl] || ['#3399ff', '#99ccff']
                });
                teamGroups[team].totalBillable += totalBillable;
                teamGroups[team].totalNonBillable += totalNonBillable;
                grandTotalBillable += totalBillable;
                grandTotalNonBillable += totalNonBillable;
            }
        });

        // Sort teams alphabetically, but put "Unassigned" at the end
        const sortedTeams = Object.keys(teamGroups).sort((a, b) => {
            if (a === 'Unassigned') return 1;
            if (b === 'Unassigned') return -1;
            return a.localeCompare(b);
        });

        // Sort implementations within each team by total hours (descending)
        sortedTeams.forEach(team => {
            teamGroups[team].implementations.sort((a, b) => b.total - a.total);
        });

        const grandTotal = grandTotalBillable + grandTotalNonBillable;
        const totalImplementations = Object.values(teamGroups).reduce((sum, t) => sum + t.implementations.length, 0);

        // Flatten all items for pagination - each impl is now ONE card with both billable + non-billable
        const allItems = [];
        sortedTeams.forEach(team => {
            const teamData = teamGroups[team];
            const teamTotal = teamData.totalBillable + teamData.totalNonBillable;
            allItems.push({ type: 'team', team, data: teamData, total: teamTotal });
            teamData.implementations.forEach(impl => {
                // Add single implementation card
                allItems.push({ type: 'impl', team, impl });
            });
        });

        // Pagination settings - items per page
        const itemsPerPage = 18;
        const totalPages = Math.ceil(allItems.length / itemsPerPage);
        let currentPage = 1;

        function renderPage(page, animate = false) {
            const startIdx = (page - 1) * itemsPerPage;
            const endIdx = Math.min(startIdx + itemsPerPage, allItems.length);
            const pageItems = allItems.slice(startIdx, endIdx);

            let legendHTML = `
                <div class="custom-legend" style="background: #f8f9fa; border-radius: 6px; padding: 12px; margin-top: 8px; border: 1px solid #dee2e6;">
                    <style>
                        .legend-grid {
                            display: grid;
                            grid-template-columns: repeat(auto-fill, minmax(280px, 1fr));
                            gap: 6px;
                            opacity: ${animate ? '0' : '1'};
                            transition: opacity 0.25s ease-in-out;
                        }
                        .legend-card {
                            display: flex;
                            flex-direction: column;
                            padding: 8px 12px;
                            border-radius: 6px;
                            cursor: pointer;
                            transition: all 0.15s;
                            font-size: 11px;
                            background: white;
                            border: 1px solid #e9ecef;
                            border-left: 4px solid;
                        }
                        .legend-card:hover { background: #e3f2fd; border-color: #90caf9; border-left-width: 4px; transform: translateY(-1px); box-shadow: 0 2px 6px rgba(0,0,0,0.08); }
                        .legend-card.highlighted { background: #bbdefb; border-color: #64b5f6; }
                        .legend-card.dimmed { opacity: 0.35; }
                        .legend-card-name {
                            font-weight: 600;
                            color: #333;
                            overflow: hidden;
                            text-overflow: ellipsis;
                            white-space: nowrap;
                            margin-bottom: 6px;
                            padding-bottom: 6px;
                            border-bottom: 1px solid #eee;
                        }
                        .legend-card-values {
                            display: flex;
                            align-items: center;
                            justify-content: space-between;
                            gap: 12px;
                        }
                        .legend-card-item {
                            display: flex;
                            align-items: center;
                            flex: 1;
                        }
                        .legend-card-item.billable { color: #333; }
                        .legend-card-item.nonbillable { color: #666; }
                        .legend-card-dot { width: 8px; height: 8px; border-radius: 50%; margin-right: 5px; flex-shrink: 0; }
                        .legend-card-type { margin-right: 4px; }
                        .legend-card-hours { font-weight: 600; }
                        .legend-team-header {
                            grid-column: 1 / -1;
                            display: flex;
                            align-items: center;
                            justify-content: space-between;
                            padding: 8px 12px;
                            border-radius: 4px;
                            font-size: 11px;
                            font-weight: 600;
                            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
                            color: white;
                            margin-top: 6px;
                        }
                        .legend-team-header:first-child { margin-top: 0; }
                        .legend-nav { display: flex; align-items: center; justify-content: space-between; margin-top: 10px; padding-top: 10px; border-top: 1px solid #dee2e6; }
                        .legend-nav-btn { background: #fff; border: 1px solid #dee2e6; border-radius: 4px; padding: 5px 12px; cursor: pointer; font-size: 12px; font-weight: 500; transition: all 0.15s; }
                        .legend-nav-btn:hover:not(:disabled) { background: #667eea; color: white; border-color: #667eea; }
                        .legend-nav-btn:disabled { opacity: 0.4; cursor: not-allowed; }
                        .legend-summary { font-size: 11px; color: #555; }
                        .legend-summary strong { color: #333; }
                    </style>
                    <div class="legend-grid" id="legend-grid">
            `;

            pageItems.forEach(item => {
                if (item.type === 'team') {
                    const teamPercent = grandTotal > 0 ? ((item.total / grandTotal) * 100).toFixed(0) : 0;
                    legendHTML += `
                        <div class="legend-team-header">
                            <span>${item.team} <span style="font-weight: normal; opacity: 0.9; margin-left: 6px;">(${item.data.implementations.length})</span></span>
                            <span style="font-weight: normal;">
                                <span style="opacity: 0.8;">${item.total.toFixed(0)}h</span>
                                <span style="background: rgba(255,255,255,0.25); padding: 2px 6px; border-radius: 10px; margin-left: 6px;">${teamPercent}%</span>
                            </span>
                        </div>
                    `;
                } else if (item.type === 'impl') {
                    const impl = item.impl;
                    const totalHrs = impl.billable + impl.nonBillable;
                    legendHTML += `
                        <div class="legend-card"
                             style="border-left-color: ${impl.colors[0]};"
                             data-impl="${impl.name}"
                             title="${impl.name}&#10;Total: ${totalHrs.toFixed(1)} hrs&#10;Billable: ${impl.billable.toFixed(1)} hrs&#10;Non-Billable: ${impl.nonBillable.toFixed(1)} hrs">
                            <div class="legend-card-name">${impl.name}</div>
                            <div class="legend-card-values">
                                <div class="legend-card-item billable">
                                    <span class="legend-card-dot" style="background: ${impl.colors[0]};"></span>
                                    <span class="legend-card-type">Billable</span>
                                    <span class="legend-card-hours">${impl.billable.toFixed(0)}h</span>
                                </div>
                                <div class="legend-card-item nonbillable">
                                    <span class="legend-card-dot" style="background: ${impl.colors[1]};"></span>
                                    <span class="legend-card-type">Non-Billable</span>
                                    <span class="legend-card-hours">${impl.nonBillable.toFixed(0)}h</span>
                                </div>
                            </div>
                        </div>
                    `;
                }
            });

            legendHTML += `</div>`;

            // Navigation footer with pagination
            legendHTML += `
                <div class="legend-nav">
                    <div class="legend-summary">
                        <strong>${grandTotal.toFixed(0)} hrs</strong> total
                        <span style="margin: 0 8px; color: #ccc;">|</span>
                        <span style="color: #28a745;">●</span> <strong>${grandTotalBillable.toFixed(0)}h</strong> billable
                        <span style="margin: 0 8px; color: #ccc;">|</span>
                        <span style="color: #6c757d;">●</span> <strong>${grandTotalNonBillable.toFixed(0)}h</strong> non-billable
                        <span style="margin: 0 8px; color: #ccc;">|</span>
                        <strong>${sortedTeams.length}</strong> teams · <strong>${totalImplementations}</strong> implementations
                    </div>
                    <div class="d-flex align-items-center">
                        <button class="legend-nav-btn" id="legend-prev" ${page === 1 ? 'disabled' : ''}>◀ Prev</button>
                        <span style="font-size: 12px; min-width: 70px; text-align: center; font-weight: 500;">${page} / ${totalPages}</span>
                        <button class="legend-nav-btn" id="legend-next" ${page === totalPages ? 'disabled' : ''}>Next ▶</button>
                    </div>
                </div>
            `;

            legendHTML += `</div>`;

            if (animate) {
                $('#custom-legend-container').html(legendHTML);
                setTimeout(() => {
                    $('#legend-grid').css('opacity', '1');
                }, 50);
            } else {
                $('#custom-legend-container').html(legendHTML);
            }

            // Bind hover events for highlighting
            $('.legend-card').on('mouseenter', function() {
                const implName = $(this).data('impl');
                highlightSeries(implName, true);
                $(this).addClass('highlighted');
            }).on('mouseleave', function() {
                const implName = $(this).data('impl');
                highlightSeries(implName, false);
                $(this).removeClass('highlighted');
            });

            // Click to toggle series visibility
            $('.legend-card').on('click', function() {
                const implName = $(this).data('impl');
                toggleSeriesVisibility(implName);
            });

            // Pagination handlers with transition
            $('#legend-prev').on('click', function() {
                if (currentPage > 1) {
                    currentPage--;
                    renderPage(currentPage, true);
                }
            });

            $('#legend-next').on('click', function() {
                if (currentPage < totalPages) {
                    currentPage++;
                    renderPage(currentPage, true);
                }
            });
        }

        function highlightSeries(implName, highlight) {
            chart.series.forEach(s => {
                const isTargetSeries = s.name.startsWith(implName + ' -');
                const isSpecialSeries = s.name.includes('Prediction') || s.name.includes('Capacity');

                if (highlight) {
                    if (isTargetSeries) {
                        s.setState('hover');
                        s.group && s.group.toFront();
                    } else if (!isSpecialSeries) {
                        s.setState('inactive');
                    }
                } else {
                    s.setState('normal');
                }
            });
        }

        function toggleSeriesVisibility(implName) {
            let anyVisible = false;
            chart.series.forEach(s => {
                if (s.name.startsWith(implName + ' -')) {
                    anyVisible = anyVisible || s.visible;
                }
            });

            chart.series.forEach(s => {
                if (s.name.startsWith(implName + ' -')) {
                    if (anyVisible) {
                        s.hide();
                    } else {
                        s.show();
                    }
                }
            });
            // Update legend item appearance
            $(`.legend-card[data-impl="${implName}"]`).toggleClass('dimmed', anyVisible);
        }

        // Initial render
        renderPage(1);
    }

    load_chart();
    Object.values(filters).forEach(ctrl => { ctrl.df.onchange = () => load_chart(); });
};
