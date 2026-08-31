// Drill-down (stage 1: popup, stage 2: open filtered list view in new tab).
// Split out of gitlab_issue_dashboard.js to keep that file shorter; loaded via
// the `page_js` hook in hooks.py, concatenated after GitLabIssueDashboard is defined.
Object.assign(GitLabIssueDashboard.prototype, {
    getChartClickIndex(e) {
        const el = e.target && e.target.closest ? e.target.closest("[data-point-index]") : null;
        if (!el) return null;
        const index = parseInt(el.getAttribute("data-point-index"), 10);
        return Number.isNaN(index) ? null : index;
    },

    getFilterContext() {
        const projects = this.normalizeProjectsValue(this.filters.projects.get_value() || []);
        const { from_date: defaultFromDate, to_date: defaultToDate } = this.getDefaultDateRange();
        return {
            projects,
            from_date: this.filters.from_date.get_value() || defaultFromDate,
            to_date: this.filters.to_date.get_value() || defaultToDate,
            issue_scope: this.normalizeIssueScopeValue(this.filters.issue_scope.get_value()),
        };
    },

    getProjectTitle(project) {
        const projectTitles = (this.currentData && this.currentData.project_titles) || {};
        return projectTitles[project] || project;
    },

    getScopeLabel(projects) {
        if (!projects || !projects.length) return __("All Projects");
        if (projects.length === 1) return this.getProjectTitle(projects[0]);
        return __("Selected Projects");
    },

    computeRollingFromDate(months) {
        const d = new Date();
        d.setMonth(d.getMonth() - months);
        return this.formatDate(d);
    },

    computeMonthDateRange(monthKey) {
        const [year, month] = String(monthKey).split("-").map(Number);
        const from = new Date(year, month - 1, 1);
        const to = new Date(year, month, 0);
        return { from_date: this.formatDate(from), to_date: this.formatDate(to) };
    },

    monthKeyToLabel(monthKey) {
        const [year, month] = String(monthKey).split("-").map(Number);
        const d = new Date(year, month - 1, 1);
        return d.toLocaleString(frappe.boot.lang || undefined, { month: "long", year: "numeric" });
    },

    buildListViewUrl(params) {
        const searchParams = new URLSearchParams();

        if (params.projects && params.projects.length) {
            searchParams.set("gitlab_project", JSON.stringify(["in", params.projects]));
        }

        if (params.issue_scope === "parent") {
            searchParams.set("parent_issue", JSON.stringify(["is", "not set"]));
        } else if (params.issue_scope === "child") {
            searchParams.set("parent_issue", JSON.stringify(["is", "set"]));
        }

        if (params.state) {
            searchParams.set("state", params.state);
        }

        if (params.require_touch_time) {
            searchParams.set("total_touch_time", JSON.stringify(["is", "set"]));
        }

        if (params.require_cycle_time) {
            searchParams.set("cycle_time_started_at", JSON.stringify(["is", "set"]));
        }

        if (params.aging_bucket === "0_30") {
            searchParams.set("aging_days", JSON.stringify(["<=", 30]));
        } else if (params.aging_bucket === "31_90") {
            searchParams.set("aging_days", JSON.stringify(["between", [31, 90]]));
        } else if (params.aging_bucket === "gt_90") {
            searchParams.set("aging_days", JSON.stringify([">", 90]));
        }

        if (params.date_field && params.from_date && params.to_date) {
            searchParams.set(params.date_field, JSON.stringify(["between", [params.from_date, params.to_date]]));
        } else if (params.date_field && params.rolling_months) {
            const fromDate = this.computeRollingFromDate(params.rolling_months);
            searchParams.set(params.date_field, JSON.stringify(["between", [fromDate, this.formatDate(new Date())]]));
        }

        const query = searchParams.toString();
        const slug = frappe.router.slug("GitLab Issue");
        return `/app/${slug}${query ? "?" + query : ""}`;
    },

    renderDrilldownBody($body, data, note, showLeadTime, onLoadMore, showTouchTime, showCycleTime) {
        const rows = (data && data.rows) || [];
        const total = (data && data.total) || 0;
        const projectTitles = (data && data.project_titles) || {};

        if (!rows.length) {
            $body.html(`<p class="text-muted">${__("No matching issues found.")}</p>`);
            return;
        }

        const hasMore = rows.length < total;
        const countNote = hasMore
            ? __("Showing {0} of {1} matching issues.", [rows.length, total])
            : __("{0} matching issue(s).", [rows.length]);
        const loadMoreHtml = hasMore
            ? `<div style="margin-top: 8px;"><button type="button" class="btn btn-xs btn-default gid-drilldown-load-more">${__("Load More")}</button></div>`
            : "";
        const noteHtml = note
            ? `<div class="text-muted gid-drilldown-note" style="margin-top: 8px;">${frappe.utils.escape_html(note)}</div>`
            : "";
        const leadTimeHeader = showLeadTime ? `<th class="text-right">${__("Lead Time (days)")}</th>` : "";
        const touchTimeHeader = showTouchTime ? `<th class="text-right">${__("Touch Time (days)")}</th>` : "";
        const cycleTimeHeader = showCycleTime ? `<th class="text-right">${__("Cycle Time (days)")}</th>` : "";
        const summary = (showTouchTime && data && data.touch_time_summary)
            || (showCycleTime && data && data.cycle_time_summary);
        const summaryHtml = summary
            ? `<div class="gid-drilldown-note" style="margin-top: 8px;"><strong>${__("Total")}: ${summary.total_days} ${__("days")} &nbsp;·&nbsp; ${__("Average")}: ${summary.avg_days} ${__("days")}</strong></div>`
            : "";

        const tableRows = rows.map((row) => {
            const project = frappe.utils.escape_html(projectTitles[row.gitlab_project] || row.gitlab_project || "");
            const issueLabel = frappe.utils.escape_html(row.issue_id || row.name || "");
            const link = row.issue_url
                ? `<a href="${frappe.utils.escape_html(row.issue_url)}" target="_blank" rel="noopener">${issueLabel}</a>`
                : issueLabel;
            const created = row.created_at ? frappe.datetime.str_to_user(row.created_at) : "-";
            const closed = row.closed_at ? frappe.datetime.str_to_user(row.closed_at) : "-";
            const leadTimeCell = showLeadTime
                ? `<td class="text-right">${row.lead_time_days === null || row.lead_time_days === undefined ? "-" : row.lead_time_days}</td>`
                : "";
            const touchTimeCell = showTouchTime
                ? `<td class="text-right">${row.touch_time_days === null || row.touch_time_days === undefined ? "-" : row.touch_time_days}</td>`
                : "";
            const cycleTimeCell = showCycleTime
                ? `<td class="text-right">${row.cycle_time_days === null || row.cycle_time_days === undefined ? "-" : row.cycle_time_days}</td>`
                : "";

            return `
                <tr>
                    <td>${link}</td>
                    <td>${project}</td>
                    <td>${frappe.utils.escape_html(row.state || "")}</td>
                    <td>${created}</td>
                    <td>${closed}</td>
                    ${leadTimeCell}
                    ${touchTimeCell}
                    ${cycleTimeCell}
                </tr>
            `;
        }).join("");

        $body.html(`
            <div class="text-muted gid-drilldown-note" style="margin-bottom: 8px;">${countNote}</div>
            <div class="gid-table-wrap" style="max-height: 420px; overflow: auto;">
                <table class="table table-bordered table-hover">
                    <thead>
                        <tr>
                            <th>${__("Issue")}</th>
                            <th>${__("Project")}</th>
                            <th>${__("State")}</th>
                            <th>${__("Created")}</th>
                            <th>${__("Closed")}</th>
                            ${leadTimeHeader}
                            ${touchTimeHeader}
                            ${cycleTimeHeader}
                        </tr>
                    </thead>
                    <tbody>${tableRows}</tbody>
                </table>
            </div>
            ${summaryHtml}
            ${loadMoreHtml}
            ${noteHtml}
        `);

        if (hasMore && typeof onLoadMore === "function") {
            $body.find(".gid-drilldown-load-more").on("click", (e) => {
                const $btn = $(e.currentTarget);
                $btn.prop("disabled", true).text(__("Loading..."));
                onLoadMore();
            });
        }
    },

    openDrilldown({ title, tabs, activeKey }) {
        if (!tabs || !tabs.length) return;

        const state = {
            activeKey: activeKey && tabs.some((t) => t.key === activeKey) ? activeKey : tabs[0].key,
            cache: {},
        };

        const dialog = new frappe.ui.Dialog({
            title,
            size: "extra-large",
            fields: [
                { fieldtype: "HTML", fieldname: "gid_drilldown_tabs" },
                { fieldtype: "HTML", fieldname: "gid_drilldown_body" },
            ],
        });

        const $tabsWrap = dialog.fields_dict.gid_drilldown_tabs.$wrapper;
        const $body = dialog.fields_dict.gid_drilldown_body.$wrapper;

        const updatePrimaryAction = () => {
            const tab = tabs.find((t) => t.key === state.activeKey);
            if (!tab) return;

            dialog.set_primary_action(__("Open in New Tab"), () => {
                window.open(this.buildListViewUrl(tab.params), "_blank");
            });
        };

        const renderTabs = () => {
            if (tabs.length < 2) {
                $tabsWrap.empty();
                return;
            }

            $tabsWrap.html(
                tabs.map((t) => `
                    <button type="button"
                        class="btn btn-xs ${t.key === state.activeKey ? "btn-primary" : "btn-default"} gid-drilldown-tab"
                        data-key="${frappe.utils.escape_html(t.key)}">${frappe.utils.escape_html(t.label)}</button>
                `).join("")
            );

            $tabsWrap.find(".gid-drilldown-tab").on("click", (e) => {
                state.activeKey = $(e.currentTarget).data("key");
                renderTabs();
                updatePrimaryAction();
                loadActive();
            });
        };

        const fetchPage = (tab, startAt) => {
            return frappe.call({
                method: "phamos.gitlab_integration.page.gitlab_issue_dashboard.gitlab_issue_dashboard.get_gitlab_issue_drilldown",
                args: Object.assign({}, tab.params, { start: startAt }),
            }).then((r) => r.message || { rows: [], total: 0, project_titles: {} });
        };

        const loadActive = () => {
            const tab = tabs.find((t) => t.key === state.activeKey);
            if (!tab) return;

            if (state.cache[tab.key]) {
                this.renderDrilldownBody($body, state.cache[tab.key], tab.note, tab.showLeadTime, () => loadMore(tab), tab.showTouchTime, tab.showCycleTime);
                return;
            }

            $body.html(`<div class="text-muted" style="padding: 24px 0;">${__("Loading...")}</div>`);

            fetchPage(tab, 0).then((data) => {
                state.cache[tab.key] = data;
                if (state.activeKey === tab.key) {
                    this.renderDrilldownBody($body, data, tab.note, tab.showLeadTime, () => loadMore(tab), tab.showTouchTime, tab.showCycleTime);
                }
            });
        };

        const loadMore = (tab) => {
            const cached = state.cache[tab.key];
            if (!cached) return;

            fetchPage(tab, cached.rows.length).then((data) => {
                cached.rows = cached.rows.concat(data.rows || []);
                cached.total = data.total;
                cached.project_titles = Object.assign({}, cached.project_titles, data.project_titles);
                if (state.activeKey === tab.key) {
                    this.renderDrilldownBody($body, cached, tab.note, tab.showLeadTime, () => loadMore(tab), tab.showTouchTime, tab.showCycleTime);
                }
            });
        };

        renderTabs();
        updatePrimaryAction();
        dialog.show();
        loadActive();
    },

    openLeadTimeDrilldown(projects, period) {
        const filterCtx = this.getFilterContext();
        const periodLabelMap = {
            filtered: __("Selected Filter Range"),
            last_month: __("Last Month"),
            last_3_months: __("Last 3 Months"),
            last_6_months: __("Last 6 Months"),
            last_12_months: __("Last 12 Months"),
        };
        const rollingMonthsMap = { last_month: 1, last_3_months: 3, last_6_months: 6, last_12_months: 12 };

        const params = {
            projects,
            issue_scope: filterCtx.issue_scope,
            date_field: "closed_at",
            state: "closed",
        };

        if (period === "filtered") {
            params.from_date = filterCtx.from_date;
            params.to_date = filterCtx.to_date;
        } else {
            params.rolling_months = rollingMonthsMap[period];
        }

        this.openDrilldown({
            title: __("Lead Time — {0} ({1})", [this.getScopeLabel(projects), periodLabelMap[period] || period]),
            tabs: [{ key: "closed", label: __("Closed Issues"), params, showLeadTime: true }],
        });
    },

    openTouchTimeDrilldown(projects, period) {
        const filterCtx = this.getFilterContext();
        const periodLabelMap = {
            filtered: __("Selected Filter Range"),
            last_month: __("Last Month"),
            last_3_months: __("Last 3 Months"),
            last_6_months: __("Last 6 Months"),
            last_12_months: __("Last 12 Months"),
        };
        const rollingMonthsMap = { last_month: 1, last_3_months: 3, last_6_months: 6, last_12_months: 12 };

        const params = {
            projects,
            issue_scope: filterCtx.issue_scope,
            date_field: "closed_at",
            state: "closed",
            require_touch_time: true,
        };

        if (period === "filtered") {
            params.from_date = filterCtx.from_date;
            params.to_date = filterCtx.to_date;
        } else {
            params.rolling_months = rollingMonthsMap[period];
        }

        this.openDrilldown({
            title: __("Touch Time — {0} ({1})", [this.getScopeLabel(projects), periodLabelMap[period] || period]),
            tabs: [{
                key: "closed",
                label: __("Closed Issues"),
                params,
                showTouchTime: true,
                note: __("Only issues with a counted timesheet are shown, matching the average above."),
            }],
        });
    },

    openCycleTimeDrilldown(projects, period) {
        const filterCtx = this.getFilterContext();
        const periodLabelMap = {
            filtered: __("Selected Filter Range"),
            last_month: __("Last Month"),
            last_3_months: __("Last 3 Months"),
            last_6_months: __("Last 6 Months"),
            last_12_months: __("Last 12 Months"),
        };
        const rollingMonthsMap = { last_month: 1, last_3_months: 3, last_6_months: 6, last_12_months: 12 };

        const params = {
            projects,
            issue_scope: filterCtx.issue_scope,
            date_field: "closed_at",
            state: "closed",
            require_cycle_time: true,
        };

        if (period === "filtered") {
            params.from_date = filterCtx.from_date;
            params.to_date = filterCtx.to_date;
        } else {
            params.rolling_months = rollingMonthsMap[period];
        }

        this.openDrilldown({
            title: __("Cycle Time — {0} ({1})", [this.getScopeLabel(projects), periodLabelMap[period] || period]),
            tabs: [{
                key: "closed",
                label: __("Closed Issues"),
                params,
                showCycleTime: true,
                note: __("Only issues with a resolved Cycle Time start are shown, matching the average above."),
            }],
        });
    },

    openAgingDrilldown(projects, bucket) {
        const filterCtx = this.getFilterContext();
        const bucketLabelMap = { "0_30": __("0-30 days"), "31_90": __("31-90 days"), gt_90: __(">90 days") };

        const params = {
            projects: projects || [],
            issue_scope: filterCtx.issue_scope,
            date_field: "closed_at",
            from_date: filterCtx.from_date,
            to_date: filterCtx.to_date,
            state: "closed",
        };
        if (bucket) params.aging_bucket = bucket;

        const title = bucket
            ? __("Closed Tickets Aging — {0} ({1})", [this.getScopeLabel(projects), bucketLabelMap[bucket]])
            : __("Closed Tickets — {0}", [this.getScopeLabel(projects)]);

        this.openDrilldown({
            title,
            tabs: [{ key: "closed", label: __("Closed Issues"), params }],
        });
    },

    openFlowTotalsDrilldown(projects, kind) {
        const filterCtx = this.getFilterContext();
        const dateField = kind === "closed" ? "closed_at" : "created_at";
        const params = {
            projects,
            issue_scope: filterCtx.issue_scope,
            date_field: dateField,
            from_date: filterCtx.from_date,
            to_date: filterCtx.to_date,
            state: kind === "closed" ? "closed" : "opened",
        };
        const kindLabel = kind === "closed" ? __("Closed") : __("Opened");

        this.openDrilldown({
            title: __("{0} — {1} Issues", [this.getScopeLabel(projects), kindLabel]),
            tabs: [{ key: kind, label: kindLabel, params }],
        });
    },

    openFlowMonthDrilldown(projects, monthKey, defaultKind) {
        const filterCtx = this.getFilterContext();
        const { from_date, to_date } = this.computeMonthDateRange(monthKey);
        const monthLabel = this.monthKeyToLabel(monthKey);

        const openedParams = {
            projects, issue_scope: filterCtx.issue_scope, date_field: "created_at", from_date, to_date, state: "opened",
        };
        const closedParams = {
            projects, issue_scope: filterCtx.issue_scope, date_field: "closed_at", from_date, to_date, state: "closed",
        };

        this.openDrilldown({
            title: __("{0} — {1}", [this.getScopeLabel(projects), monthLabel]),
            tabs: [
                { key: "opened", label: __("Opened"), params: openedParams },
                { key: "closed", label: __("Closed"), params: closedParams },
            ],
            activeKey: defaultKind,
        });
    },

    handleAgingChartSelect(e) {
        const ctx = this.agingChartContext;
        if (!ctx) return;
        const index = e.index;

        if (ctx.mode === "bucket") {
            const bucket = ctx.bucketOrder[index];
            if (!bucket) return;
            this.openAgingDrilldown(ctx.projects, bucket);
        } else if (ctx.mode === "index_project") {
            const project = ctx.indexProjects[index];
            if (project === undefined) return;
            this.openAgingDrilldown(project ? [project] : [], null);
        }
    },

    handleFlowChartSelect(e) {
        const ctx = this.flowChartContext;
        if (!ctx) return;
        const monthKey = ctx.monthKeys[e.index];
        if (!monthKey) return;
        this.openFlowMonthDrilldown(ctx.projects || [], monthKey);
    },
});
