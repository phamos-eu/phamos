frappe.pages["gitlab-issue-dashboard"].on_page_load = function (wrapper) {
    frappe.ui.make_app_page({
        parent: wrapper,
        title: __("GitLab Issue Dashboard"),
        single_column: true,
    });

    const page = wrapper.page;
    page.gitlabIssueDashboard = new GitLabIssueDashboard(page, wrapper);
};

class GitLabIssueDashboard {
    constructor(page, wrapper) {
        this.page = page;
        this.wrapper = wrapper;
        this.filters = {};
        this.currentData = null;
        this.themeObserver = null;
        this.lastThemeKey = "";

        this.makeLayout();
        this.makeFilters();
        this.setupThemeWatcher();
        this.loadData();
    }

    makeLayout() {
        const root = $(this.page.main);
        root.empty();

        root.append(`
            <div class="gitlab-issue-dashboard">
                <style>
                    .gitlab-issue-dashboard {
                        --gid-card-bg: var(--card-bg, #ffffff);
                        --gid-card-border: var(--border-color, #dbe5ef);
                        --gid-title-color: var(--heading-color, #12344d);
                        --gid-subtitle-color: var(--text-muted, #4a6572);
                        --gid-grid-color: var(--border-color, #dbe5ef);
                        --gid-shadow: 0 4px 14px rgba(15, 23, 42, 0.06);
                        --gid-aging-green: #2e7d32;
                        --gid-aging-amber: #ef6c00;
                        --gid-aging-red: #c62828;
                        --gid-flow-opened: #1976d2;
                        --gid-flow-closed: #43a047;
                    }

                    .gitlab-issue-dashboard.gid-theme-dark {
                        --gid-card-bg: var(--fg-color, #1a1f2b);
                        --gid-card-border: var(--border-color, #3a4250);
                        --gid-title-color: var(--heading-color, #f2f5f7);
                        --gid-subtitle-color: var(--text-muted, #c3c7ce);
                        --gid-grid-color: rgba(255, 255, 255, 0.18);
                        --gid-shadow: 0 8px 24px rgba(0, 0, 0, 0.35);
                        --gid-aging-green: #2e7d32;
                        --gid-aging-amber: #ef6c00;
                        --gid-aging-red: #c62828;
                        --gid-flow-opened: #1e88e5;
                        --gid-flow-closed: #43a047;
                    }

                    .gitlab-issue-dashboard .gid-filter-card,
                    .gitlab-issue-dashboard .gid-section-card {
                        background: var(--gid-card-bg);
                        border: 1px solid var(--gid-card-border);
                        border-radius: 12px;
                        padding: 16px;
                        box-shadow: var(--gid-shadow);
                    }

                    .gitlab-issue-dashboard .gid-title {
                        font-size: 16px;
                        font-weight: 700;
                        color: var(--gid-title-color);
                        margin-bottom: 8px;
                    }

                    .gitlab-issue-dashboard .gid-subtitle {
                        font-size: 12px;
                        color: var(--gid-subtitle-color);
                        margin-bottom: 12px;
                    }

                    .gitlab-issue-dashboard .gid-actions {
                        display: flex;
                        gap: 8px;
                        justify-content: flex-end;
                        margin-top: 8px;
                    }

                    .gitlab-issue-dashboard .gid-kpi-row {
                        display: grid;
                        grid-template-columns: repeat(3, minmax(140px, 1fr));
                        gap: 10px;
                        margin-bottom: 12px;
                    }

                    .gitlab-issue-dashboard .gid-kpi {
                        border-radius: 10px;
                        padding: 10px 12px;
                        color: #fff;
                        font-weight: 600;
                    }

                    .gitlab-issue-dashboard .gid-kpi small {
                        display: block;
                        opacity: 0.9;
                        font-size: 11px;
                        margin-bottom: 4px;
                    }

                    .gitlab-issue-dashboard .gid-kpi strong {
                        font-size: 20px;
                        line-height: 1;
                    }

                    .gitlab-issue-dashboard .gid-kpi-green { background: var(--gid-aging-green); }
                    .gitlab-issue-dashboard .gid-kpi-amber { background: var(--gid-aging-amber); }
                    .gitlab-issue-dashboard .gid-kpi-red { background: var(--gid-aging-red); }

                    .gitlab-issue-dashboard .gid-table-wrap {
                        max-height: 360px;
                        overflow: auto;
                    }

                    .gitlab-issue-dashboard .table {
                        color: var(--gid-title-color);
                    }

                    .gitlab-issue-dashboard .table > thead > tr > th,
                    .gitlab-issue-dashboard .table > tbody > tr > td {
                        border-color: var(--gid-card-border);
                    }

                    .gitlab-issue-dashboard .chart-container svg text {
                        fill: var(--gid-subtitle-color) !important;
                    }

                    .gitlab-issue-dashboard .chart-container .title,
                    .gitlab-issue-dashboard .chart-container .chart-title {
                        fill: var(--gid-title-color) !important;
                    }

                    .gitlab-issue-dashboard .chart-container svg line,
                    .gitlab-issue-dashboard .chart-container svg path.domain {
                        stroke: var(--gid-grid-color) !important;
                    }
                </style>

                <div class="gid-filter-card" style="margin-bottom: 16px;">
                    <div class="gid-title">${__("Filters")}</div>
                    <div id="gid-filter-summary" class="gid-subtitle"></div>
                    <div class="row">
                        <div class="col-md-6">
                            <div id="filter-projects"></div>
                        </div>
                        <div class="col-md-3">
                            <div id="filter-from-date"></div>
                        </div>
                        <div class="col-md-3">
                            <div id="filter-to-date"></div>
                        </div>
                    </div>
                    <div class="gid-actions">
                        <button class="btn btn-default btn-sm" id="gid-reset-filters">${__("Reset")}</button>
                        <button class="btn btn-primary btn-sm" id="gid-apply-filters">${__("Apply")}</button>
                    </div>
                </div>

                <div class="gid-section-card" style="margin-bottom: 16px;">
                    <div class="gid-title">${__("Closed Tickets Aging")}</div>
                    <div class="gid-kpi-row" id="aging-kpis"></div>
                    <div id="aging-chart" style="min-height: 320px;"></div>
                </div>

                <div class="gid-section-card" style="margin-bottom: 16px;">
                    <div class="gid-title">${__("Opened vs Closed by Month")}</div>
                    <div id="flow-chart" style="min-height: 320px;"></div>
                </div>

                <div class="gid-section-card">
                    <div class="gid-title">${__("Flow Balance Table")}</div>
                    <div class="gid-table-wrap" id="flow-table"></div>
                </div>
            </div>
        `);

        this.$projectsFilter = root.find("#filter-projects");
        this.$fromDateFilter = root.find("#filter-from-date");
        this.$toDateFilter = root.find("#filter-to-date");
        this.$dashboard = root.find(".gitlab-issue-dashboard");
        this.$filterSummary = root.find("#gid-filter-summary");
        this.$applyBtn = root.find("#gid-apply-filters");
        this.$resetBtn = root.find("#gid-reset-filters");
        this.$agingKpis = root.find("#aging-kpis");
        this.$agingChart = root.find("#aging-chart");
        this.$flowChart = root.find("#flow-chart");
        this.$flowTable = root.find("#flow-table");

        this.applyThemeClass();
    }

