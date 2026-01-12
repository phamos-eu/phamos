// ============================================================================
// OKR Dashboard - Modular Architecture
// ============================================================================

/**
 * Global configuration object for OKR Dashboard
 * @type {Object}
 */
const OKR_DASHBOARD_CONFIG = {
    CHART_HEIGHT: 300,
    DEFAULT_FILTERS: {
        date_range: '',
        okr_type: '',
        responsible_person: '',
        from_date: '',
        to_date: ''
    },
    PROGRESS_THRESHOLDS: {
        EXCELLENT: 80,
        GOOD: 60,
        FAIR: 40,
        POOR: 20
    },
    OKR_SCORE_THRESHOLDS: {
        EXCELLENT: 0.8,
        GOOD: 0.6,
        FAIR: 0.4
    },
    CHART_COLORS: {
        EXCELLENT: '#27ae60',
        GOOD: '#3498db',
        FAIR: '#f39c12',
        POOR: '#e67e22',
        CRITICAL: '#e74c3c',
        OVERDUE: '#e74c3c',
        DUE_SOON: '#f39c12',
        ON_TIME: '#27ae60'
    }
};

// Global State Management
const DashboardState = {
    data: {},
    filters: { ...OKR_DASHBOARD_CONFIG.DEFAULT_FILTERS },
    pagination: {
        currentPage: 1,
        itemsPerPage: 50,
        totalItems: 0,
        hasMore: true,
        startItem: 1,
        endItem: 50
    },
    
    /**
     * Updates dashboard data with validation
     * @param {Object} newData - The new data to set
     */
    updateData(newData) {
        if (!newData || typeof newData !== 'object') {
            console.warn('Invalid data provided to updateData:', newData);
            return;
        }
        this.data = newData;
    },
    
    updateFilters(newFilters) {
        this.filters = { ...this.filters, ...newFilters };
        // Reset pagination when filters change
        this.pagination.currentPage = 1;
        this.pagination.hasMore = true;
        this.data = {}; // Clear existing data
        this.updatePaginationDisplay();
    },
    
    resetFilters() {
        this.filters = { ...OKR_DASHBOARD_CONFIG.DEFAULT_FILTERS };
        this.pagination.currentPage = 1;
        this.pagination.hasMore = true;
        this.data = {}; // Clear existing data
        this.updatePaginationDisplay();
    },
    
    updatePagination(totalItems) {
        this.pagination.totalItems = totalItems;
        this.pagination.hasMore = this.pagination.currentPage * this.pagination.itemsPerPage < totalItems;
        this.updatePaginationDisplay();
    },
    
    updatePaginationDisplay() {
        const start = (this.pagination.currentPage - 1) * this.pagination.itemsPerPage + 1;
        const end = Math.min(this.pagination.currentPage * this.pagination.itemsPerPage, this.pagination.totalItems);
        this.pagination.startItem = start;
        this.pagination.endItem = end;
        
        // Update to show actual loaded items count
        if (this.data.objectives && this.data.objectives.length > 0) {
            this.pagination.endItem = Math.min(start + this.data.objectives.length - 1, this.pagination.totalItems);
        }
    },
    
    nextPage() {
        if (this.pagination.hasMore) {
            this.pagination.currentPage++;
            return true;
        }
        return false;
    },
    
    resetPagination() {
        this.pagination.currentPage = 1;
        this.pagination.hasMore = true;
        this.updatePaginationDisplay();
    },
    
    setItemsPerPage(itemsPerPage) {
        this.pagination.itemsPerPage = itemsPerPage;
        this.pagination.currentPage = 1;
        this.pagination.hasMore = true;
        this.updatePaginationDisplay();
    }
};

// ============================================================================
// UTILITY FUNCTIONS
// ============================================================================

