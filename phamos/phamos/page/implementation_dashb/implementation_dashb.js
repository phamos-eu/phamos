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
                const implementationTeams = r.message.implementation_teams || {};


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
                            nonBillable: new Array(categories.length).fill(0),
                            team: implementationTeams[impl] || 'Unassigned'
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

                // Chart rendering
                $('#chart-container').html(`
                    <div class="d-flex justify-content-start mb-2">
                        <button id="toggle-legend" class="btn btn-sm btn-outline-secondary">Show Legend</button>
                    </div>
                    <div id="implementation-chart" style="height:600px;"></div>
                    <div id="custom-legend-container" style="display: none;"></div>
                `);

                const chart = Highcharts.chart('implementation-chart', {
                    chart: { zoomType: 'xy' },
                    legend: { enabled: false },
                    title: { text: 'Billable vs Non-Billable Time with Prediction' },
                    xAxis: { categories: categories },
                    yAxis: { title: { text: 'Time (hrs)' } },
                    tooltip: {
                        shared: true,
                        formatter: function () {
                            let total = 0;
                            let s = `<b>${this.x}</b><br/>`;
                            this.points.forEach(point => {
                                s += `<span style="color:${point.color}">\u25CF</span> 
                                    ${point.series.name}: <b>${point.y} hrs</b><br/>`;
                                if (!point.series.name.includes('Prediction')) total += point.y;
                            });
                            s += `<hr/><b>Total Worked Hrs: ${total} hrs</b>`;
                            return s;
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
                const isSpecialSeries = s.name.includes('Prediction') || s.name.includes('Internal');
                
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