    setupThemeWatcher() {
        this.lastThemeKey = this.getThemeKey();

        if (this.themeObserver) {
            this.themeObserver.disconnect();
        }

        this.themeObserver = new MutationObserver(() => {
            const nextThemeKey = this.getThemeKey();
            if (nextThemeKey === this.lastThemeKey) return;

            this.lastThemeKey = nextThemeKey;
            this.applyThemeClass();

            if (this.currentData) {
                this.renderAgingChart();
                this.renderFlowChart();
            }
        });

        this.themeObserver.observe(document.documentElement, {
            attributes: true,
            attributeFilter: ["class", "data-theme", "data-theme-mode", "style"],
        });
    }

    getThemeKey() {
        const htmlClass = document.documentElement.className || "";
        const htmlDataTheme = document.documentElement.getAttribute("data-theme") || "";
        const htmlDataThemeMode = document.documentElement.getAttribute("data-theme-mode") || "";
        const bodyClass = document.body ? document.body.className : "";
        return [htmlClass, htmlDataTheme, htmlDataThemeMode, bodyClass].join("|");
    }

    isDarkTheme() {
        const html = document.documentElement;
        const body = document.body;
        const classText = `${html.className || ""} ${body ? body.className || "" : ""}`.toLowerCase();
        const dataTheme = `${html.getAttribute("data-theme") || ""} ${html.getAttribute("data-theme-mode") || ""}`.toLowerCase();
        return classText.includes("dark") || dataTheme.includes("dark");
    }