const DashboardUtils = {
    // Date formatting utilities
    formatDate(dateString, type = 'target') {
        if (!dateString) {
            return type === 'checkin' ? 'Never' : 'Not Set';
        }
        
        try {
            const date = new Date(dateString);
            
            if (type === 'checkin') {
                const now = new Date();
                const diffTime = Math.abs(now - date);
                const diffDays = Math.ceil(diffTime / (1000 * 60 * 60 * 24));
                
                if (diffDays === 0) return 'Today';
                if (diffDays === 1) return 'Yesterday';
                if (diffDays <= 7) return `${diffDays} days ago`;
            }
            
            return date.toLocaleDateString('en-US', { 
                year: 'numeric', 
                month: 'short', 
                day: 'numeric' 
            });
        } catch (e) {
            return 'Invalid Date';
        }
    },

    // OKR Score formatting
    formatOkrScore(score) {
        if (score === null || score === undefined || score === '') return 'N/A';
        return Math.round(score * 10) / 10;
    },

    // Progress classification
    getProgressClass(progress) {
        if (progress >= 100) return 'completed';
        if (progress > 0) return 'in-progress';
        return '';
    },

    // OKR Score classification
    getOkrScoreClass(score) {
        if (score === null || score === undefined || score === '') return 'no-score';
        if (score >= OKR_DASHBOARD_CONFIG.OKR_SCORE_THRESHOLDS.EXCELLENT) return 'excellent';
        if (score >= OKR_DASHBOARD_CONFIG.OKR_SCORE_THRESHOLDS.GOOD) return 'good';
        if (score >= OKR_DASHBOARD_CONFIG.OKR_SCORE_THRESHOLDS.FAIR) return 'fair';
        return 'poor';
    },

    // OKR Type utilities
    getOkrTypeClass(type) {
        const typeMap = {
            'Company': 'company',
            'Team': 'team',
            'Individual': 'individual'
        };
        return typeMap[type] || 'kr';
    },

    getOkrTypeLabel(type) {
        const labelMap = {
            'Company': 'Company',
            'Team': 'Team',
            'Individual': 'Individual'
        };
        return labelMap[type] || 'KR';
    },


};

// ============================================================================
// FILTER MANAGEMENT
// ============================================================================

const FilterManager = {
    filterTimeout: null,
    
    init() {
        this.bindFilterEvents();
        this.setupResponsiblePersonField();
        this.setupOkrLinkField();
    },
    
    cleanup() {
        // Clear any pending timeouts
        if (this.filterTimeout) {
            clearTimeout(this.filterTimeout);
            this.filterTimeout = null;
        }
        
        // Remove event listeners
        $(window).off('scroll.dashboard');
        $('.dashboard-sidebar').off('change');
    },

    bindFilterEvents() {
        $('#date-filter').on('change', this.handleDateFilterChange.bind(this));
        $('#okr-type-filter').on('change', this.handleFilterChange.bind(this));
        $('#responsible-filter').on('change', this.handleResponsibleFilterChange.bind(this));
        $('#from-date, #to-date').on('change', this.handleFilterChange.bind(this));
    },

    handleDateFilterChange() {
        const dateFilter = $('#date-filter').val();
        const customDateGroup = $('.custom-date-group');
        
        if (dateFilter === 'custom') {
            customDateGroup.show();
        } else {
            customDateGroup.hide();
        }
        
        this.handleFilterChange();
    },

    handleFilterChange() {
        const filters = this.getCurrentFilters();
        DashboardState.updateFilters(filters);
        DataManager.loadDashboardData();
    },

    handleResponsibleFilterChange() {
        // Debounce filter changes to prevent excessive API calls
        clearTimeout(this.filterTimeout);
        this.filterTimeout = setTimeout(() => {
            const filters = this.getCurrentFilters();
            
            // Clear existing data when filters change
            DashboardState.data = {};
            DashboardState.pagination.currentPage = 1;
            DashboardState.pagination.hasMore = true;
            
            DashboardState.updateFilters(filters);
            DataManager.loadDashboardData();
        }, 300);
    },

    getCurrentFilters() {
        // Get responsible person value directly from link field
        let responsiblePerson = '';
        if (this.responsibleField) {
            responsiblePerson = this.responsibleField.get_value() || '';
        }
        let selectedOkr = '';
        if (this.okrLinkField) {
            selectedOkr = this.okrLinkField.get_value() || '';
        }
        
        return {
            date_range: $('#date-filter').val() || '',
            okr_type: $('#okr-type-filter').val() || '',
            responsible_person: responsiblePerson,
            okr: selectedOkr,
            from_date: $('#from-date').val() || '',
            to_date: $('#to-date').val() || ''
        };
    },

    clearFilters() {
        $('#date-filter').val('');
        $('#okr-type-filter').val('');
        if (this.responsibleField) {
            this.responsibleField.set_value('');
        }
        if (this.okrLinkField) {
            this.okrLinkField.set_value('');
        }
        $('.custom-date-group').hide();
        $('#from-date').val('');
        $('#to-date').val('');
        
        // Reset dashboard state and clear existing data
        DashboardState.resetFilters();
        DashboardState.data = {};
        DashboardState.pagination.currentPage = 1;
        DashboardState.pagination.hasMore = true;
        
        // Force reload of dashboard data to show all records
        DataManager.loadDashboardData();
    },



    setupResponsiblePersonField() {
        // Remove the existing input and hidden field
        $('#responsible-filter, #responsible-filter-hidden').remove();
        
        // Create a new container for the link field
        const container = $('<div class="link-field-container"></div>');
        $('.link-field-wrapper').append(container);
        
        // Create Frappe standard link field using the correct pattern
        const linkField = frappe.ui.form.make_control({
            parent: container,
            df: {
                fieldname: 'responsible_person',
                fieldtype: 'Link',
                options: 'User',
                placeholder: 'Search user...',
                label: ''
            },
            render_input: true
        });
        
        // Refresh the control to ensure proper initialization
        linkField.refresh();
        
        // Add proper event listener with value change detection
        linkField.df.onchange = () => {
            const value = linkField.get_value();
            console.log('Link field onchange triggered with value:', value);
            
            // Only trigger if value has actually changed
            if (value !== this.lastResponsiblePersonValue) {
                this.lastResponsiblePersonValue = value;
                this.handleResponsibleFilterChange();
            }
        };
        
        this.responsibleField = linkField;
        this.lastResponsiblePersonValue = '';
    },

    setupOkrLinkField() {
        const container = $('<div class="link-field-container"></div>');
        $('.okr-link-wrapper').append(container);
        const okrLinkField = frappe.ui.form.make_control({
            parent: container,
            df: {
                fieldname: 'okr',
                fieldtype: 'Link',
                options: 'OKR',
                placeholder: 'Search OKR...',
                label: ''
            },
            render_input: true
        });
        okrLinkField.refresh();
        okrLinkField.df.onchange = () => {
            const value = okrLinkField.get_value();
            if (value !== this.lastOkrValue) {
                this.lastOkrValue = value;
                this.handleResponsibleFilterChange();
            }
        };
        this.okrLinkField = okrLinkField;
        this.lastOkrValue = '';
    }

};

