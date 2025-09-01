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
    filters.implementation = create_filter('Implementation', 'Link', 'implementation', '#filter-section', null, 'Implementation');
    // Clear Filters Button Handler
    $('#clear-filters-btn').on('click', () => {
        Object.values(filters).forEach(ctrl => {
            ctrl.set_value('');
        });
        load_chart(); 
    });

    // Chart rendering
    function load_chart() {
        let from_date = filters.from_date.get_value();
        let to_date = filters.to_date.get_value();

        if (!from_date && !to_date) {
            const today = frappe.datetime.get_today(); 
            const past6 = frappe.datetime.add_months(today, -6); 
            const future6 = frappe.datetime.add_months(today, 6);

            from_date = past6;
            to_date = future6;

            filters.from_date.set_value(from_date);
            filters.to_date.set_value(to_date);
        }
        const args = {
            from_date: filters.from_date.get_value(),
            to_date: filters.to_date.get_value(),
            team: filters.team.get_value(),
            implementation: filters.implementation.get_value()
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

                const categorySet = new Set();
                planningData.forEach(row => categorySet.add(row.month_and_year));
                predictionData.forEach(row => categorySet.add(row.month_and_year));

                const categories = Array.from(categorySet).sort();
                const categoryIndexMap = {};
                categories.forEach((month, idx) => {
                    categoryIndexMap[month] = idx;
                });

                const series = [];
                const colorPairs = [
                    ['#3399ff', '#99ccff'], // Blue pair
                    ['#28a745', '#90ee90'], // Green pair
                    ['#ff9933', '#ffcc99'], // Orange pair
                    ['#800080', '#d1b3ff'], // Purple pair
                    ['#cc0000', '#ff6666']  // Red pair
                ];

                const groupedData = {};

                planningData.forEach(row => {
                    let impl = row.implementation_name || 'Unknown';

                    if (filters.implementation.get_value()) {
                        impl = filters.implementation.get_value();
                    }
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

                let colorIndex = 0;

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
                const isFiltered = filters.implementation.get_value() || filters.team.get_value();

    if (isFiltered) {
        // 1. Individual Prediction Dots (scatter)
        const predictionDots = predictionData.map(row => ({
            x: categoryIndexMap[row.month_and_year],
            y: row.prediction || 0
        }));

        series.push({
            name: 'Prediction',
            type: 'scatter',
            data: predictionDots,
            color: '#ff0000',
            marker: {
                symbol: 'circle',
                radius: 4
            },
            tooltip: {
                pointFormat: '<span style="color:{point.color}">\u25CF</span> Prediction: <b>{point.y}</b><br/>'
            }
        });

        // 2. Average Prediction Line (filtered)
        const averagePredictions = categories.map(month => {
            const filtered = predictionData.filter(row => row.month_and_year === month);
            const total = filtered.reduce((sum, r) => sum + (r.prediction || 0), 0);
            return filtered.length ? total / filtered.length : null;
        });

        series.push({
            name: 'Average Prediction',
            type: 'line',
            data: averagePredictions,
            color: '#000000',
            dashStyle: 'Dot',
            marker: { enabled: true, radius: 3 },
            tooltip: {
                pointFormat: '<span style="color:{point.color}">\u25CF</span> Avg Prediction: <b>{point.y:.2f}</b><br/>'
            }
        });

    } else {
        // Cumulative Prediction Line (all implementations)
        const cumulativePredictions = categories.map(month => {
            const monthRows = predictionData.filter(row => row.month_and_year === month);
            return monthRows.reduce((sum, r) => sum + (r.prediction || 0), 0);
        });

        series.push({
            name: 'Cumulative Prediction',
            type: 'line',
            data: cumulativePredictions,
            color: '#000000',
            dashStyle: 'Solid',
            marker: { enabled: true, radius: 3 },
            tooltip: {
                pointFormat: '<span style="color:{point.color}">\u25CF</span> Cumulative: <b>{point.y}</b><br/>'
            }
        });
            }
                const predictionPoints = predictionData.map(row => ({
                    x: categoryIndexMap[row.month_and_year],
                    y: row.prediction || 0
                }));

                const averagePredictions = categories.map(month => {
                    const filtered = predictionData.filter(row => row.month_and_year === month);
                    const total = filtered.reduce((sum, r) => sum + (r.prediction || 0), 0);
                    return filtered.length ? total / filtered.length : null;
                });

                $('#chart-container').html('<div id="implementation-chart" style="height:600px;"></div>');
                Highcharts.chart('implementation-chart', {
                chart: { zoomType: 'xy' },
                title: { text: 'Billable vs Non-Billable Time with Prediction' },
                xAxis: {
                    categories: categories,
                    title: { text: 'Month' }
                },
                yAxis: {
                    title: { text: 'Time (hrs)' }
                },
                tooltip: {
                    shared: true,
                    formatter: function () {
                        let total = 0;
                        let s = `<b>${this.x}</b><br/>`;

                        this.points.forEach(point => {
                            s += `<span style="color:${point.color}">\u25CF</span> 
                                ${point.series.name}: <b>${point.y} hrs</b><br/>`;

                            if (!point.series.name.includes('Prediction')) {
                                total += point.y;
                            }
                        });

                        s += `<hr/><b>Total Worked Hrs: ${total} hrs</b>`;
                        return s;
                    }
                },
                plotOptions: {
                    area: {
                        stacking: 'normal',
                        marker: { enabled: false }
                    },
                    line: {
                        marker: { enabled: true, radius: 3 }
                    }
                },
                series: series 
            });
            }
        });
    }
    // Static color map for each implementation
    const implementationColorMap = {};
    const colorPairs = [
        ['#3399ff', '#99ccff'],
        ['#28a745', '#90ee90'],
        ['#ff9933', '#ffcc99'],
        ['#800080', '#d1b3ff'],
        ['#cc0000', '#ff6666']
    ];
    let globalColorIndex = 0;

    // Call on page load
    load_chart();

    // Call again on any filter change
    Object.values(filters).forEach(ctrl => {
        ctrl.df.onchange = () => {
            load_chart();
        };
    });
};