    applyThemeClass() {
        if (!this.$dashboard || !this.$dashboard.length) return;
        this.$dashboard.toggleClass("gid-theme-dark", this.isDarkTheme());
    }

    getChartColors(type) {
        const rootNode = this.$dashboard && this.$dashboard.length
            ? this.$dashboard[0]
            : document.documentElement;
        const styles = window.getComputedStyle(rootNode);

        if (type === "aging") {
            return [
                styles.getPropertyValue("--gid-aging-green").trim() || "#2E7D32",
                styles.getPropertyValue("--gid-aging-amber").trim() || "#EF6C00",
                styles.getPropertyValue("--gid-aging-red").trim() || "#C62828",
            ];
        }

        return [
            styles.getPropertyValue("--gid-flow-opened").trim() || "#1976D2",
            styles.getPropertyValue("--gid-flow-closed").trim() || "#43A047",
        ];
    }

    makeFilters() {
        const defaultRange = this.getDefaultDateRange();

        this.filters.projects = frappe.ui.form.make_control({
            parent: this.$projectsFilter,
            df: {
                label: __("GitLab Projects"),
                fieldname: "gitlab_projects",
                fieldtype: "MultiSelectList",
                get_data: (txt) => frappe.db.get_link_options("GitLab Project", txt),
                onchange: () => {
                    this.updateFilterState();
                    this.loadData();
                },
            },
            render_input: true,
        });

        this.filters.from_date = frappe.ui.form.make_control({
            parent: this.$fromDateFilter,
            df: {
                label: __("From Date"),
                fieldname: "from_date",
                fieldtype: "Date",
                default: defaultRange.from_date,
                reqd: 1,
                onchange: () => {
                    this.updateFilterState();
                    this.loadData();
                },
            },
            render_input: true,
        });

        this.filters.to_date = frappe.ui.form.make_control({
            parent: this.$toDateFilter,
            df: {
                label: __("To Date"),
                fieldname: "to_date",
                fieldtype: "Date",
                default: defaultRange.to_date,
                reqd: 1,
                onchange: () => {
                    this.updateFilterState();
                    this.loadData();
                },
            },
            render_input: true,
        });

        this.filters.from_date.set_value(defaultRange.from_date);
        this.filters.to_date.set_value(defaultRange.to_date);

        this.$applyBtn.on("click", () => this.loadData());
        this.$resetBtn.on("click", () => this.resetFilters());
        this.page.set_primary_action(__("Apply Filters"), () => this.loadData());
        this.updateFilterState();
    }

    resetFilters() {
        const defaultRange = this.getDefaultDateRange();
        this.filters.projects.set_value([]);
        this.filters.from_date.set_value(defaultRange.from_date);
        this.filters.to_date.set_value(defaultRange.to_date);
        this.updateFilterState();
        this.loadData();
    }

    updateFilterState() {
        const projects = this.normalizeProjectsValue(this.filters.projects.get_value() || []);
        const { from_date: defaultFromDate, to_date: defaultToDate } = this.getDefaultDateRange();
        const fromDate = this.filters.from_date.get_value() || defaultFromDate;
        const toDate = this.filters.to_date.get_value() || defaultToDate;
        const summary = projects.length
            ? __(
                "{0} project(s) selected, Date Range: {1} to {2}",
                [projects.length, fromDate, toDate]
            )
            : __("All projects, Date Range: {0} to {1}", [fromDate, toDate]);
        this.$filterSummary.text(summary);
    }