// ============================================================================
// DATA MANAGEMENT
// ============================================================================

const DataManager = {
    isLoading: false,
    
    showLoading() {
        this.isLoading = true;
        $('.dashboard-main').addClass('loading');
        $('.loading-spinner').show();
    },
    
    hideLoading() {
        this.isLoading = false;
        $('.dashboard-main').removeClass('loading');
        $('.loading-spinner').hide();
    },
    
    loadDashboardData() {
        if (this.isLoading) return; // Prevent multiple simultaneous requests
        
        this.showLoading();
        frappe.call({
            method: 'phamos.okr_addon.page.okr_dashboard.okr_dashboard.get_dashboard_data',
            args: {
                filters: JSON.stringify(DashboardState.filters),
                page: DashboardState.pagination.currentPage,
                items_per_page: DashboardState.pagination.itemsPerPage
            },
            callback: (r) => {
                console.log('Dashboard data loaded:', r.message);
                this.hideLoading();
                if (r.message) {
                    // Always replace data to maintain hierarchy structure
                    DashboardState.updateData(r.message);
                    DashboardState.updatePagination(r.message.total_items || 0);
                    DashboardRenderer.updateDashboard();
                } else {
                    console.error('Failed to load dashboard data');
                    frappe.show_alert('Failed to load dashboard data', 3);
                }
            },
            error: (r) => {
                this.hideLoading();
                console.error('Error loading dashboard data:', r);
                frappe.show_alert('Error loading dashboard data', 3);
            }
        });
    },

    loadMoreData() {
        if (DashboardState.pagination.hasMore) {
            DashboardState.pagination.currentPage++;
            DataManager.loadDashboardData();
        }
    },

    changeItemsPerPage(itemsPerPage) {
        DashboardState.setItemsPerPage(itemsPerPage);
        this.loadDashboardData();
    }
};

// ============================================================================
// CHART MANAGEMENT
// ============================================================================

