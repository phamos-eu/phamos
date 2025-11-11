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
                    chart.update({ legend: { enabled: legendVisible } });
                    $(this).text(legendVisible ? "Hide Legend" : "Show Legend");
                });
            }
        });
    }

    load_chart();
    Object.values(filters).forEach(ctrl => { ctrl.df.onchange = () => load_chart(); });
};