    normalizeProjectsValue(rawValue) {
        if (!rawValue) return [];

        if (Array.isArray(rawValue)) {
            return rawValue
                .map((item) => {
                    if (typeof item === "string") return item;
                    if (item && typeof item === "object") return item.value || item.name || "";
                    return "";
                })
                .filter(Boolean);
        }

        if (typeof rawValue === "string") {
            const value = rawValue.trim();
            if (!value) return [];

            if (value.startsWith("[")) {
                try {
                    return this.normalizeProjectsValue(JSON.parse(value));
                } catch (e) {
                    return value.split(",").map((v) => v.trim()).filter(Boolean);
                }
            }

            return value.split(",").map((v) => v.trim()).filter(Boolean);
        }

        return [];
    }

    async loadData() {
        try {
            frappe.dom.freeze(__("Loading dashboard..."));

            const projects = this.normalizeProjectsValue(this.filters.projects.get_value() || []);
            const { from_date: defaultFromDate, to_date: defaultToDate } = this.getDefaultDateRange();
            const from_date = this.filters.from_date.get_value() || defaultFromDate;
            const to_date = this.filters.to_date.get_value() || defaultToDate;

            if (from_date > to_date) {
                frappe.msgprint({
                    title: __("Invalid Date Range"),
                    message: __("From Date cannot be after To Date."),
                    indicator: "orange",
                });
                return;
            }

            const response = await frappe.call({
                method: "phamos.gitlab_integration.page.gitlab_issue_dashboard.gitlab_issue_dashboard.get_gitlab_issue_dashboard_data",
                args: {
                    projects,
                    from_date,
                    to_date,
                },
            });

            this.currentData = response.message || {};
            this.updateFilterState();
            this.renderAgingChart();
            this.renderFlowChart();
            this.renderFlowTable();
        } catch (error) {
            frappe.msgprint({
                title: __("Dashboard Error"),
                message: __("Could not load GitLab issue dashboard data."),
                indicator: "red",
            });
            console.error(error);
        } finally {
            frappe.dom.unfreeze();
        }
    }

    renderAgingChart() {
        this.$agingChart.empty();
        this.applyThemeClass();

        const aging = (this.currentData && this.currentData.aging) || {};
        const projectBuckets = aging.project_buckets || [];
        const projectTitles = (this.currentData && this.currentData.project_titles) || {};
        const agingColors = this.getChartColors("aging");
        const values = [
            aging.bucket_0_30 || 0,
            aging.bucket_31_90 || 0,
            aging.bucket_gt_90 || 0,
        ];

        this.$agingKpis.html(`
            <div class="gid-kpi gid-kpi-green"><small>${__("0-30 days")}</small><strong>${values[0]}</strong></div>
            <div class="gid-kpi gid-kpi-amber"><small>${__("31-90 days")}</small><strong>${values[1]}</strong></div>
            <div class="gid-kpi gid-kpi-red"><small>${__(">90 days")}</small><strong>${values[2]}</strong></div>
        `);

        if (aging.mode === "project_compare" && projectBuckets.length > 1) {
            this.agingChart = new frappe.Chart(this.$agingChart[0], {
                title: __("Closed Tickets Aging - Project Comparison"),
                data: {
                    labels: projectBuckets.map((row) => projectTitles[row.project] || row.project || ""),
                    datasets: [
                        {
                            name: __("0-30 days"),
                            values: projectBuckets.map((row) => row.bucket_0_30 || 0),
                        },
                        {
                            name: __("31-90 days"),
                            values: projectBuckets.map((row) => row.bucket_31_90 || 0),
                        },
                        {
                            name: __(">90 days"),
                            values: projectBuckets.map((row) => row.bucket_gt_90 || 0),
                        },
                    ],
                },
                type: "bar",
                height: 300,
                colors: agingColors,
            });
            return;
        }

        const title = aging.mode === "single" && aging.project
            ? __("Closed Tickets Aging - {0}", [aging.project])
            : __("Closed Tickets Aging - Selected Projects");

        this.agingChart = new frappe.Chart(this.$agingChart[0], {
            title,
            data: {
                labels: [__("0-30 days"), __("31-90 days"), __(">90 days")],
                datasets: [
                    {
                        name: __("0-30 days"),
                        values: [values[0], 0, 0],
                    },
                    {
                        name: __("31-90 days"),
                        values: [0, values[1], 0],
                    },
                    {
                        name: __(">90 days"),
                        values: [0, 0, values[2]],
                    },
                ],
            },
            type: "bar",
            height: 300,
            colors: agingColors,
        });
    }