const ChartManager = {
    updateAllCharts() {
        this.updateProgressChart();
        this.updateTimelineChart();
        this.updateRiskChart();
        this.updateTrendsChart();
    },

    /**
     * Updates the progress distribution chart
     */
    updateProgressChart() {
        const performanceMetrics = DashboardState.data.performance_metrics || {};
        const progressDist = performanceMetrics.progress_distribution || {};
        
        const chartData = [
            { name: 'Excellent', y: progressDist.excellent || 0, color: OKR_DASHBOARD_CONFIG.CHART_COLORS.EXCELLENT },
            { name: 'Good', y: progressDist.good || 0, color: OKR_DASHBOARD_CONFIG.CHART_COLORS.GOOD },
            { name: 'Fair', y: progressDist.fair || 0, color: OKR_DASHBOARD_CONFIG.CHART_COLORS.FAIR },
            { name: 'Poor', y: progressDist.poor || 0, color: OKR_DASHBOARD_CONFIG.CHART_COLORS.POOR },
            { name: 'Critical', y: progressDist.critical || 0, color: OKR_DASHBOARD_CONFIG.CHART_COLORS.CRITICAL }
        ];
        
        const config = {
            chart: {
                type: 'pie',
                height: OKR_DASHBOARD_CONFIG.CHART_HEIGHT
            },
            title: { text: 'Progress Distribution' },
            series: [{
                name: 'OKRs',
                data: chartData
            }],
            plotOptions: {
                pie: {
                    allowPointSelect: true,
                    cursor: 'pointer',
                    dataLabels: {
                        enabled: true,
                        format: '<b>{point.name}</b>: {point.percentage:.1f} %'
                    }
                }
            }
        };
        
        Highcharts.chart('progress-chart', config);
    },

    updateTimelineChart() {
        const timelineData = DashboardState.data.timeline_data || {};
        const stats = DashboardState.data.stats || {};
        
        const chartData = [
            { name: 'Overdue', y: stats.timeline?.overdue || 0, color: OKR_DASHBOARD_CONFIG.CHART_COLORS.OVERDUE },
            { name: 'Due Soon', y: stats.timeline?.due_soon || 0, color: OKR_DASHBOARD_CONFIG.CHART_COLORS.DUE_SOON },
            { name: 'On Time', y: stats.timeline?.on_time || 0, color: OKR_DASHBOARD_CONFIG.CHART_COLORS.ON_TIME }
        ];
        
        const config = {
            chart: {
                type: 'column',
                height: OKR_DASHBOARD_CONFIG.CHART_HEIGHT
            },
            title: { text: 'Timeline Analysis' },
            xAxis: {
                categories: ['Overdue', 'Due Soon', 'On Time']
            },
            yAxis: {
                title: { text: 'Number of OKRs' }
            },
            series: [{
                name: 'OKRs',
                data: chartData.map(item => item.y)
            }],
            plotOptions: {
                column: {
                    colorByPoint: true,
                    colors: [OKR_DASHBOARD_CONFIG.CHART_COLORS.OVERDUE, 
                             OKR_DASHBOARD_CONFIG.CHART_COLORS.DUE_SOON, 
                             OKR_DASHBOARD_CONFIG.CHART_COLORS.ON_TIME]
                }
            }
        };
        
        Highcharts.chart('timeline-chart', config);
    },

    updateRiskChart() {
        const riskAnalysis = DashboardState.data.risk_analysis || {};
        const riskPercentages = riskAnalysis.risk_percentages || {};
        
        const chartData = [
            { name: 'Overdue', y: riskPercentages.overdue || 0 },
            { name: 'Low Confidence', y: riskPercentages.low_confidence || 0 },
            { name: 'Low Progress', y: riskPercentages.low_progress || 0 },
            { name: 'No Measurables', y: riskPercentages.no_measurables || 0 },
            { name: 'No Check-ins', y: riskPercentages.no_check_ins || 0 }
        ];
        
        const config = {
            chart: {
                type: 'bar',
                height: OKR_DASHBOARD_CONFIG.CHART_HEIGHT
            },
            title: { text: 'Risk Analysis' },
            xAxis: {
                categories: ['Overdue', 'Low Confidence', 'Low Progress', 'No Measurables', 'No Check-ins']
            },
            yAxis: {
                title: { text: 'Risk Percentage' }
            },
            series: [{
                name: 'Risk Percentage',
                data: chartData.map(item => item.y),
                color: OKR_DASHBOARD_CONFIG.CHART_COLORS.CRITICAL
            }],
            plotOptions: {
                bar: {
                    dataLabels: {
                        enabled: true,
                        format: '{y}%'
                    }
                }
            }
        };
        
        Highcharts.chart('risk-chart', config);
    },

    updateTrendsChart() {
        const timelineData = DashboardState.data.timeline_data || {};
        
        const labels = timelineData.labels || ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun'];
        const progressData = timelineData.progress || [0, 0, 0, 0, 0, 0];
        const confidenceData = timelineData.confidence || [0, 0, 0, 0, 0, 0];
        
        const config = {
            chart: {
                type: 'line',
                height: OKR_DASHBOARD_CONFIG.CHART_HEIGHT
            },
            title: { text: 'Performance Trends' },
            xAxis: { categories: labels },
            yAxis: { title: { text: 'Percentage' } },
            series: [{
                name: 'Progress',
                data: progressData,
                color: OKR_DASHBOARD_CONFIG.CHART_COLORS.GOOD
            }, {
                name: 'Confidence',
                data: confidenceData,
                color: OKR_DASHBOARD_CONFIG.CHART_COLORS.EXCELLENT
            }],
            plotOptions: {
                line: {
                    marker: { enabled: true }
                }
            }
        };
        
        Highcharts.chart('trends-chart', config);
    }
};

