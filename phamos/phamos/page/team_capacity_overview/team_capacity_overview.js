frappe.pages['team-capacity-overview'].on_page_load = function (wrapper) {

    var page = frappe.ui.make_app_page({
        parent: wrapper,
        title: 'Team Capacity Overview',
        single_column: true
    });
    $("<style>")
    .prop("type", "text/css")
    .html(`
    /* Toggle wrapper spacing */
    .comparison-toggle-wrapper {
        margin-top: -5px;
        display: flex;
        align-items: center;
        gap: 20px;
    }

    /* Hide the checkbox */
    .comparison-toggle-wrapper input[type="checkbox"] {
        opacity: 0;
        width: 0;
        height: 0;
        position: absolute;
    }

    /* Slider track */
    .comparison-toggle-wrapper .slider {
        position: relative;
        width: 42px;
        height: 22px;
        background-color: #d1d5db;
        border-radius: 20px;
        transition: background 0.25s ease;
        display: inline-block;
    }

    /* Knob */
    .comparison-toggle-wrapper .slider:before {
        content: "";
        position: absolute;
        width: 16px;
        height: 16px;
        left: 3px;
        top: 50%;
        transform: translateY(-50%);
        background-color: #fff;
        border-radius: 50%;
        box-shadow: 0 1px 4px rgba(0,0,0,0.25);
        transition: transform 0.25s ease;
    }

    /* Checked state */
    .comparison-toggle-wrapper input:checked + .slider {
        background-color: #5463ecff;
    }

    .comparison-toggle-wrapper input:checked + .slider:before {
        transform: translate(20px, -50%);
    }

    /* Label text */
    .comparison-toggle-wrapper .toggle-label {
        font-weight: 500;
        color: #444;
    }
    `)
    .appendTo("head");




    /* ---------------- FILTERS ---------------- */

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
        get_data: function (txt) {
            return frappe.db.get_link_options("Team", txt);
        }
    });
    /* ---------------- CUSTOM TOGGLE (ONLY ONCE) ---------------- */

    const comparison_wrapper = $(`
        <div class="comparison-toggle-wrapper">
            <label class="switch">
                <input type="checkbox" id="enable_comparison_toggle">
                <span class="slider"></span>
            </label>
            <span class="toggle-label">Enable Historical Comparison</span>
        </div>
    `);

    page.page_form.append(comparison_wrapper);

    $("#enable_comparison_toggle").on("change", function () {
        let enabled = $(this).is(":checked");
        page.comparison_type.toggle(enabled);
        load_chart();
    });

    page.comparison_type = page.add_field({
        fieldname: 'comparison_type',
        label: 'Comparison Period',
        fieldtype: 'Select',
        options: [
            { label: "Same period last year", value: "last_year" },
            { label: "Same period last month (30 days back)", value: "last_month" }
        ],
        default: "last_year",
        hidden: true
    });
    page.comparison_type.df.onchange = function() {
        load_chart();
    };

    page.add_field({
        fieldname: 'clear',
        label: 'Clear',
        fieldtype: 'Button',
        click() {
            let d = get_month_weeks();
            page.from_date.set_value(d.start_date);
            page.to_date.set_value(d.end_date);
            page.team.set_value([]);
            $("#enable_comparison_toggle").prop("checked", false);
            page.comparison_type.toggle(false);
            load_chart();
        }
    });

    /* ---------------- CHART CONTAINER ---------------- */

    $(wrapper).find('.layout-main').append(`
        <div id="team_chart" style="height:650px;width:100%;margin-top:20px;"></div>
    `);

    /* ---------------- DEFAULT DATES ---------------- */

    let d = get_month_weeks();
    page.from_date.set_value(d.start_date);
    page.to_date.set_value(d.end_date);

    page.from_date.$input.on("change", load_chart);
    page.to_date.$input.on("change", load_chart);
    page.team.df.onchange = load_chart;

    load_chart();

    /* ---------------- LOAD CHART ---------------- */

    function load_chart() {
        let from_date = page.from_date.get_value();
        let to_date = page.to_date.get_value();

        if (!from_date || !to_date) {
            let d = get_month_weeks();
            from_date = d.start_date;
            to_date = d.end_date;
        }

        let filters = {
            from_date,
            to_date,
            team: page.team.get_value() || [],
            enable_comparison: $("#enable_comparison_toggle").is(":checked"),
            comparison_type: page.comparison_type.get_value()
        };

        frappe.call({
            method: "phamos.phamos.page.team_capacity_overview.team_capacity_overview.get_team_capacity",
            args: { filters },
            callback(r) {
                if (r.message) {
                    render_chart(
                        r.message.weeks,
                        r.message.teams,
                        r.message.actual_line,
                        r.message.historical_actual_line
                    );
                }
            }
        });
    }

    /* ---------------- HELPERS ---------------- */

    function get_month_weeks() {
        let today = new Date();
        let start = new Date(today.getFullYear(), today.getMonth(), 1);
        let end = new Date(today.getFullYear(), today.getMonth() + 1, 0);
        start.setDate(start.getDate() - 14);

        return {
            start_date: frappe.datetime.obj_to_str(start),
            end_date: frappe.datetime.obj_to_str(end)
        };
    }

    function render_chart(weeks, teams, actual_line, historical_actual_line) {

        let series = [];

        teams.sort((a, b) =>
            a.data.reduce((x, y) => x + y, 0) -
            b.data.reduce((x, y) => x + y, 0)
        );

        if (teams.length) {
            series.push({
                name: teams[0].name,
                type: "area",
                data: teams[0].data,
                color: teams[0].color
            });
        }

        for (let i = 1; i < teams.length; i++) {
            series.push({
                name: teams[i].name,
                type: "arearange",
                data: teams[i].data.map((v, idx) => [teams[i - 1].data[idx], v]),
                color: teams[i].color,
                lineWidth: 0
            });
        }

        series.push({
            name: "Actual Time Spent",
            type: "line",
            data: actual_line,
            dashStyle: "ShortDash",
            color: "#000"
        });

        if (historical_actual_line) {
            series.push({
                name: "Historical Actual Time",
                type: "line",
                data: historical_actual_line,
                dashStyle: "Dot",
                color: "#666"
            });
        }
        frappe.require(["https://code.highcharts.com/highcharts-more.js"], () => {

            Highcharts.chart("team_chart", {
            chart: { type: "area" },
            title: { text: "Team Weekly Capacity" },
            xAxis: { categories: weeks },
            yAxis: { min: 0, title: { text: "Hours" } },

            tooltip: {
            shared: true,
            formatter: function () {

            let idx = this.points[0].point.index;

            // Current week start & end
            let weekStart = new Date(page.from_date.get_value());
            weekStart.setDate(weekStart.getDate() + (idx * 7));

            let weekEnd = new Date(weekStart);
            weekEnd.setDate(weekEnd.getDate() + 6);

            let actualRange =
                frappe.datetime.obj_to_str(weekStart) +
                " - " +
                frappe.datetime.obj_to_str(weekEnd);

            let html = `<b>${actualRange}</b><br/>`;

            this.points.forEach(p => {

                if (p.series.name === "Historical Actual Time") {

                    let hFrom = new Date(weekStart);
                    let hTo = new Date(weekEnd);

                    if (page.comparison_type.get_value() === "last_year") {
                        hFrom.setFullYear(hFrom.getFullYear() - 1);
                        hTo.setFullYear(hTo.getFullYear() - 1);
                    } else if (page.comparison_type.get_value() === "last_month") {
                        hFrom.setMonth(hFrom.getMonth() - 1);
                        hTo.setMonth(hTo.getMonth() - 1);
                    }

                    let histRange =
                        frappe.datetime.obj_to_str(hFrom) +
                        " - " +
                        frappe.datetime.obj_to_str(hTo);

                    html += `
                        <span style="color:${p.color}">●</span>
                        ${p.series.name} (${histRange}):
                        <b>${p.y}</b><br/>
                    `;
                } else {
                    html += `
                        <span style="color:${p.color}">●</span>
                        ${p.series.name}:
                        <b>${p.y}</b><br/>
                    `;
                }
            });

            return html;
        }
        },
            series
        });

        });
    }
        function shift_range(range, value, unit) {
        let parts = range.split(" - ");

        let start = new Date(parts[0]);
        let end = new Date(parts[1]);

        if (unit === "year") {
            start.setFullYear(start.getFullYear() + value);
            end.setFullYear(end.getFullYear() + value);
        } else {
            start.setMonth(start.getMonth() + value);
            end.setMonth(end.getMonth() + value);
        }

        return `
            ${frappe.datetime.obj_to_str(start)}
            -
            ${frappe.datetime.obj_to_str(end)}
        `;
    }

};