    renderFlowChart() {
        this.$flowChart.empty();
        this.applyThemeClass();

        const monthly = (this.currentData && this.currentData.monthly_flow) || [];
        const selectedProjects = (this.currentData && this.currentData.projects) || [];
        const flowColors = this.getChartColors("flow");
        const monthAgg = {};

        monthly.forEach((row) => {
            const include = selectedProjects.length === 0 || selectedProjects.includes(row.gitlab_project);
            if (!include) return;

            const monthKey = row.month_key || `${row.year_no || ""}-${String(row.month_no || "").padStart(2, "0")}`;
            if (!monthAgg[monthKey]) {
                monthAgg[monthKey] = {
                    month: row.month || monthKey,
                    opened: 0,
                    closed: 0,
                    month_order: row.month_order || 0,
                };
            }

            monthAgg[monthKey].opened += row.opened || 0;
            monthAgg[monthKey].closed += row.closed || 0;
        });

        const sortedMonthKeys = Object.keys(monthAgg).sort((a, b) => {
            const monthOrderDiff = (monthAgg[a].month_order || 0) - (monthAgg[b].month_order || 0);
            if (monthOrderDiff !== 0) return monthOrderDiff;
            return a.localeCompare(b);
        });

        const labels = [];
        const openedValues = [];
        const closedValues = [];

        sortedMonthKeys.forEach((monthKey) => {
            labels.push(monthAgg[monthKey].month || monthKey);
            openedValues.push(monthAgg[monthKey].opened);
            closedValues.push(monthAgg[monthKey].closed);
        });

        if (!labels.length) {
            this.$flowChart.html(`<p class="text-muted">${__("No monthly data found for selected filters.")}</p>`);
            return;
        }

        this.flowChart = new frappe.Chart(this.$flowChart[0], {
            title: __("Opened vs Closed by Month"),
            data: {
                labels,
                datasets: [
                    { name: __("Opened"), values: openedValues },
                    { name: __("Closed"), values: closedValues },
                ],
            },
            type: "bar",
            height: 300,
            colors: flowColors,
        });
    }

    renderFlowTable() {
        const rows = (this.currentData && this.currentData.monthly_flow) || [];
        const projectTitles = (this.currentData && this.currentData.project_titles) || {};

        if (!rows.length) {
            this.$flowTable.html(`<p class="text-muted">${__("No data found for selected filters.")}</p>`);
            return;
        }

        const selectedProjects = (this.currentData && this.currentData.projects) || [];

        if (!selectedProjects.length) {
            this.renderCollectiveFlowTable(rows);
            return;
        }

        const filteredRows = rows.filter((row) => {
            const byProject = selectedProjects.length === 0 || selectedProjects.includes(row.gitlab_project);
            const hasActivity = (row.opened || 0) > 0 || (row.closed || 0) > 0;
            return byProject && hasActivity;
        });

        if (!filteredRows.length) {
            this.$flowTable.html(`<p class="text-muted">${__("No monthly activity for selected project(s).")}</p>`);
            return;
        }

        const html = [
            '<table class="table table-bordered table-hover">',
            "<thead>",
            "<tr>",
            `<th>${__("Project")}</th>`,
            `<th>${__("Month")}</th>`,
            `<th class="text-right">${__("Opened")}</th>`,
            `<th class="text-right">${__("Closed")}</th>`,
            `<th class="text-right">${__("Flow Balance %")}</th>`,
            "</tr>",
            "</thead>",
            "<tbody>",
        ];

        filteredRows.forEach((row) => {
            html.push("<tr>");
            html.push(`<td>${frappe.utils.escape_html(projectTitles[row.gitlab_project] || row.gitlab_project || "")}</td>`);
            html.push(`<td>${frappe.utils.escape_html(row.month || "")}</td>`);
            html.push(`<td class="text-right">${row.opened || 0}</td>`);
            html.push(`<td class="text-right">${row.closed || 0}</td>`);
            html.push(`<td class="text-right">${(row.flow_balance || 0).toFixed(2)}%</td>`);
            html.push("</tr>");
        });

        html.push("</tbody>");
        html.push("</table>");

        this.$flowTable.html(html.join(""));
    }

