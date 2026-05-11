frappe.pages['team-capacity-overview'].on_page_load = function (wrapper) {

    /* ---------------- HIGHCHARTS MORE MODULE ---------------- */

    function ensure_highcharts_more(callback) {
        if (
            typeof Highcharts !== "undefined" &&
            Highcharts.seriesTypes &&
            Highcharts.seriesTypes.arearange
        ) {
            callback();
            return;
        }

        let version = (typeof Highcharts !== "undefined" && Highcharts.version)
            ? Highcharts.version
            : "12.5.0";

        let existing = document.getElementById("highcharts-more-script");
        if (existing) existing.remove();

        let script = document.createElement("script");
        script.id = "highcharts-more-script";
        script.src = `https://code.highcharts.com/${version}/highcharts-more.js`;

        script.onload = function () { setTimeout(callback, 100); };
        script.onerror = function () {
            console.error("Failed to load highcharts-more.js version:", version);
            frappe.msgprint("Failed to load Highcharts module. Check your internet connection.", "Error");
        };

        document.head.appendChild(script);
    }

    /* ---------------- PAGE SETUP ---------------- */

    var page = frappe.ui.make_app_page({
        parent: wrapper,
        title: 'Team Capacity Overview',
        single_column: true
    });
    $("<style>")
    .prop("type", "text/css")
    .html(`
    /* ── Shared toggle ── */
    .comparison-toggle-wrapper {
        margin-top: -5px;
        display: flex;
        align-items: center;
        gap: 20px;
    }

    .comparison-toggle-wrapper input[type="checkbox"] {
        opacity: 0;
        width: 0;
        height: 0;
        position: absolute;
    }

    .comparison-toggle-wrapper .slider {
        position: relative;
        width: 42px;
        height: 22px;
        background-color: #d1d5db;
        border-radius: 20px;
        transition: background 0.25s ease;
        display: inline-block;
    }

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

    .comparison-toggle-wrapper input:checked + .slider {
        background-color: #000;
    }

    .comparison-toggle-wrapper input:checked + .slider:before {
        transform: translate(20px, -50%);
    }

    .comparison-toggle-wrapper .toggle-label {
        font-weight: 500;
        color: #444;
    }

    /* ── Chart wrapper ── */
    .tco-chart-area {
        width: 100%;
        padding: 20px 0 30px 0;
    }

    /* ── Switch buttons ── */
    .chart-switcher-row {
        display: flex;
        align-items: center;
        gap: 0;
        margin-bottom: 16px;
    }

    .chart-switch-btn {
        padding: 7px 24px;
        font-size: 13px;
        font-weight: 600;
        border: 1.5px solid #000;
        background: #fff;
        color: #000;
        cursor: pointer;
        transition: all 0.18s ease;
        outline: none;
        line-height: 1.4;
    }

    .chart-switch-btn:first-child {
        border-radius: 6px 0 0 6px;
        border-right: none;
    }

    .chart-switch-btn:last-child {
        border-radius: 0 6px 6px 0;
    }

    .chart-switch-btn.active {
        background: #000;
        color: #fff;
    }

    .chart-switch-btn:hover:not(.active) {
        background: #f3f3f3;
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
            return frappe.call({
                method: "phamos.phamos.page.team_capacity_overview.team_capacity_overview.get_all_teams",
                args: { txt: txt || "" },
                async: false
            }).responseJSON.message.map(name => ({
                label: name,
                value: name,
                description: ""
            }));
        }
    });

    /* ---------------- SHARED TOGGLE ---------------- */

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
        page.comparison_type.toggle($(this).is(":checked"));
        load_active_chart();
    });

    page.comparison_type = page.add_field({
        fieldname: 'comparison_type',
        label: 'Comparison Period',
        fieldtype: 'Select',
        options: [
            {
                label: "Same period last year",
                value: "last_year"
            },
            {
                label: "Same period last month (30 days back)",
                value: "last_month"
            }
        ],
        default: "last_year",
        hidden: true
    });

    page.comparison_type.df.onchange = function () {
        load_active_chart();
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

            load_active_chart();
        }
    });

    /* ---------------- CHART AREA ---------------- */

    let $main = $(page.main);

    $main.append(`
        <div class="tco-chart-area">

            <div class="chart-switcher-row">
                <button class="chart-switch-btn active" id="btn_chart_original">
                    Team Weekly Capacity
                </button>

                <button class="chart-switch-btn" id="btn_chart_capacity">
                    Capacity vs Time Spent
                </button>
            </div>

            <div id="panel_chart_original">
                <div id="team_chart" style="width:100%;height:600px;"></div>
            </div>

            <div id="panel_chart_capacity" style="display:none;">
                <div id="capacity_chart" style="width:100%;height:600px;"></div>
            </div>

        </div>
    `);

    /* ---------------- SWITCH EVENTS ---------------- */

    let active_chart = "original";

    $("#btn_chart_original").on("click", function () {

        active_chart = "original";

        $("#btn_chart_original").addClass("active");
        $("#btn_chart_capacity").removeClass("active");

        $("#panel_chart_original").show();
        $("#panel_chart_capacity").hide();

        load_chart();
    });

    $("#btn_chart_capacity").on("click", function () {

        active_chart = "capacity";

        $("#btn_chart_capacity").addClass("active");
        $("#btn_chart_original").removeClass("active");

        $("#panel_chart_capacity").show();
        $("#panel_chart_original").hide();

        load_capacity_chart();
    });

    /* ---------------- DEFAULT DATES ---------------- */

    let d = get_month_weeks();

    page.from_date.set_value(d.start_date);
    page.to_date.set_value(d.end_date);

    page.from_date.$input.on("change", load_active_chart);
    page.to_date.$input.on("change", load_active_chart);
    page.team.df.onchange = load_active_chart;

    load_chart();

    /* ---------------- ACTIVE CHART ---------------- */

    function load_active_chart() {
        if (active_chart === "original") {
            load_chart();
        } else {
            load_capacity_chart();
        }
    }

    /* ================================================================
       CHART 1
    ================================================================ */

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

    /* ================================================================
       CHART 2
    ================================================================ */

    function load_capacity_chart() {

        let from_date = page.from_date.get_value();
        let to_date = page.to_date.get_value();

        if (!from_date || !to_date) {

            let d = get_month_weeks();

            from_date = d.start_date;
            to_date = d.end_date;
        }

        let hist_enabled = $("#enable_comparison_toggle").is(":checked");

        let hist_type = page.comparison_type.get_value() || "last_year";

        let filters = {
            from_date,
            to_date,
            team: page.team.get_value() || [],
            enable_comparison: hist_enabled,
            comparison_type: hist_type
        };

        frappe.call({
            method: "phamos.phamos.page.team_capacity_overview.team_capacity_overview.get_team_capacity",
            args: { filters },

            callback(r) {
                if (r.message) {

                    render_capacity_chart(
                        r.message.weeks,
                        r.message.teams,
                        r.message.actual_line,
                        r.message.historical_actual_line,
                        hist_enabled,
                        hist_type
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

    /* ================================================================
       RENDER CHART 1
    ================================================================ */

    function render_chart(weeks, teams, actual_line, historical_actual_line) {

        if (typeof Highcharts === "undefined") {
            frappe.msgprint("Highcharts is not loaded.", "Error");
            return;
        }

        let series = [];

        let colors = [
            "#7cb5ec",
            "#434348",
            "#90ed7d",
            "#f7a35c",
            "#8085e9",
            "#f15c80"
        ];

        teams.forEach(function (team, i) {

            series.push({
                name: team.name,
                type: "line",
                data: team.data,
                color: team.color || colors[i % colors.length],
                lineWidth: 2,
                marker: { enabled: false }
            });
        });

        // Actual time spent — dashed black line
        series.push({
            name: "Actual Time Spent",
            type: "line",
            data: actual_line,
            dashStyle: "ShortDash",
            color: "#000",
            lineWidth: 2,
            marker: { enabled: false }
        });

        // Historical comparison — dotted gray line
        if (historical_actual_line) {
            series.push({
                name: "Historical Actual Time",
                type: "line",
                data: historical_actual_line,
                dashStyle: "Dot",
                color: "#666",
                lineWidth: 2,
                marker: { enabled: false }
            });
        }

        Highcharts.chart("team_chart", {

            chart: {
                type: "line"
            },

            title: {
                text: "Team Weekly Capacity"
            },

            xAxis: {
                categories: weeks
            },

            yAxis: {
                min: 0,
                title: { text: "Hours" }
            },

            series
        });
    }

    /* ================================================================
       RENDER CHART 2
    ================================================================ */

    function render_capacity_chart(
        weeks,
        teams,
        actual_line,
        historical_actual_line,
        hist_enabled,
        hist_type
    ) {

        if (typeof Highcharts === "undefined") {
            frappe.msgprint("Highcharts is not loaded.", "Error");
            return;
        }

        let series = [];

        let colors = [
            "#7cb5ec",
            "#a407b3",
            "#90ed7d",
            "#f7a35c",
            "#424bf7",
            "#f15c80"
        ];

        let total_capacity = weeks.map(function (_, wi) {

            return teams.reduce(function (sum, team) {
                return sum + (team.data[wi] || 0);
            }, 0);
        });

        series.push({
            name: "Total Capacity",
            type: "line",
            data: total_capacity,
            color: "#000",
            lineWidth: 3,
            zIndex: 10,
            marker: { enabled: false }
        });

        series.push({
            name: "Total Time Spent",
            type: "line",
            data: actual_line,
            dashStyle: "Dot",
            color: "#000",
            lineWidth: 2.5,
            zIndex: 9,
            marker: { enabled: false }
        });

        if (hist_enabled && historical_actual_line) {

            series.push({
                name: "Historical Total Time Spent",
                type: "line",
                data: historical_actual_line,
                dashStyle: "Dot",
                color: "#888",
                lineWidth: 2,
                zIndex: 8,
                marker: { enabled: false }
            });
        }
        console.log("TEAMS DATA", teams);
        teams.forEach(function (team, i) {

            let color = team.color || colors[i % colors.length];

            series.push({
                name: team.name + " Capacity",
                type: "line",
                data: team.data,
                color: color,
                lineWidth: 2,
                zIndex: 5,
                marker: { enabled: false }
            });

            /* ── Current Team Time Spent ── */

            if (team.actual_data) {

                series.push({
                    name: team.name + " Time Spent",
                    type: "line",
                    data: team.actual_data,
                    dashStyle: "Dot",
                    color: color,
                    lineWidth: 2,
                    zIndex: 4,
                    marker: { enabled: false }
                });
            }

            /* ── Historical Team Time Spent ── */

            if (hist_enabled && team.historical_actual_data) {

                series.push({
                    name: team.name + " Historical Time Spent",
                    type: "line",
                    data: team.historical_actual_data,
                    dashStyle: "ShortDash",
                    color: color,
                    lineWidth: 2,
                    opacity: 0.55,
                    zIndex: 3,
                    marker: { enabled: false }
                });
            }
        });

        Highcharts.chart("capacity_chart", {

            chart: {
                type: "line"
            },

            title: {
                text: "Capacity vs Time Spent (Team-wise)"
            },

            xAxis: {
                categories: weeks
            },

            yAxis: {
                min: 0,
                title: { text: "Hours" }
            },

            series
        });
    }

};
