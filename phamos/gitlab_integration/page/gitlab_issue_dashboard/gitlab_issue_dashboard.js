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
        this.compareToCompany = false;
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
                        --gid-lead-main: #6a1b9a;
                        --gid-lead-accent: #5e35b1;
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
                        --gid-lead-main: #8e24aa;
                        --gid-lead-accent: #7e57c2;
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

                    .gitlab-issue-dashboard .gid-compare-toggle {
                        margin-top: 10px;
                        color: var(--gid-title-color);
                        font-size: 13px;
                        display: none;
                    }

                    .gitlab-issue-dashboard .gid-compare-toggle label {
                        display: inline-flex;
                        align-items: center;
                        gap: 8px;
                        margin: 0;
                        cursor: pointer;
                    }

                    .gitlab-issue-dashboard .gid-kpi-row {
                        display: grid;
                        grid-template-columns: repeat(3, minmax(140px, 1fr));
                        gap: 10px;
                        margin-bottom: 12px;
                    }

                    .gitlab-issue-dashboard .gid-kpi-row-lead {
                        grid-template-columns: repeat(5, minmax(120px, 1fr));
                    }

                    .gitlab-issue-dashboard .gid-lead-row {
                        margin-bottom: 12px;
                    }

                    .gitlab-issue-dashboard .gid-lead-row:last-child {
                        margin-bottom: 0;
                    }

                    .gitlab-issue-dashboard .gid-lead-row-label {
                        font-size: 12px;
                        font-weight: 600;
                        color: var(--gid-subtitle-color);
                        margin-bottom: 6px;
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
                    .gitlab-issue-dashboard .gid-kpi-opened { background: var(--gid-flow-opened); }
                    .gitlab-issue-dashboard .gid-kpi-closed { background: var(--gid-flow-closed); }
                    .gitlab-issue-dashboard .gid-kpi-lead-main { background: var(--gid-lead-main); }
                    .gitlab-issue-dashboard .gid-kpi-lead { background: var(--gid-lead-accent); }

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
                        <div class="col-md-4">
                            <div id="filter-projects"></div>
                        </div>
                        <div class="col-md-2">
                            <div id="filter-issue-scope"></div>
                        </div>
                        <div class="col-md-3">
                            <div id="filter-from-date"></div>
                        </div>
                        <div class="col-md-3">
                            <div id="filter-to-date"></div>
                        </div>
                    </div>
                    <div id="gid-compare-company-wrap" class="gid-compare-toggle">
                        <label>
                            <input type="checkbox" id="gid-compare-company" />
                            <span>${__("Compare to Company")}</span>
                        </label>
                    </div>
                    <div class="gid-actions">
                        <button class="btn btn-default btn-sm" id="gid-reset-filters">${__("Reset")}</button>
                        <button class="btn btn-primary btn-sm" id="gid-apply-filters">${__("Apply")}</button>
                    </div>
                </div>

                <div class="gid-section-card" style="margin-bottom: 16px;">
                    <div class="gid-title">${__("Lead Time (Created to Completed)")}</div>
                    <div class="gid-subtitle">${__("Average number of days from ticket creation to completion.")}</div>
                    <div id="lead-time-kpis"></div>
                </div>

                <div class="gid-section-card" style="margin-bottom: 16px;">
                    <div class="gid-title">${__("Closed Tickets Aging")}</div>
                    <div class="gid-kpi-row" id="aging-kpis"></div>
                    <div id="aging-chart" style="min-height: 320px;"></div>
                </div>

                <div class="gid-section-card" style="margin-bottom: 16px;">
                    <div class="gid-title">${__("Opened vs Closed by Month")}</div>
                    <div class="gid-kpi-row" id="flow-kpis"></div>
                    <div id="flow-chart" style="min-height: 320px;"></div>
                </div>

                <div class="gid-section-card">
                    <div class="gid-title">${__("Flow Balance Table")}</div>
                    <div class="gid-table-wrap" id="flow-table"></div>
                </div>
            </div>
        `);

        this.$projectsFilter = root.find("#filter-projects");
        this.$issueScopeFilter = root.find("#filter-issue-scope");
        this.$fromDateFilter = root.find("#filter-from-date");
        this.$toDateFilter = root.find("#filter-to-date");
        this.$dashboard = root.find(".gitlab-issue-dashboard");
        this.$filterSummary = root.find("#gid-filter-summary");
        this.$compareCompanyWrap = root.find("#gid-compare-company-wrap");
        this.$compareCompanyToggle = root.find("#gid-compare-company");
        this.$applyBtn = root.find("#gid-apply-filters");
        this.$resetBtn = root.find("#gid-reset-filters");
        this.$leadTimeKpis = root.find("#lead-time-kpis");
        this.$agingKpis = root.find("#aging-kpis");
        this.$agingChart = root.find("#aging-chart");
        this.$flowKpis = root.find("#flow-kpis");
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

        this.filters.issue_scope = frappe.ui.form.make_control({
            parent: this.$issueScopeFilter,
            df: {
                label: __("Issue Type"),
                fieldname: "issue_scope",
                fieldtype: "Select",
                options: `${__("Both")}\n${__("Parent Issues")}\n${__("Child Issues")}`,
                default: __("Both"),
                reqd: 1,
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
        this.filters.issue_scope.set_value(__("Both"));

        this.$applyBtn.on("click", () => this.loadData());
        this.$resetBtn.on("click", () => this.resetFilters());
        this.$compareCompanyToggle.on("change", () => {
            this.compareToCompany = !!this.$compareCompanyToggle.prop("checked");
            this.updateFilterState();
            this.loadData();
        });
        this.page.set_primary_action(__("Apply Filters"), () => this.loadData());
        this.updateFilterState();
    }

    resetFilters() {
        const defaultRange = this.getDefaultDateRange();
        this.filters.projects.set_value([]);
        this.filters.issue_scope.set_value(__("Both"));
        this.filters.from_date.set_value(defaultRange.from_date);
        this.filters.to_date.set_value(defaultRange.to_date);
        this.compareToCompany = false;
        this.$compareCompanyToggle.prop("checked", false);
        this.updateFilterState();
        this.loadData();
    }

    updateFilterState() {
        const projects = this.normalizeProjectsValue(this.filters.projects.get_value() || []);
        const { from_date: defaultFromDate, to_date: defaultToDate } = this.getDefaultDateRange();
        const fromDate = this.filters.from_date.get_value() || defaultFromDate;
        const toDate = this.filters.to_date.get_value() || defaultToDate;
        const issueScope = this.normalizeIssueScopeValue(this.filters.issue_scope.get_value());
        const issueScopeLabelMap = {
            both: __("Both"),
            parent: __("Parent Issues"),
            child: __("Child Issues"),
        };
        const issueScopeLabel = issueScopeLabelMap[issueScope] || __("Both");
        const canCompareToCompany = projects.length === 1;

        if (canCompareToCompany) {
            this.$compareCompanyWrap.show();
        } else {
            this.$compareCompanyWrap.hide();
            this.compareToCompany = false;
            this.$compareCompanyToggle.prop("checked", false);
        }

        const summary = projects.length
            ? __(
                "{0} project(s) selected, Date Range: {1} to {2}",
                [projects.length, fromDate, toDate]
            )
            : __("All projects, Date Range: {0} to {1}", [fromDate, toDate]);
        const compareNote = canCompareToCompany && this.compareToCompany
            ? ` | ${__("Comparison: Company")}`
            : "";
        this.$filterSummary.text(`${summary} | ${__("Issue Type")}: ${issueScopeLabel}${compareNote}`);
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

    normalizeIssueScopeValue(rawValue) {
        const value = (rawValue || "").toString().trim().toLowerCase();
        if (value === "parent" || value === "parent issues") return "parent";
        if (value === "child" || value === "child issues") return "child";
        return "both";
    }

    async loadData() {
        try {
            frappe.dom.freeze(__("Loading dashboard..."));

            const projects = this.normalizeProjectsValue(this.filters.projects.get_value() || []);
            const { from_date: defaultFromDate, to_date: defaultToDate } = this.getDefaultDateRange();
            const from_date = this.filters.from_date.get_value() || defaultFromDate;
            const to_date = this.filters.to_date.get_value() || defaultToDate;
            const issue_scope = this.normalizeIssueScopeValue(this.filters.issue_scope.get_value());
            const compare_to_company = this.compareToCompany && projects.length === 1;

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
                    issue_scope,
                    compare_to_company,
                },
            });

            this.currentData = response.message || {};
            this.compareToCompany = !!this.currentData.compare_to_company;
            this.$compareCompanyToggle.prop("checked", this.compareToCompany);
            this.updateFilterState();
            this.renderLeadTimeKpis();
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

    renderLeadTimeKpis() {
        const leadTime = (this.currentData && this.currentData.lead_time) || {};
        const mode = leadTime.mode || "combined";
        const projectTitles = (this.currentData && this.currentData.project_titles) || {};

        const formatDays = (value) => {
            if (value === null || value === undefined) return __("N/A");
            return __("{0} days", [value]);
        };

        const buildRow = (label, data) => {
            const rolling = (data && data.rolling) || {};
            const labelHtml = label
                ? `<div class="gid-lead-row-label">${frappe.utils.escape_html(label)}</div>`
                : "";
            return `
                <div class="gid-lead-row">
                    ${labelHtml}
                    <div class="gid-kpi-row gid-kpi-row-lead">
                        <div class="gid-kpi gid-kpi-lead-main"><small>${__("Selected Filter Avg")}</small><strong>${formatDays(data ? data.filtered : null)}</strong></div>
                        <div class="gid-kpi gid-kpi-lead"><small>${__("Last Month")}</small><strong>${formatDays(rolling.last_month)}</strong></div>
                        <div class="gid-kpi gid-kpi-lead"><small>${__("Last 3 Months")}</small><strong>${formatDays(rolling.last_3_months)}</strong></div>
                        <div class="gid-kpi gid-kpi-lead"><small>${__("Last 6 Months")}</small><strong>${formatDays(rolling.last_6_months)}</strong></div>
                        <div class="gid-kpi gid-kpi-lead"><small>${__("Last 12 Months")}</small><strong>${formatDays(rolling.last_12_months)}</strong></div>
                    </div>
                </div>
            `;
        };

        let html = "";

        if (mode === "single" && leadTime.company) {
            const projectTitle = projectTitles[leadTime.project] || leadTime.project || __("Project");
            html += buildRow(projectTitle, leadTime);
            html += buildRow(__("Company"), leadTime.company);
        } else if (mode === "project_compare" && (leadTime.project_lead_times || []).length) {
            leadTime.project_lead_times.forEach((row) => {
                const title = projectTitles[row.project] || row.project || __("Project");
                html += buildRow(title, row);
            });
        } else {
            html += buildRow(null, leadTime);
        }

        this.$leadTimeKpis.html(html);
    }

    renderAgingChart() {
        this.$agingChart.empty();
        this.applyThemeClass();

        const aging = (this.currentData && this.currentData.aging) || {};
        const companyAging = (this.currentData && this.currentData.company_aging) || {};
        const compareToCompany = !!(this.currentData && this.currentData.compare_to_company);
        const selectedProjects = (this.currentData && this.currentData.projects) || [];
        const compareSingleProject = compareToCompany && selectedProjects.length === 1;
        const projectBuckets = aging.project_buckets || [];
        const projectTitles = (this.currentData && this.currentData.project_titles) || {};
        const agingColors = this.getChartColors("aging");
        const values = [
            aging.bucket_0_30 || 0,
            aging.bucket_31_90 || 0,
            aging.bucket_gt_90 || 0,
        ];
        const companyValues = [
            companyAging.bucket_0_30 || 0,
            companyAging.bucket_31_90 || 0,
            companyAging.bucket_gt_90 || 0,
        ];

        this.$agingKpis.html(`
            <div class="gid-kpi gid-kpi-green"><small>${__("0-30 days")}</small><strong>${values[0]}</strong></div>
            <div class="gid-kpi gid-kpi-amber"><small>${__("31-90 days")}</small><strong>${values[1]}</strong></div>
            <div class="gid-kpi gid-kpi-red"><small>${__(">90 days")}</small><strong>${values[2]}</strong></div>
        `);

        if (compareSingleProject) {
            const selectedProject = selectedProjects[0];
            const selectedTitle = projectTitles[selectedProject] || selectedProject || __("Project");

            this.agingChart = new frappe.Chart(this.$agingChart[0], {
                title: __("Closed Tickets Aging - Project vs Company"),
                data: {
                    labels: [selectedTitle, __("Company")],
                    datasets: [
                        {
                            name: __("0-30 days"),
                            values: [values[0], companyValues[0]],
                        },
                        {
                            name: __("31-90 days"),
                            values: [values[1], companyValues[1]],
                        },
                        {
                            name: __(">90 days"),
                            values: [values[2], companyValues[2]],
                        },
                    ],
                },
                type: "bar",
                height: 300,
                colors: agingColors,
            });
            return;
        }

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
        const companyMonthly = (this.currentData && this.currentData.company_monthly_flow) || [];
        const selectedProjects = (this.currentData && this.currentData.projects) || [];
        const projectTitles = (this.currentData && this.currentData.project_titles) || {};
        const compareToCompany = !!(this.currentData && this.currentData.compare_to_company);
        const compareSingleProject = compareToCompany && selectedProjects.length === 1;
        const flowColors = this.getChartColors("flow");
        const filteredRows = monthly.filter((row) => {
            return selectedProjects.length === 0 || selectedProjects.includes(row.gitlab_project);
        });

        const monthMeta = {};
        filteredRows.forEach((row) => {
            const monthKey = row.month_key || `${row.year_no || ""}-${String(row.month_no || "").padStart(2, "0")}`;
            if (!monthMeta[monthKey]) {
                monthMeta[monthKey] = {
                    month: row.month || monthKey,
                    month_order: row.month_order || 0,
                };
            }
        });

        if (compareSingleProject) {
            companyMonthly.forEach((row) => {
                const monthKey = row.month_key || `${row.year_no || ""}-${String(row.month_no || "").padStart(2, "0")}`;
                if (!monthMeta[monthKey]) {
                    monthMeta[monthKey] = {
                        month: row.month || monthKey,
                        month_order: row.month_order || 0,
                    };
                }
            });
        }

        const monthAgg = {};
        filteredRows.forEach((row) => {
            const monthKey = row.month_key || `${row.year_no || ""}-${String(row.month_no || "").padStart(2, "0")}`;
            if (!monthAgg[monthKey]) {
                monthAgg[monthKey] = {
                    opened: 0,
                    closed: 0,
                };
            }

            monthAgg[monthKey].opened += row.opened || 0;
            monthAgg[monthKey].closed += row.closed || 0;
        });

        const totals = filteredRows.reduce((acc, row) => {
            acc.opened += row.opened || 0;
            acc.closed += row.closed || 0;
            return acc;
        }, { opened: 0, closed: 0 });

        this.$flowKpis.html(`
            <div class="gid-kpi gid-kpi-opened"><small>${__("Opened Total")}</small><strong>${totals.opened}</strong></div>
            <div class="gid-kpi gid-kpi-closed"><small>${__("Closed Total")}</small><strong>${totals.closed}</strong></div>
        `);

        const sortedMonthKeys = Object.keys(monthMeta).sort((a, b) => {
            const monthOrderDiff = (monthMeta[a].month_order || 0) - (monthMeta[b].month_order || 0);
            if (monthOrderDiff !== 0) return monthOrderDiff;
            return a.localeCompare(b);
        });

        const labels = sortedMonthKeys.map((monthKey) => monthMeta[monthKey].month || monthKey);

        if (!labels.length) {
            this.$flowChart.html(`<p class="text-muted">${__("No monthly data found for selected filters.")}</p>`);
            return;
        }

        if (compareSingleProject) {
            const selectedProject = selectedProjects[0];
            const selectedTitle = projectTitles[selectedProject] || selectedProject || __("Project");

            const companyMap = {};
            companyMonthly.forEach((row) => {
                const monthKey = row.month_key || `${row.year_no || ""}-${String(row.month_no || "").padStart(2, "0")}`;
                companyMap[monthKey] = {
                    opened: row.opened || 0,
                    closed: row.closed || 0,
                };
            });

            const selectedOpenedValues = sortedMonthKeys.map((monthKey) => (monthAgg[monthKey] ? monthAgg[monthKey].opened : 0));
            const selectedClosedValues = sortedMonthKeys.map((monthKey) => (monthAgg[monthKey] ? monthAgg[monthKey].closed : 0));
            const companyOpenedValues = sortedMonthKeys.map((monthKey) => (companyMap[monthKey] ? companyMap[monthKey].opened : 0));
            const companyClosedValues = sortedMonthKeys.map((monthKey) => (companyMap[monthKey] ? companyMap[monthKey].closed : 0));

            this.flowChart = new frappe.Chart(this.$flowChart[0], {
                title: __("Opened vs Closed by Month - Project vs Company"),
                data: {
                    labels,
                    datasets: [
                        { name: `${selectedTitle} - ${__("Opened")}`, values: selectedOpenedValues },
                        { name: `${selectedTitle} - ${__("Closed")}`, values: selectedClosedValues },
                        { name: `${__("Company")} - ${__("Opened")}`, values: companyOpenedValues },
                        { name: `${__("Company")} - ${__("Closed")}`, values: companyClosedValues },
                    ],
                },
                type: "bar",
                height: 300,
                colors: ["#1976d2", "#43a047", "#ef6c00", "#8e24aa"],
            });
            return;
        }

        // Show project-wise bars for multi-project comparison instead of summing into one pair.
        if (selectedProjects.length > 1) {
            const projectMonthMap = {};
            filteredRows.forEach((row) => {
                const project = row.gitlab_project;
                const monthKey = row.month_key || `${row.year_no || ""}-${String(row.month_no || "").padStart(2, "0")}`;

                if (!projectMonthMap[project]) {
                    projectMonthMap[project] = {};
                }

                projectMonthMap[project][monthKey] = {
                    opened: row.opened || 0,
                    closed: row.closed || 0,
                };
            });

            const comparePalette = [
                ["#1976d2", "#43a047"],
                ["#ef6c00", "#8e24aa"],
                ["#00897b", "#c62828"],
                ["#3949ab", "#f9a825"],
            ];

            const datasets = [];
            const chartColors = [];

            selectedProjects.forEach((project, index) => {
                const title = projectTitles[project] || project || "";
                const palette = comparePalette[index % comparePalette.length];

                const openedValues = sortedMonthKeys.map((monthKey) => {
                    return (projectMonthMap[project] && projectMonthMap[project][monthKey]
                        ? projectMonthMap[project][monthKey].opened
                        : 0);
                });

                const closedValues = sortedMonthKeys.map((monthKey) => {
                    return (projectMonthMap[project] && projectMonthMap[project][monthKey]
                        ? projectMonthMap[project][monthKey].closed
                        : 0);
                });

                datasets.push({ name: `${title} - ${__("Opened")}`, values: openedValues });
                datasets.push({ name: `${title} - ${__("Closed")}`, values: closedValues });
                chartColors.push(palette[0], palette[1]);
            });

            this.flowChart = new frappe.Chart(this.$flowChart[0], {
                title: __("Opened vs Closed by Month - Project Comparison"),
                data: {
                    labels,
                    datasets,
                },
                type: "bar",
                height: 300,
                colors: chartColors,
            });
            return;
        }

        const openedValues = [];
        const closedValues = [];

        sortedMonthKeys.forEach((monthKey) => {
            openedValues.push((monthAgg[monthKey] && monthAgg[monthKey].opened) || 0);
            closedValues.push((monthAgg[monthKey] && monthAgg[monthKey].closed) || 0);
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
        const compareToCompany = !!(this.currentData && this.currentData.compare_to_company);

        if (!selectedProjects.length) {
            this.renderCollectiveFlowTable(rows);
            return;
        }

        if (selectedProjects.length === 1 && compareToCompany) {
            this.renderSingleProjectVsCompanyFlowTable(rows, selectedProjects[0], projectTitles);
            return;
        }

        if (selectedProjects.length > 1) {
            this.renderProjectComparisonFlowTable(rows, selectedProjects, projectTitles);
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

    renderSingleProjectVsCompanyFlowTable(rows, selectedProject, projectTitles) {
        const companyRows = (this.currentData && this.currentData.company_monthly_flow) || [];
        const monthMap = {};

        rows.forEach((row) => {
            if (row.gitlab_project !== selectedProject) return;

            const monthKey = row.month_key || `${row.year_no || ""}-${String(row.month_no || "").padStart(2, "0")}`;
            if (!monthMap[monthKey]) {
                monthMap[monthKey] = {
                    month_key: monthKey,
                    month: row.month || monthKey,
                    month_order: row.month_order || 0,
                    project: { opened: 0, closed: 0, flow_balance: 0 },
                    company: { opened: 0, closed: 0, flow_balance: 0 },
                };
            }

            monthMap[monthKey].project = {
                opened: row.opened || 0,
                closed: row.closed || 0,
                flow_balance: row.flow_balance || 0,
            };
        });

        companyRows.forEach((row) => {
            const monthKey = row.month_key || `${row.year_no || ""}-${String(row.month_no || "").padStart(2, "0")}`;
            if (!monthMap[monthKey]) {
                monthMap[monthKey] = {
                    month_key: monthKey,
                    month: row.month || monthKey,
                    month_order: row.month_order || 0,
                    project: { opened: 0, closed: 0, flow_balance: 0 },
                    company: { opened: 0, closed: 0, flow_balance: 0 },
                };
            }

            monthMap[monthKey].company = {
                opened: row.opened || 0,
                closed: row.closed || 0,
                flow_balance: row.flow_balance || 0,
            };
        });

        const monthRows = Object.keys(monthMap)
            .map((monthKey) => monthMap[monthKey])
            .filter((row) => {
                return (
                    row.project.opened > 0
                    || row.project.closed > 0
                    || row.company.opened > 0
                    || row.company.closed > 0
                );
            })
            .sort((a, b) => {
                const monthOrderDiff = (a.month_order || 0) - (b.month_order || 0);
                if (monthOrderDiff !== 0) return monthOrderDiff;
                return (a.month_key || "").localeCompare(b.month_key || "");
            });

        if (!monthRows.length) {
            this.$flowTable.html(`<p class="text-muted">${__("No monthly activity for selected project/company.")}</p>`);
            return;
        }

        const projectTitle = frappe.utils.escape_html(projectTitles[selectedProject] || selectedProject || __("Project"));
        const html = [
            '<table class="table table-bordered table-hover">',
            "<thead>",
            "<tr>",
            `<th rowspan="2">${__("Month")}</th>`,
            `<th class="text-center" colspan="3">${projectTitle}</th>`,
            `<th class="text-center" colspan="3">${__("Company")}</th>`,
            "</tr>",
            "<tr>",
            `<th class="text-right">${__("Opened")}</th>`,
            `<th class="text-right">${__("Closed")}</th>`,
            `<th class="text-right">${__("Flow Balance %")}</th>`,
            `<th class="text-right">${__("Opened")}</th>`,
            `<th class="text-right">${__("Closed")}</th>`,
            `<th class="text-right">${__("Flow Balance %")}</th>`,
            "</tr>",
            "</thead>",
            "<tbody>",
        ];

        monthRows.forEach((row) => {
            html.push("<tr>");
            html.push(`<td>${frappe.utils.escape_html(row.month || "")}</td>`);
            html.push(`<td class="text-right">${row.project.opened}</td>`);
            html.push(`<td class="text-right">${row.project.closed}</td>`);
            html.push(`<td class="text-right">${(row.project.flow_balance || 0).toFixed(2)}%</td>`);
            html.push(`<td class="text-right">${row.company.opened}</td>`);
            html.push(`<td class="text-right">${row.company.closed}</td>`);
            html.push(`<td class="text-right">${(row.company.flow_balance || 0).toFixed(2)}%</td>`);
            html.push("</tr>");
        });

        html.push("</tbody>");
        html.push("</table>");

        this.$flowTable.html(html.join(""));
    }

    renderProjectComparisonFlowTable(rows, selectedProjects, projectTitles) {
        const byMonth = {};

        rows.forEach((row) => {
            if (!selectedProjects.includes(row.gitlab_project)) return;

            const monthKey = row.month_key || `${row.year_no || ""}-${String(row.month_no || "").padStart(2, "0")}`;
            if (!byMonth[monthKey]) {
                byMonth[monthKey] = {
                    month_key: monthKey,
                    month: row.month || monthKey,
                    month_order: row.month_order || 0,
                    projects: {},
                };
            }

            byMonth[monthKey].projects[row.gitlab_project] = {
                opened: row.opened || 0,
                closed: row.closed || 0,
                flow_balance: row.flow_balance || 0,
            };
        });

        const monthRows = Object.keys(byMonth)
            .map((monthKey) => byMonth[monthKey])
            .filter((monthData) => {
                return selectedProjects.some((project) => {
                    const data = monthData.projects[project];
                    return data && (data.opened > 0 || data.closed > 0);
                });
            })
            .sort((a, b) => {
                const monthOrderDiff = (a.month_order || 0) - (b.month_order || 0);
                if (monthOrderDiff !== 0) return monthOrderDiff;
                return (a.month_key || "").localeCompare(b.month_key || "");
            });

        if (!monthRows.length) {
            this.$flowTable.html(`<p class="text-muted">${__("No monthly activity for selected project(s).")}</p>`);
            return;
        }

        const html = [
            '<table class="table table-bordered table-hover">',
            "<thead>",
            "<tr>",
            `<th rowspan="2">${__("Month")}</th>`,
        ];

        selectedProjects.forEach((project) => {
            const projectTitle = frappe.utils.escape_html(projectTitles[project] || project || "");
            html.push(`<th class="text-center" colspan="3">${projectTitle}</th>`);
        });

        html.push("</tr>");
        html.push("<tr>");

        selectedProjects.forEach(() => {
            html.push(`<th class="text-right">${__("Opened")}</th>`);
            html.push(`<th class="text-right">${__("Closed")}</th>`);
            html.push(`<th class="text-right">${__("Flow Balance %")}</th>`);
        });

        html.push("</tr>");
        html.push("</thead>");
        html.push("<tbody>");

        monthRows.forEach((monthData) => {
            html.push("<tr>");
            html.push(`<td>${frappe.utils.escape_html(monthData.month || "")}</td>`);

            selectedProjects.forEach((project) => {
                const projectMonthData = monthData.projects[project] || { opened: 0, closed: 0, flow_balance: 0 };
                html.push(`<td class="text-right">${projectMonthData.opened || 0}</td>`);
                html.push(`<td class="text-right">${projectMonthData.closed || 0}</td>`);
                html.push(`<td class="text-right">${(projectMonthData.flow_balance || 0).toFixed(2)}%</td>`);
            });

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
