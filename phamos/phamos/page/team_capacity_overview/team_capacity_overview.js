frappe.pages['team-capacity-overview'].on_page_load = function(wrapper) {
    var page = frappe.ui.make_app_page({
        parent: wrapper,
        title: 'Team Capacity Overview',
        single_column: true
    });

    // Filters
    page.from_date = page.add_field({
        fieldname: 'from_date',
        label: 'From Date',
        fieldtype: 'Date'
    });

    page.to_date = page.add_field({
        fieldname: 'to_date',
        label: 'To Date',
        fieldtype: 'Date'
    });

    page.team = page.add_field({
        fieldname: "team",
        label: "Team",
        fieldtype: "MultiSelectList",
        get_data: function(txt) {
            return frappe.db.get_link_options("Team", txt);
        }
    });

    page.add_field({
        fieldname: 'clear',
        label: 'Clear',
        fieldtype: 'Button',
        click: function() {
            let d = get_month_weeks();
            page.from_date.set_value(d.start_date);
            page.to_date.set_value(d.end_date);
            page.team.set_value([]);
            load_chart();
        }
    });

    // Chart container
    $(wrapper).find('.layout-main').append(`
        <div id="team_chart" style="height:650px; width:100%; margin-top:20px;"></div>
    `);

    // Set default dates
    let d = get_month_weeks();
    page.from_date.set_value(d.start_date);
    page.to_date.set_value(d.end_date);

    // Event listeners
    page.from_date.$input.on("change", load_chart);
    page.to_date.$input.on("change", load_chart);
    page.team.df.onchange = () => {
    console.log("Team selected:", page.team.get_value());
    load_chart();
};


    // Initial load
    load_chart();

    // Load chart function
    function load_chart() {
        let from_date = page.from_date.get_value();
        let to_date = page.to_date.get_value();

        if (!from_date || !to_date) {
            let d = get_month_weeks();
            from_date = d.start_date;
            to_date = d.end_date;
            page.from_date.set_value(from_date);
            page.to_date.set_value(to_date);
        }

        let filters = { 
            from_date, 
            to_date, 
            team: page.team.get_value() || [] 
        };
        console.log("Team selected:", page.team.get_value());

        console.log("Filters:", filters);

        frappe.call({
            method: "phamos.phamos.page.team_capacity_overview.team_capacity_overview.get_team_capacity",
            args: { filters: filters },
            callback: function(r) {
                if (r.message) {
                    render_chart(r.message.weeks, r.message.teams, r.message.actual_line);
                }
            }
        });
    }

    // Helper: get start/end dates of current month
    function get_month_weeks() {
        let today = new Date();
        let year = today.getFullYear();
        let month = today.getMonth();

        let start = new Date(year, month, 1);
        let end = new Date(year, month + 1, 0);

        let start_with_prev = new Date(start);
        start_with_prev.setDate(start_with_prev.getDate() - 14);

        return {
            start_date: frappe.datetime.obj_to_str(start_with_prev),
            end_date: frappe.datetime.obj_to_str(end)
        };
    }

    // Render Highcharts function remains same
    function render_chart(weeks, teams, actual_line) {
        teams.sort((a, b) => a.data.reduce((x,y)=>x+y,0) - b.data.reduce((x,y)=>x+y,0));
        let chart_series = [];

        if (teams.length > 0) {
            chart_series.push({ name: teams[0].name, type: "area", data: teams[0].data, color: teams[0].color });
        }

        for (let i = 1; i < teams.length; i++) {
            let lower = teams[i - 1].data;
            let upper = teams[i].data;
            let range = upper.map((val, idx) => [lower[idx], val]);
            chart_series.push({
                name: teams[i].name,
                type: "arearange",
                data: range,
                color: teams[i].color,
                fillOpacity: 0.6,
                lineWidth: 0,
                tooltip: { pointFormatter: function () { return `<span style="color:${this.color}">●</span> ${this.series.name}: <b>${this.high}</b><br/>`; } }
            });
        }

        chart_series.push({
            name: "Actual Time Spent",
            data: actual_line,
            type: "line",
            dashStyle: "ShortDash",
            lineWidth: 2,
            color: "#000",
            marker: { enabled: true }
        });

        frappe.require(["https://code.highcharts.com/highcharts-more.js"], () => {
            Highcharts.chart("team_chart", {
                chart: { type: "area" },
                title: { text: "Team Weekly Capacity" },
                xAxis: { categories: weeks },
                yAxis: { min: 0, title: { text: "Hours" } },
                series: chart_series
            });
        });
    }

};