// ============================================================================
// HIERARCHY MANAGEMENT
// ============================================================================

const HierarchyManager = {
    buildHierarchy(okrs) {
        const hierarchy = [];
        const lookup = {};
        
        // Create lookup table
        okrs.forEach(obj => {
            lookup[obj.name] = { ...obj, children: [] };
        });
        
        // Build hierarchy (supports both KRA and OKR parents)
        okrs.forEach(obj => {
            let parentFound = false;
            
            // Check for KRA parent first
            if (obj.parent_kra && lookup[obj.parent_kra]) {
                lookup[obj.parent_kra].children.push(lookup[obj.name]);
                parentFound = true;
            }
            // Check for OKR parent
            else if (obj.parent_okr && lookup[obj.parent_okr]) {
                lookup[obj.parent_okr].children.push(lookup[obj.name]);
                parentFound = true;
            }
            
            // If no parent found, add to root hierarchy
            if (!parentFound) {
                hierarchy.push(lookup[obj.name]);
            }
        });
        
        return hierarchy;
    },

    createHierarchyRow(item, level) {
        const hasChildren = item.children && item.children.length > 0;
        
        const row = `
            <tr class="hierarchy-row level-${level}" data-level="${level}" data-id="${item.name}" data-parent="${item.parent_kra || item.parent_okr || ''}" data-parent-type="${item.parent_type || ''}">
                <td>
                    <div style="display: flex; align-items: center;">
                        <span class="hierarchy-indicator expanded" onclick="HierarchyManager.toggleHierarchy(this)" style="display: ${hasChildren ? 'inline-block' : 'none'}">
                            <i class="fas fa-chevron-down"></i>
                        </span>
                        ${item.name}
                    </div>
                </td>
                <td>
                    <div style="display: flex; align-items: center;">
                        ${item.title}
                    </div>
                </td>
                <td>
                    <span class="okr-type-badge ${DashboardUtils.getOkrTypeClass(item.okr_type)}">${DashboardUtils.getOkrTypeLabel(item.okr_type)}</span>
                </td>
                <td>
                    <div class="progress-wrapper">
                        <div class="progress">
                            <div class="progress-bar ${DashboardUtils.getProgressClass(item.progress)}" style="width: ${item.progress || 0}%"></div>
                        </div>
                        <small>${Math.round(item.progress || 0)}%</small>
                    </div>
                </td>
                <td>
                    <span class="okr-score ${DashboardUtils.getOkrScoreClass(item.okr_score)}">${DashboardUtils.formatOkrScore(item.okr_score)}</span>
                </td>
                <td>${DashboardUtils.formatDate(item.target_date, 'target')}</td>
                <td>${DashboardUtils.formatDate(item.last_check_in, 'checkin')}</td>
                <td>
                    <span class="group-badge">${item.responsible_person || 'Unassigned'}</span>
                </td>
            </tr>
        `;
        
        let html = row;
        
        // Add children
        if (hasChildren) {
            item.children.forEach(child => {
                html += this.createHierarchyRow(child, level + 1);
            });
        }
        
        return html;
    },

    toggleHierarchy(element) {
        const indicator = $(element);
        const row = indicator.closest('tr');
        const id = row.data('id');
        const hasChildren = $(`.hierarchy-row[data-parent="${id}"]`).length > 0;
        
        if (!hasChildren) return;
        
        if (indicator.hasClass('expanded')) {
            // Collapse
            indicator.removeClass('expanded').addClass('collapsed');
            indicator.find('i').removeClass('fas fa-chevron-down').addClass('fas fa-chevron-right');
            $(`.hierarchy-row[data-parent="${id}"]`).hide();
        } else {
            // Expand
            indicator.removeClass('collapsed').addClass('expanded');
            indicator.find('i').removeClass('fas fa-chevron-right').addClass('fas fa-chevron-down');
            $(`.hierarchy-row[data-parent="${id}"]`).show();
        }
    },

    expandAll() {
        $('.hierarchy-indicator').each(function() {
            const indicator = $(this);
            const id = indicator.closest('tr').data('id');
            const hasChildren = $(`.hierarchy-row[data-parent="${id}"]`).length > 0;
            
            if (hasChildren) {
                indicator.removeClass('collapsed').addClass('expanded');
                indicator.find('i').removeClass('fas fa-chevron-right').addClass('fas fa-chevron-down');
                $(`.hierarchy-row[data-parent="${id}"]`).show();
            }
        });
    },

    collapseAll() {
        $('.hierarchy-indicator').each(function() {
            const indicator = $(this);
            indicator.removeClass('expanded').addClass('collapsed');
            indicator.find('i').removeClass('fas fa-chevron-down').addClass('fas fa-chevron-right');
        });
        $('.hierarchy-row[data-level="1"], .hierarchy-row[data-level="2"], .hierarchy-row[data-level="3"]').hide();
    }
};

