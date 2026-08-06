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

        this.makeLayout();
        this.makeFilters();
        this.loadData();
    }

    makeLayout() {
        const root = $(this.page.main);
        root.empty();

        root.append(`
            <div class="gitlab-issue-dashboard">
                <style>
                    .gitlab-issue-dashboard .gid-filter-card,
                    .gitlab-issue-dashboard .gid-section-card {
                        background: linear-gradient(180deg, #ffffff 0%, #f7fafc 100%);
                        border: 1px solid #dbe5ef;
                        border-radius: 12px;
                        padding: 16px;
                        box-shadow: 0 4px 14px rgba(15, 23, 42, 0.06);
                    }

                    .gitlab-issue-dashboard .gid-title {
                        font-size: 16px;
                        font-weight: 700;
                        color: #12344d;
                        margin-bottom: 8px;
                    }

                    .gitlab-issue-dashboard .gid-subtitle {
                        font-size: 12px;
                        color: #4a6572;
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

                    .gitlab-issue-dashboard .gid-kpi-green { background: #2e7d32; }
                    .gitlab-issue-dashboard .gid-kpi-amber { background: #ef6c00; }
                    .gitlab-issue-dashboard .gid-kpi-red { background: #c62828; }

                    .gitlab-issue-dashboard .gid-table-wrap {
                        max-height: 360px;
                        overflow: auto;
                    }
                </style>

                <div class="gid-filter-card" style="margin-bottom: 16px;">
                    <div class="gid-title">${__("Filters")}</div>
                    <div id="gid-filter-summary" class="gid-subtitle"></div>
                    <div class="row">
                        <div class="col-md-8">
                            <div id="filter-projects"></div>
                        </div>
                        <div class="col-md-4">
                            <div id="filter-year"></div>
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
        this.$yearFilter = root.find("#filter-year");
        this.$filterSummary = root.find("#gid-filter-summary");
        this.$applyBtn = root.find("#gid-apply-filters");
        this.$resetBtn = root.find("#gid-reset-filters");
        this.$agingKpis = root.find("#aging-kpis");
        this.$agingChart = root.find("#aging-chart");
        this.$flowChart = root.find("#flow-chart");
        this.$flowTable = root.find("#flow-table");
    }

    makeFilters() {
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

        this.filters.year = frappe.ui.form.make_control({
            parent: this.$yearFilter,
            df: {
                label: __("Year"),
                fieldname: "year",
                fieldtype: "Select",
                options: this.getLastFiveYears(),
                default: String(new Date().getFullYear()),
                reqd: 1,
                onchange: () => {
                    this.updateFilterState();
                    this.loadData();
                },
            },
            render_input: true,
        });

        this.filters.year.set_value(String(new Date().getFullYear()));

        this.$applyBtn.on("click", () => this.loadData());
        this.$resetBtn.on("click", () => this.resetFilters());
        this.page.set_primary_action(__("Apply Filters"), () => this.loadData());
        this.updateFilterState();
    }

    resetFilters() {
        this.filters.projects.set_value([]);
        this.filters.year.set_value(String(new Date().getFullYear()));
        this.updateFilterState();
        this.loadData();
    }

    updateFilterState() {
        const projects = this.normalizeProjectsValue(this.filters.projects.get_value() || []);
        const year = this.filters.year.get_value() || String(new Date().getFullYear());
        const summary = projects.length
            ? __("{0} project(s) selected, Year: {1}", [projects.length, year])
            : __("All projects, Year: {0}", [year]);
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
            const year = this.filters.year.get_value();

            const response = await frappe.call({
                method: "phamos.gitlab_integration.page.gitlab_issue_dashboard.gitlab_issue_dashboard.get_gitlab_issue_dashboard_data",
                args: {
                    projects,
                    year,
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

        const aging = (this.currentData && this.currentData.aging) || {};
        const projectBuckets = aging.project_buckets || [];
        const projectTitles = (this.currentData && this.currentData.project_titles) || {};
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
                colors: ["#2E7D32", "#EF6C00", "#C62828"],
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
            colors: ["#2E7D32", "#EF6C00", "#C62828"],
        });
    }

    renderFlowChart() {
        this.$flowChart.empty();

        const monthly = (this.currentData && this.currentData.monthly_flow) || [];
        const selectedProjects = (this.currentData && this.currentData.projects) || [];

        const monthAgg = {};
        for (let i = 1; i <= 12; i++) {
            monthAgg[i] = { month: "", opened: 0, closed: 0 };
        }

        monthly.forEach((row) => {
            const include = selectedProjects.length === 0 || selectedProjects.includes(row.gitlab_project);
            if (!include) return;

            const m = row.month_no;
            if (!monthAgg[m]) return;

            monthAgg[m].month = row.month || monthAgg[m].month;
            monthAgg[m].opened += row.opened || 0;
            monthAgg[m].closed += row.closed || 0;
        });

        const labels = [];
        const openedValues = [];
        const closedValues = [];

        Object.keys(monthAgg).forEach((monthNo) => {
            labels.push(monthAgg[monthNo].month || monthNo);
            openedValues.push(monthAgg[monthNo].opened);
            closedValues.push(monthAgg[monthNo].closed);
        });

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
            colors: ["#1976D2", "#43A047"],
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
            const monthNo = row.month_no;
            if (!byMonth[monthNo]) {
                byMonth[monthNo] = {
                    month: row.month || String(monthNo),
                    opened: 0,
                    closed: 0,
                };
            }

            byMonth[monthNo].opened += row.opened || 0;
            byMonth[monthNo].closed += row.closed || 0;
        });

        const collectiveRows = Object.keys(byMonth)
            .map((monthNo) => {
                const monthData = byMonth[monthNo];
                const opened = monthData.opened;
                const closed = monthData.closed;
                const flowBalance = opened ? (closed / opened) * 100 : 0;

                return {
                    month_no: Number(monthNo),
                    month: monthData.month,
                    opened,
                    closed,
                    flow_balance: flowBalance,
                };
            })
            .filter((row) => row.opened > 0 || row.closed > 0)
            .sort((a, b) => a.month_no - b.month_no);

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

    getLastFiveYears() {
        const currentYear = new Date().getFullYear();
        const years = [];

        for (let i = 0; i < 5; i++) {
            years.push(String(currentYear - i));
        }

        return years.join("\n");
    }
}