    renderCollectiveFlowTable(rows) {
        const byMonth = {};

        rows.forEach((row) => {
            const monthKey = row.month_key || `${row.year_no || ""}-${String(row.month_no || "").padStart(2, "0")}`;
            if (!byMonth[monthKey]) {
                byMonth[monthKey] = {
                    month_key: monthKey,
                    month: row.month || monthKey,
                    opened: 0,
                    closed: 0,
                    month_order: row.month_order || 0,
                };
            }

            byMonth[monthKey].opened += row.opened || 0;
            byMonth[monthKey].closed += row.closed || 0;
        });

        const collectiveRows = Object.keys(byMonth)
            .map((monthKey) => {
                const monthData = byMonth[monthKey];
                const opened = monthData.opened;
                const closed = monthData.closed;
                const flowBalance = opened ? (closed / opened) * 100 : 0;

                return {
                    month_key: monthData.month_key,
                    month_order: monthData.month_order,
                    month: monthData.month,
                    opened,
                    closed,
                    flow_balance: flowBalance,
                };
            })
            .filter((row) => row.opened > 0 || row.closed > 0)
            .sort((a, b) => {
                const monthOrderDiff = (a.month_order || 0) - (b.month_order || 0);
                if (monthOrderDiff !== 0) return monthOrderDiff;
                return (a.month_key || "").localeCompare(b.month_key || "");
            });

        if (!collectiveRows.length) {
            this.$flowTable.html(`<p class="text-muted">${__("No monthly activity found.")}</p>`);
            return;
        }

        const html = [
            '<table class="table table-bordered table-hover">',
            "<thead>",
            "<tr>",
            `<th>${__("Project")}</th>`,
            `<th>${__("Month")}</th>`,
            `<th class="text-right">${__("Opened")}</th>`,
            `<th class="text-right">${__("Closed")}</th>`,
            `<th class="text-right">${__("Flow Balance %")}</th>`,
            "</tr>",
            "</thead>",
            "<tbody>",
        ];

        collectiveRows.forEach((row) => {
            html.push("<tr>");
            html.push(`<td>${__("All Projects")}</td>`);
            html.push(`<td>${frappe.utils.escape_html(row.month || "")}</td>`);
            html.push(`<td class="text-right">${row.opened || 0}</td>`);
            html.push(`<td class="text-right">${row.closed || 0}</td>`);
            html.push(`<td class="text-right">${(row.flow_balance || 0).toFixed(2)}%</td>`);
            html.push("</tr>");
        });

        html.push("</tbody>");
        html.push("</table>");

        this.$flowTable.html(html.join(""));
    }

    getDefaultDateRange() {
        const toDate = new Date();
        const fromDate = new Date(toDate);
        fromDate.setMonth(fromDate.getMonth() - 6);

        return {
            from_date: this.formatDate(fromDate),
            to_date: this.formatDate(toDate),
        };
    }

    formatDate(dateObj) {
        const year = dateObj.getFullYear();
        const month = String(dateObj.getMonth() + 1).padStart(2, "0");
        const day = String(dateObj.getDate()).padStart(2, "0");
        return `${year}-${month}-${day}`;
    }
}