// ============================================================================
// DASHBOARD RENDERER
// ============================================================================

const DashboardRenderer = {
    updateDashboard() {
        this.updateMetrics();
        ChartManager.updateAllCharts();
        this.renderHierarchicalTable();
    },

    updateMetrics() {
        const stats = DashboardState.data.stats || {};
        
        $('#total-objectives').text(stats.total || 0);
        $('#completed-objectives').text(stats.completed || 0);
        $('#in-progress-objectives').text(stats.in_progress || 0);
        $('#at-risk-objectives').text(stats.at_risk || 0);
        $('#overall-progress').text((stats.overall_progress || 0) + '%');
        $('#health-score').text(stats.avg_health_score || 0);
    },

    renderHierarchicalTable() {
        const okrs = DashboardState.data.objectives || [];
        
        const tbody = $('#hierarchy-tbody');
        tbody.empty();
        
        const hierarchy = HierarchyManager.buildHierarchy(okrs);
        
        hierarchy.forEach((item, index) => {
            const row = HierarchyManager.createHierarchyRow(item, 0);
            tbody.append(row);
        });

        // Add footer if it doesn't exist
        if ($('.table-footer').length === 0) {
            const footerHTML = `
                <div class="table-footer">
                    <div class="footer-left">
                        <span class="data-display">Showing <strong>${DashboardState.pagination.startItem}-${DashboardState.pagination.endItem}</strong> of <strong>${DashboardState.pagination.totalItems}</strong></span>
                        <div class="rows-per-load">
                            <label style="margin-bottom: 0rem !important;">Rows per load:</label>
                            <select class="rows-selector" onchange="DataManager.changeItemsPerPage(this.value)">
                                <option value="25" ${DashboardState.pagination.itemsPerPage === 25 ? 'selected' : ''}>25</option>
                                <option value="50" ${DashboardState.pagination.itemsPerPage === 50 ? 'selected' : ''}>50</option>
                                <option value="100" ${DashboardState.pagination.itemsPerPage === 100 ? 'selected' : ''}>100</option>
                                <option value="200" ${DashboardState.pagination.itemsPerPage === 200 ? 'selected' : ''}>200</option>
                            </select>
                        </div>
                    </div>
                    <div class="footer-right">
                        ${DashboardState.pagination.hasMore ? `
                            <button class="btn btn-primary load-more-btn" onclick="DataManager.loadMoreData()">
                                Load More
                            </button>
                        ` : ''}
                    </div>
                </div>
            `;
            $('.table-responsive').after(footerHTML);
        } else {
            // Update existing footer
            const actualEndItem = DashboardState.data.objectives ? 
                Math.min(DashboardState.pagination.startItem + DashboardState.data.objectives.length - 1, DashboardState.pagination.totalItems) : 
                DashboardState.pagination.endItem;
            
            $('.data-display').html(`Showing <strong>${DashboardState.pagination.startItem}-${actualEndItem}</strong> of <strong>${DashboardState.pagination.totalItems}</strong>`);
            $('.rows-selector').val(DashboardState.pagination.itemsPerPage);
            
            if (DashboardState.pagination.hasMore) {
                if ($('.load-more-btn').length === 0) {
                    $('.footer-right').prepend('<button class="btn btn-primary load-more-btn" onclick="DataManager.loadMoreData()">Load More</button>');
                }
            } else {
                $('.load-more-btn').remove();
            }
        }
    }
};

