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

        root.append(frappe.render_template("gitlab_issue_dashboard_layout"));

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
        this.$touchTimeKpis = root.find("#touch-time-kpis");
        this.$cycleTimeKpis = root.find("#cycle-time-kpis");
        this.$agingKpis = root.find("#aging-kpis");
        this.$agingChart = root.find("#aging-chart");
        this.$flowKpis = root.find("#flow-kpis");
        this.$flowChart = root.find("#flow-chart");
        this.$flowTable = root.find("#flow-table");

        this.agingChartContext = null;
        this.flowChartContext = null;
        this.$agingChart[0].addEventListener("click", (e) => {
            const index = this.getChartClickIndex(e);
            if (index !== null) this.handleAgingChartSelect({ index });
        });
        this.$flowChart[0].addEventListener("click", (e) => {
            const index = this.getChartClickIndex(e);
            if (index !== null) this.handleFlowChartSelect({ index });
        });

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
            this.renderTouchTimeKpis();
            this.renderCycleTimeKpis();
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

        const buildRow = (label, data, projectId) => {
            const rolling = (data && data.rolling) || {};
            const labelHtml = label
                ? `<div class="gid-lead-row-label">${frappe.utils.escape_html(label)}</div>`
                : "";
            const projAttr = projectId ? frappe.utils.escape_html(projectId) : "";
            const kpi = (period, title, value, extraClass) => `
                <div class="gid-kpi ${extraClass} gid-clickable" data-drill="lead_time" data-project="${projAttr}" data-period="${period}">
                    <small>${title}</small><strong>${formatDays(value)}</strong>
                </div>
            `;
            return `
                <div class="gid-lead-row">
                    ${labelHtml}
                    <div class="gid-kpi-row gid-kpi-row-lead">
                        ${kpi("filtered", __("Selected Filter Avg"), data ? data.filtered : null, "gid-kpi-lead-main")}
                        ${kpi("last_month", __("Last Month"), rolling.last_month, "gid-kpi-lead")}
                        ${kpi("last_3_months", __("Last 3 Months"), rolling.last_3_months, "gid-kpi-lead")}
                        ${kpi("last_6_months", __("Last 6 Months"), rolling.last_6_months, "gid-kpi-lead")}
                        ${kpi("last_12_months", __("Last 12 Months"), rolling.last_12_months, "gid-kpi-lead")}
                    </div>
                </div>
            `;
        };

        let html = "";

        if (mode === "single" && leadTime.company) {
            const projectTitle = projectTitles[leadTime.project] || leadTime.project || __("Project");
            html += buildRow(projectTitle, leadTime, leadTime.project);
            html += buildRow(__("Company"), leadTime.company, null);
        } else if (mode === "project_compare" && (leadTime.project_lead_times || []).length) {
            leadTime.project_lead_times.forEach((row) => {
                const title = projectTitles[row.project] || row.project || __("Project");
                html += buildRow(title, row, row.project);
            });
        } else {
            html += buildRow(null, leadTime, null);
        }

        this.$leadTimeKpis.html(html);
        this.$leadTimeKpis.off("click", ".gid-kpi").on("click", ".gid-kpi", (e) => {
            const $el = $(e.currentTarget);
            const project = $el.attr("data-project");
            const period = $el.attr("data-period");
            this.openLeadTimeDrilldown(project ? [project] : [], period);
        });
    }

    renderTouchTimeKpis() {
        const touchTime = (this.currentData && this.currentData.touch_time) || {};
        const leadTime = (this.currentData && this.currentData.lead_time) || {};
        const mode = touchTime.mode || "combined";
        const projectTitles = (this.currentData && this.currentData.project_titles) || {};

        const formatDays = (value) => {
            if (value === null || value === undefined) return __("N/A");
            return __("{0} days", [value]);
        };

        const formatPct = (touchValue, leadValue) => {
            if (touchValue === null || touchValue === undefined) return null;
            if (!leadValue) return null;
            return Math.round((touchValue / leadValue) * 1000) / 10;
        };

        const buildRow = (label, data, leadData, projectId) => {
            const rolling = (data && data.rolling) || {};
            const leadRolling = (leadData && leadData.rolling) || {};
            const labelHtml = label
                ? `<div class="gid-lead-row-label">${frappe.utils.escape_html(label)}</div>`
                : "";
            const projAttr = projectId ? frappe.utils.escape_html(projectId) : "";
            const kpi = (period, title, value, leadValue, extraClass) => {
                const pct = formatPct(value, leadValue);
                const pctHtml = pct !== null
                    ? `<div class="gid-kpi-sub">${__("{0}% of Lead Time", [pct])}</div>`
                    : "";
                return `
                    <div class="gid-kpi ${extraClass} gid-clickable" data-drill="touch_time" data-project="${projAttr}" data-period="${period}">
                        <small>${title}</small><strong>${formatDays(value)}</strong>
                        ${pctHtml}
                    </div>
                `;
            };
            return `
                <div class="gid-lead-row">
                    ${labelHtml}
                    <div class="gid-kpi-row gid-kpi-row-lead">
                        ${kpi("filtered", __("Selected Filter Avg"), data ? data.filtered : null, leadData ? leadData.filtered : null, "gid-kpi-touch-main")}
                        ${kpi("last_month", __("Last Month"), rolling.last_month, leadRolling.last_month, "gid-kpi-touch")}
                        ${kpi("last_3_months", __("Last 3 Months"), rolling.last_3_months, leadRolling.last_3_months, "gid-kpi-touch")}
                        ${kpi("last_6_months", __("Last 6 Months"), rolling.last_6_months, leadRolling.last_6_months, "gid-kpi-touch")}
                        ${kpi("last_12_months", __("Last 12 Months"), rolling.last_12_months, leadRolling.last_12_months, "gid-kpi-touch")}
                    </div>
                </div>
            `;
        };

        let html = "";

        if (mode === "single" && touchTime.company) {
            const projectTitle = projectTitles[touchTime.project] || touchTime.project || __("Project");
            html += buildRow(projectTitle, touchTime, leadTime, touchTime.project);
            html += buildRow(__("Company"), touchTime.company, leadTime.company, null);
        } else if (mode === "project_compare" && (touchTime.project_touch_times || []).length) {
            touchTime.project_touch_times.forEach((row) => {
                const title = projectTitles[row.project] || row.project || __("Project");
                const leadRow = (leadTime.project_lead_times || []).find((t) => t.project === row.project);
                html += buildRow(title, row, leadRow, row.project);
            });
        } else {
            html += buildRow(null, touchTime, leadTime, null);
        }

        this.$touchTimeKpis.html(html);
        this.$touchTimeKpis.off("click", ".gid-kpi").on("click", ".gid-kpi", (e) => {
            const $el = $(e.currentTarget);
            const project = $el.attr("data-project");
            const period = $el.attr("data-period");
            this.openTouchTimeDrilldown(project ? [project] : [], period);
        });
    }

    renderCycleTimeKpis() {
        const cycleTime = (this.currentData && this.currentData.cycle_time) || {};
        const leadTime = (this.currentData && this.currentData.lead_time) || {};
        const mode = cycleTime.mode || "combined";
        const projectTitles = (this.currentData && this.currentData.project_titles) || {};

        const formatDays = (value) => {
            if (value === null || value === undefined) return __("N/A");
            return __("{0} days", [value]);
        };

        const formatPct = (cycleValue, leadValue) => {
            if (cycleValue === null || cycleValue === undefined) return null;
            if (!leadValue) return null;
            return Math.round((cycleValue / leadValue) * 1000) / 10;
        };

        const buildRow = (label, data, leadData, projectId) => {
            const rolling = (data && data.rolling) || {};
            const leadRolling = (leadData && leadData.rolling) || {};
            const labelHtml = label
                ? `<div class="gid-lead-row-label">${frappe.utils.escape_html(label)}</div>`
                : "";
            const projAttr = projectId ? frappe.utils.escape_html(projectId) : "";
            const kpi = (period, title, value, leadValue, extraClass) => {
                const pct = formatPct(value, leadValue);
                const pctHtml = pct !== null
                    ? `<div class="gid-kpi-sub">${__("{0}% of Lead Time", [pct])}</div>`
                    : "";
                return `
                    <div class="gid-kpi ${extraClass} gid-clickable" data-drill="cycle_time" data-project="${projAttr}" data-period="${period}">
                        <small>${title}</small><strong>${formatDays(value)}</strong>
                        ${pctHtml}
                    </div>
                `;
            };
            return `
                <div class="gid-lead-row">
                    ${labelHtml}
                    <div class="gid-kpi-row gid-kpi-row-lead">
                        ${kpi("filtered", __("Selected Filter Avg"), data ? data.filtered : null, leadData ? leadData.filtered : null, "gid-kpi-cycle-main")}
                        ${kpi("last_month", __("Last Month"), rolling.last_month, leadRolling.last_month, "gid-kpi-cycle")}
                        ${kpi("last_3_months", __("Last 3 Months"), rolling.last_3_months, leadRolling.last_3_months, "gid-kpi-cycle")}
                        ${kpi("last_6_months", __("Last 6 Months"), rolling.last_6_months, leadRolling.last_6_months, "gid-kpi-cycle")}
                        ${kpi("last_12_months", __("Last 12 Months"), rolling.last_12_months, leadRolling.last_12_months, "gid-kpi-cycle")}
                    </div>
                </div>
            `;
        };

        let html = "";

        if (mode === "single" && cycleTime.company) {
            const projectTitle = projectTitles[cycleTime.project] || cycleTime.project || __("Project");
            html += buildRow(projectTitle, cycleTime, leadTime, cycleTime.project);
            html += buildRow(__("Company"), cycleTime.company, leadTime.company, null);
        } else if (mode === "project_compare" && (cycleTime.project_cycle_times || []).length) {
            cycleTime.project_cycle_times.forEach((row) => {
                const title = projectTitles[row.project] || row.project || __("Project");
                const leadRow = (leadTime.project_lead_times || []).find((t) => t.project === row.project);
                html += buildRow(title, row, leadRow, row.project);
            });
        } else {
            html += buildRow(null, cycleTime, leadTime, null);
        }

        this.$cycleTimeKpis.html(html);
        this.$cycleTimeKpis.off("click", ".gid-kpi").on("click", ".gid-kpi", (e) => {
            const $el = $(e.currentTarget);
            const project = $el.attr("data-project");
            const period = $el.attr("data-period");
            this.openCycleTimeDrilldown(project ? [project] : [], period);
        });
    }

    renderAgingChart() {
        this.$agingChart.empty();
        this.applyThemeClass();
        this.agingChartContext = null;

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
            <div class="gid-kpi gid-kpi-green gid-clickable" data-bucket="0_30"><small>${__("0-30 days")}</small><strong>${values[0]}</strong></div>
            <div class="gid-kpi gid-kpi-amber gid-clickable" data-bucket="31_90"><small>${__("31-90 days")}</small><strong>${values[1]}</strong></div>
            <div class="gid-kpi gid-kpi-red gid-clickable" data-bucket="gt_90"><small>${__(">90 days")}</small><strong>${values[2]}</strong></div>
        `);
        this.$agingKpis.off("click", ".gid-kpi").on("click", ".gid-kpi", (e) => {
            const bucket = $(e.currentTarget).attr("data-bucket");
            this.openAgingDrilldown(selectedProjects, bucket);
        });

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
                isNavigable: 1,
                colors: agingColors,
            });
            this.agingChartContext = { mode: "index_project", indexProjects: [selectedProject, null] };
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
                isNavigable: 1,
                colors: agingColors,
            });
            this.agingChartContext = { mode: "index_project", indexProjects: projectBuckets.map((row) => row.project) };
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
            isNavigable: 1,
            colors: agingColors,
        });
        this.agingChartContext = { mode: "bucket", bucketOrder: ["0_30", "31_90", "gt_90"], projects: selectedProjects };
    }

    renderFlowChart() {
        this.$flowChart.empty();
        this.applyThemeClass();
        this.flowChartContext = null;

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
        const openNowTotal = (this.currentData && this.currentData.open_now_total !== undefined)
            ? this.currentData.open_now_total
            : totals.opened;

        this.$flowKpis.html(`
            <div class="gid-kpi gid-kpi-opened gid-clickable" data-flow-kind="opened"><small>${__("Opened Total")}</small><strong>${openNowTotal}</strong></div>
            <div class="gid-kpi gid-kpi-closed gid-clickable" data-flow-kind="closed"><small>${__("Closed Total")}</small><strong>${totals.closed}</strong></div>
        `);
        this.$flowKpis.off("click", ".gid-kpi").on("click", ".gid-kpi", (e) => {
            const kind = $(e.currentTarget).attr("data-flow-kind");
            this.openFlowTotalsDrilldown(selectedProjects, kind);
        });

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
                isNavigable: 1,
                colors: ["#1976d2", "#43a047", "#ef6c00", "#8e24aa"],
            });
            this.flowChartContext = { monthKeys: sortedMonthKeys, projects: [selectedProject] };
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
                isNavigable: 1,
                colors: chartColors,
            });
            this.flowChartContext = { monthKeys: sortedMonthKeys, projects: selectedProjects };
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
            isNavigable: 1,
            colors: flowColors,
        });
        this.flowChartContext = { monthKeys: sortedMonthKeys, projects: selectedProjects };
    }

    renderFlowTable() {
        const rows = (this.currentData && this.currentData.monthly_flow) || [];
        const projectTitles = (this.currentData && this.currentData.project_titles) || {};

        this.$flowTable.off("click", "[data-drill='flow-cell']").on("click", "[data-drill='flow-cell']", (e) => {
            const $el = $(e.currentTarget);
            const kind = $el.attr("data-kind");
            const project = $el.attr("data-project");
            const monthKey = $el.attr("data-month-key");
            if (!monthKey) return;
            this.openFlowMonthDrilldown(project ? [project] : [], monthKey, kind);
        });

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
            html.push(`<td class="text-right gid-clickable" data-drill="flow-cell" data-kind="opened" data-project="${frappe.utils.escape_html(row.gitlab_project || "")}" data-month-key="${row.month_key}">${row.opened || 0}</td>`);
            html.push(`<td class="text-right gid-clickable" data-drill="flow-cell" data-kind="closed" data-project="${frappe.utils.escape_html(row.gitlab_project || "")}" data-month-key="${row.month_key}">${row.closed || 0}</td>`);
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
            html.push(`<td class="text-right gid-clickable" data-drill="flow-cell" data-kind="opened" data-project="${frappe.utils.escape_html(selectedProject || "")}" data-month-key="${row.month_key}">${row.project.opened}</td>`);
            html.push(`<td class="text-right gid-clickable" data-drill="flow-cell" data-kind="closed" data-project="${frappe.utils.escape_html(selectedProject || "")}" data-month-key="${row.month_key}">${row.project.closed}</td>`);
            html.push(`<td class="text-right">${(row.project.flow_balance || 0).toFixed(2)}%</td>`);
            html.push(`<td class="text-right gid-clickable" data-drill="flow-cell" data-kind="opened" data-project="" data-month-key="${row.month_key}">${row.company.opened}</td>`);
            html.push(`<td class="text-right gid-clickable" data-drill="flow-cell" data-kind="closed" data-project="" data-month-key="${row.month_key}">${row.company.closed}</td>`);
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
                html.push(`<td class="text-right gid-clickable" data-drill="flow-cell" data-kind="opened" data-project="${frappe.utils.escape_html(project || "")}" data-month-key="${monthData.month_key}">${projectMonthData.opened || 0}</td>`);
                html.push(`<td class="text-right gid-clickable" data-drill="flow-cell" data-kind="closed" data-project="${frappe.utils.escape_html(project || "")}" data-month-key="${monthData.month_key}">${projectMonthData.closed || 0}</td>`);
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
            html.push(`<td class="text-right gid-clickable" data-drill="flow-cell" data-kind="opened" data-project="" data-month-key="${row.month_key}">${row.opened || 0}</td>`);
            html.push(`<td class="text-right gid-clickable" data-drill="flow-cell" data-kind="closed" data-project="" data-month-key="${row.month_key}">${row.closed || 0}</td>`);
            html.push(`<td class="text-right">${(row.flow_balance || 0).toFixed(2)}%</td>`);
            html.push("</tr>");
        });

        html.push("</tbody>");
        html.push("</table>");

        this.$flowTable.html(html.join(""));
    }

    // Drill-down methods (getChartClickIndex, getFilterContext, openDrilldown, etc.)
    // live in gitlab_issue_dashboard_drilldown.js, attached to this prototype via
    // the `page_js` hook in hooks.py.

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