// ============================================================================
// UI CONTROLS
// ============================================================================

const UIControls = {
    toggleSidebar() {
        const sidebar = $('.dashboard-sidebar');
        const mainContent = $('.dashboard-main');
        const toggleBtn = $('.sidebar-toggle i');
        
        sidebar.toggleClass('collapsed');
        mainContent.toggleClass('sidebar-collapsed');
        
        if (sidebar.hasClass('collapsed')) {
            toggleBtn.removeClass('fa-navicon').addClass('fa-chevron-right');
        } else {
            toggleBtn.removeClass('fa-chevron-right').addClass('fa-navicon');
        }
    },

    toggleChart(chartId) {
        const chartContainer = $(`#${chartId}`).closest('.chart-container');
        chartContainer.toggleClass('expanded');
        
        // Trigger chart resize
        const chart = Highcharts.charts.find(c => c.renderTo.id === chartId);
        if (chart) {
            setTimeout(() => chart.reflow(), 100);
        }
    },

    addScrollListener() {
        let lastScrollTop = 0;
        
        $(window).on('scroll', function() {
            const sidebar = $('.dashboard-sidebar');
            const scrollTop = $(window).scrollTop();
            const windowHeight = $(window).height();
            const scrollPercentage = (scrollTop / windowHeight) * 100;
            const isScrollingUp = scrollTop < lastScrollTop;
            
            if (scrollPercentage > 10) {
                sidebar.addClass('scrolled');
                if (isScrollingUp) {
                    sidebar.css('top', 'unset'); // When scrolling up, use unset
                } else {
                    sidebar.css('top', '70px'); // When scrolling down, shift up
                }
            } else {
                sidebar.removeClass('scrolled');
                sidebar.css('top', 'unset'); // Reset to original position
            }
            
            lastScrollTop = scrollTop;
        });
    }
};

// ============================================================================
// MAIN DASHBOARD INITIALIZATION
// ============================================================================

frappe.pages['okr_dashboard'].on_page_load = function (wrapper) {
    const page = frappe.ui.make_app_page({
        parent: wrapper,
        title: 'OKR Dashboard',
        single_column: true
    });

    DashboardInitializer.init(page);
};

// Cleanup when page is unloaded
frappe.pages['okr_dashboard'].on_page_unload = function () {
    FilterManager.cleanup();
    DataManager.hideLoading();
};

const DashboardInitializer = {
    init(page) {
        // Inject CSS only for OKR dashboard page
        this.addToggleButton();
        this.renderPageLayout(page);
    },

    addToggleButton() {
        const toggleButton = `
            <button class="sidebar-toggle" onclick="UIControls.toggleSidebar()">
                <i class="fa fa-navicon"></i>
            </button>
        `;
        $('.page-head-content').prepend(toggleButton);
    },

    renderPageLayout(page) {
        this.loadTemplate(page);
    },

    loadTemplate(page) {
        // Frappe way: Use the proper Frappe template loading method
        frappe.call({
            method: 'phamos.okr_addon.page.okr_dashboard.okr_dashboard.get_dashboard_template',
            callback: (r) => {
                if (r.message) {
                    // Use the template content directly
                    $(page.body).html(r.message);
                    // Initialize components after template is loaded
                    this.initializeComponents();
                    this.loadInitialData();
                } else {
                    console.error('Failed to load dashboard template');
                    frappe.show_alert('Failed to load dashboard template', 5);
                    // Initialize components anyway to show error state
                    this.initializeComponents();
                }
            },
            error: (r) => {
                console.error('Error loading template via Frappe method:', r);
                frappe.show_alert('Error loading dashboard template. Please refresh the page.', 5);
                // Initialize components anyway to show error state
                this.initializeComponents();
            }
        });
    },
    
    initializeComponents() {
        FilterManager.init();
        UIControls.addScrollListener();
    },

    loadInitialData() {
        DataManager.loadDashboardData();
    }
};
