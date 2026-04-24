let pageSize = 20;
let totalCount = 0;
let loadedCount = 0;
let currentSortBy = null;
let currentSortOrder = null;
let currentChartView = 'week'; // 'week' or 'month'
let cachedTimesheetData = null; // Cache the timesheet data
const sortFieldMap = {
    1: "timesheet",
    2: "start_date",
    3: "employee_name",
    4: "activity_type",
    5: "billing_status",
    6: "total_hours",
    7: "billable_hours",
    8: "related_issue",
    9: "comment"
};

frappe.ready(() => {

  // Check if user is Guest
  if (frappe.session.user === "Guest") {
    frappe.msgprint("Please log in to access this page.");
    setTimeout(() => {
      window.location.href = "/login";
    }, 1500);
    return; // Stop further execution
  }

  // Initialize chart view from localStorage or default to 'week'
  currentChartView = localStorage.getItem('timesheetChartView') || 'week';
  updateChartViewButtons();

  //set default date range
  // set_default_month_range();
  load_projects();
  attach_filter_events();
  reset_and_load();

  // Toggle buttons for chart view
  $('#weekViewBtn').on('click', function() {
    if (currentChartView !== 'week') {
      currentChartView = 'week';
      localStorage.setItem('timesheetChartView', 'week');
      updateChartViewButtons();
      if (cachedTimesheetData) {
        processDataForGraph(cachedTimesheetData);
      }
    }
  });

  $('#monthViewBtn').on('click', function() {
    if (currentChartView !== 'month') {
      currentChartView = 'month';
      localStorage.setItem('timesheetChartView', 'month');
      updateChartViewButtons();
      if (cachedTimesheetData) {
        processDataForGraph(cachedTimesheetData);
      }
    }
  });

  $('#load_more').on('click', () => {
    load_timesheets();
  });

  $('.page-limit').on('click', function () {
    $('.page-limit').removeClass('active');
    $(this).addClass('active');
    pageSize = parseInt($(this).data('limit'));
    reset_and_load();
  });

  $('#download_all').on('click', function (e) {
    e.preventDefault();
    download_all_csv();
  });
  
  $('#download_selected').on('click', function (e) {
    e.preventDefault();
    download_visible_csv();
  });

  $(document).on('input', '.column-filter', function () {
    apply_column_filters();
  });
  
  $('#select_all').on('change', function () {
    const checked = $(this).is(':checked');
    $('#timesheet_table tbody input[type="checkbox"]').prop('checked', checked);
  });

  //set end date to last day of month
$('#from_date').on('change', function () {
  const startDateStr = $(this).val();
  if (!startDateStr) return;

  const startDate = new Date(startDateStr);
  const year = startDate.getFullYear();
  const month = startDate.getMonth();

  const lastDay = new Date(year, month + 1, 0);

  const yyyy = lastDay.getFullYear();
  const mm = String(lastDay.getMonth() + 1).padStart(2, '0');
  const dd = String(lastDay.getDate()).padStart(2, '0');

  $('#to_date')
      .val(`${yyyy}-${mm}-${dd}`)
      .trigger('change');
});

  
  //reset filters
  $('#clear_filters').on('click', function () {
    $('#from_date').val('');
    $('#to_date').val('');
    $('#project_filter').val('');
    // reset_and_load();
    // load_graph_data(); /// load graph data//
    reset_and_load();
  });

  $(document).on('click', function (event) {
    const $dropdown = $('#downloadDropdown');
    const $menu = $('.dropdown-menu');
  
    // If the click is outside the dropdown button and the menu
    if (!$dropdown.is(event.target) && $dropdown.has(event.target).length === 0 &&
        !$menu.is(event.target) && $menu.has(event.target).length === 0) {
      $menu.removeClass('show');
    }
  });
  
});

function reset_and_load() {
  totalCount = 0;
  loadedCount = 0;

  // Clear table rows except #no_data_row
  $('#timesheet_body').children('tr:not(#no_data_row)').remove();

  $('#no_data_row').hide();
  $('#load_more').show();

  update_summary_cards();

  load_timesheets();
  load_graph_data(); /////////added to load graph
}


function attach_filter_events() {
  ['#to_date', '#project_filter'].forEach(selector => {
    $(selector).on('change', reset_and_load);
  });
}

function load_projects() {
  frappe.call({
    method: "phamos.api.get_projects_for_logged_in_customer", // adjust path
    callback: function (r) {
      if (r.message && r.message.length) {
        const options = r.message.map(p =>
          `<option value="${p.name}">${p.project_name || p.name}</option>`
        );
        $('#project_filter').html('<option value="">All Projects</option>' + options.join(''));
      }
    }
  });
}

function load_timesheets() {
  const from_date = $('#from_date').val();
  const to_date = $('#to_date').val();
  const project = $('#project_filter').val();
  const offset = loadedCount;

  $('#load_more').prop('disabled', true).text('Loading...');

  frappe.call({
    method: "phamos.api.get_timesheets",
    args: { from_date, to_date, project, offset, limit: pageSize, sort_by: currentSortBy, sort_order: currentSortOrder },
    callback: function (r) {
      const data = r.message.timesheets || [];
      totalCount = r.message.total || 0;

      const $tbody = $('#timesheet_body');
      const $noData = $('#no_data_row');

      if (data.length === 0 && loadedCount === 0) {
        $noData.show();
        $('#load_more').hide();
        update_footer();
        return;
      }

      $noData.hide();

      data.forEach(row => {
        let btnText = "Give Feedback";
        let btnColor = "#5198e3"; // default blue
        let btnFontSize = "10px"

        
        if (Number(row.custom_rating) > 0) {
            btnText = "Under Review";
          btnColor = "#ffc107";
          btnFontSize = "10px"
        }

        const relatedIssues = row.related_issue || '';
        const escapedText = escapeHtml(relatedIssues);
        const isLong = relatedIssues.length > 180;

        $tbody.append(`
          <tr>
            <td><input type="checkbox" class="row-select" /></td>
            <td>${row.name}</td>
            <td>${frappe.datetime.str_to_user(row.start_date)}</td>
            <td>${row.employee_name}</td>
            <td>${row.activity_type}</td>
            <td>${row.custom_billing_status || ''}</td>
            <td>${format_hours(row.total_hours)}</td>
            <td>${format_hours(row.total_billable_hours)}</td>
            <td>
              <div 
                class="related-issue ${isLong ? 'long-text' : 'short-text'}"
                title="${escapedText}">
                ${escapedText || '-'}
              </div>
            </td>
            <td>
              <button 
                class="btn btn-sm comment-btn"
                style="background-color: ${btnColor}; color: white; font-size: ${btnFontSize};"
                data-name="${row.name}" 
                data-comment="${row.customer_comment || ''}">
                ${btnText}
              </button>
            </td>
          </tr>
        `);

      });

      loadedCount += data.length;
      apply_column_filters();
      update_footer();

      if (loadedCount >= totalCount || data.length < pageSize) {
        $('#load_more').hide();
      } else {
        $('#load_more').prop('disabled', false).text('Load More');
      }
    }
  });
}

function apply_column_filters() {
  const filters = {};
  $('.column-filter').each(function () {
    const value = ($(this).val() || '').trim().toLowerCase();
    const index = $(this).data('column-index');
    if (value) {
      filters[index] = value;
    }
  });

  const activeColumns = Object.keys(filters);
  let visibleCount = 0;

  $('#timesheet_body tr').each(function () {
    if (this.id === 'no_data_row') {
      return;
    }

    let visible = true;
    if (activeColumns.length) {
      const $cells = $(this).find('td');
      for (let i = 0; i < activeColumns.length; i++) {
        const colIndex = parseInt(activeColumns[i], 10);
        const filterValue = filters[colIndex];
        const cellText = ($cells.eq(colIndex).text() || '').trim().toLowerCase();
        if (!cellText.includes(filterValue)) {
          visible = false;
          break;
        }
      }
    }

    $(this).toggle(visible);
    if (visible) {
      visibleCount++;
    }
  });

  if (loadedCount > 0) {
    $('#no_data_row').toggle(visibleCount === 0);
  }
}

let currentTsName = null; // store which timesheet is being edited

// When user clicks the "Add/Edit Comment" button
$(document).on('click', '.comment-btn', function () {
  currentTsName = $(this).data('name');
  const currentComment = $(this).data('comment') || '';
  
  $('#commentInput').val(currentComment);
  $('#commentModal').modal('show');
});

// When user clicks Save in the modal
let selectedRating = 0;

// Handle click on stars
$(document).on('click', '#starRating .star', function () {
  selectedRating = parseInt($(this).data('value'));
  $('#starRating .star').each(function (index) {
    $(this).html(index < selectedRating ? '&#9733;' : '&#9734;');
  });
  $('#ratingError').hide(); // hide error after selection
});

// Intercept Save button
$('#saveComment').on('click', function (e) {
  e.preventDefault();

  const comment = $('#commentInput').val().trim();

  // 🟥 Check if rating is selected
  if (selectedRating === 0) {
    $('#ratingError').show();
    return;
  }

  // 🟩 Proceed if rating is selected
  if (!currentTsName) return;

  frappe.call({
    method: "phamos.api.update_customer_comment",
    args: {
      ts_name: currentTsName,
      comment: comment,
      custom_rating: selectedRating
    },
    callback: function (r) {
      if (!r.exc) {
        frappe.show_alert({ message: r.message.message, indicator: "green" });

        const btn = $(`.comment-btn[data-name="${currentTsName}"]`);
        btn.text("Under Review")
          .css("background-color", "#ffc107")
          .data('comment', comment)
          .data('rating', selectedRating);

        $('#commentModal').modal('hide');
        reset_and_load();
      } else {
        frappe.show_alert({ message: "Failed to send request", indicator: "red" });
      }
    }
  });
});



document.addEventListener('DOMContentLoaded', function() {
  const stars = document.querySelectorAll('#starRating .star');
  let selectedRating = 0;

  stars.forEach(star => {
    // Handle hover
    star.addEventListener('mouseover', () => {
      stars.forEach(s => s.classList.remove('hovered'));
      const value = parseInt(star.getAttribute('data-value'));
      stars.forEach((s, i) => {
        if (i < value) s.classList.add('hovered');
      });
    });

    // Remove hover when leaving
    star.addEventListener('mouseleave', () => {
      stars.forEach(s => s.classList.remove('hovered'));
    });

    // Handle click (select rating)
    star.addEventListener('click', () => {
      selectedRating = parseInt(star.getAttribute('data-value'));
      stars.forEach((s, i) => {
        if (i < selectedRating) s.classList.add('selected');
        else s.classList.remove('selected');
      });
      console.log("Selected rating:", selectedRating);
    });
  });
});


function update_footer() {
  $('#pagination_info').text(`Showing ${loadedCount} of ${totalCount}`);
  const percent = totalCount === 0 ? 0 : (loadedCount / totalCount) * 100;
  $('#pagination_progress').css('width', `${percent}%`);
}

function download_selected_as_csv() {
  const rows = [];
  $('#timesheet_table tbody tr').each(function () {
    const checkbox = $(this).find('input[type="checkbox"]');
    if (checkbox.is(':checked')) {
      const cols = $(this).find('td').map((_, td) => $(td).text().trim()).get().slice(1);
      rows.push(cols);
    }
  });

  if (!rows.length) {
    alert("Please select rows to download.");
    return;
  }

  const headers = ['Employee', 'Employee Name', 'Activity Type', 'Start Date', 'End Date', 'Total Hours', 'Billable Hours'];
  const csv = [headers.join(",")].concat(rows.map(r => r.join(","))).join("\n");

  const blob = new Blob([csv], { type: 'text/csv' });
  const link = document.createElement('a');
  link.href = URL.createObjectURL(blob);
  link.download = 'timesheets.csv';
  link.click();
}

function download_visible_csv() {
  const rows = [];
  $('#timesheet_table tbody tr').each(function () {
    const checkbox = $(this).find('input[type="checkbox"]');
    if (checkbox.is(':checked')) {
      const cols = $(this).find('td').map((_, td) => $(td).text().trim()).get().slice(1);
      rows.push(cols);
    }
  });

  if (!rows.length) {
    alert("Please select rows to download.");
    return;
  }

  const headers = ['Timesheet', 'Employee ID', 'Employee Name', 'Activity Type', 'Start Date', 'End Date', 'Billing Status', 'Total Hours', 'Billable Hours'];
  const csv = [headers.join(",")].concat(rows.map(r => r.join(","))).join("\n");

  const blob = new Blob([csv], { type: 'text/csv' });
  const link = document.createElement('a');
  link.href = URL.createObjectURL(blob);
  link.download = 'timesheets_filtered.csv';
  link.click();
}

function download_all_csv() {
  const from_date = $('#from_date').val();
  const to_date = $('#to_date').val();
  const project = $('#project_filter').val();

  frappe.call({
    method: "phamos.api.get_timesheets",
    args: {
      from_date,
      to_date,
      project,
      offset: 0,
      limit: 10000 // set safe high limit
    },
    callback: function (r) {
      const data = r.message.timesheets || [];

      const rows = data.map(row => [
        row.name,
        row.timesheet_status || '',
        row.employee || '',
        row.employee_name || '',
        row.activity_type || '',
        row.start_date,
        row.end_date,
        row.custom_billing_status || '',
        row.total_hours,
        row.total_billable_hours
      ]);

      const headers = ['Timesheet', 'Employee ID', 'Employee Name', 'Activity Type', 'Start Date', 'End Date', 'Billing Status', 'Total Hours', 'Billable Hours'];
      const csv = [headers.join(",")].concat(rows.map(r => r.join(","))).join("\n");

      const blob = new Blob([csv], { type: 'text/csv' });
      const link = document.createElement('a');
      link.href = URL.createObjectURL(blob);
      link.download = 'timesheets_all.csv';
      link.click();
    }
  });
}

function set_default_month_range() {
  const today = new Date();
  const year = today.getFullYear();
  const month = today.getMonth();

  // First day of current month
  const firstDay = new Date(year, month, 1);

  // Last day of current month
  const lastDay = new Date(year, month + 1, 0);

  // Format as yyyy-mm-dd
  const format = (date) => {
    const yyyy = date.getFullYear();
    const mm = String(date.getMonth() + 1).padStart(2, '0');
    const dd = String(date.getDate()).padStart(2, '0');
    return `${yyyy}-${mm}-${dd}`;
  };

  $('#from_date').val(format(firstDay));
  $('#to_date').val(format(lastDay));
}

function format_hours(decimal_hours) {
  const totalMinutes = Math.round(parseFloat(decimal_hours || 0) * 60);
  const hours = Math.floor(totalMinutes / 60);
  const minutes = totalMinutes % 60;
  return `${hours} hr ${minutes} min`;
}

function formatShortRelative(dateStr) {
  const input = new Date(dateStr);
  const now = new Date();

  let years = now.getFullYear() - input.getFullYear();
  let months = now.getMonth() - input.getMonth();
  let days = now.getDate() - input.getDate();

  if (days < 0) {
    months -= 1;
    days += new Date(now.getFullYear(), now.getMonth(), 0).getDate();
  }

  if (months < 0) {
    years -= 1;
    months += 12;
  }

  if (years > 0) return `${years} year${years > 1 ? 's' : ''} ago`;
  if (months > 0) return `${months} month${months > 1 ? 's' : ''} ago`;
  if (days > 0) return `${days} day${days > 1 ? 's' : ''} ago`;

  return "Today";
}

function truncateText(text = '', limit = 80) {
  const str = String(text);
  if (str.length <= limit) {
    return str;
  }
  return `${str.slice(0, limit).trim()}…`;
}

function escapeHtml(text = '') {
  return String(text)
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
    .replace(/'/g, '&#39;');
}

// Update chart view button states
function updateChartViewButtons() {
  if (currentChartView === 'week') {
    $('#weekViewBtn').addClass('active').removeClass('btn-outline-primary').addClass('btn-primary');
    $('#monthViewBtn').removeClass('active btn-primary').addClass('btn-outline-primary');
  } else {
    $('#monthViewBtn').addClass('active').removeClass('btn-outline-primary').addClass('btn-primary');
    $('#weekViewBtn').removeClass('active btn-primary').addClass('btn-outline-primary');
  }
}

function update_summary_cards() {
  const from_date = $('#from_date').val();
  const to_date = $('#to_date').val();
  const project = $('#project_filter').val();

  frappe.call({
    method: "phamos.api.get_timesheet_totals",
    args: { from_date, to_date, project },
    callback: function (r) {
      const total = r.message || {};
      $('#total_working').text(format_hours(total.total_hours));
      $('#total_billable').text(format_hours(total.billable_hours));
    }
  });
}

// Helper function to generate all weeks or months between two dates
function generateCompletePeriods(minDate, maxDate, viewType) {
    const periods = [];
    const current = new Date(minDate);
    
    if (viewType === 'week') {
        // Align to Monday of the start week
        const day = current.getDay();
        const diff = current.getDate() - day + (day === 0 ? -6 : 1);
        current.setDate(diff);
        
        // Generate all Mondays between min and max
        while (current <= maxDate) {
            periods.push(current.toISOString().split('T')[0]);
            current.setDate(current.getDate() + 7); // Next Monday
        }
    } else {
        // Monthly view - align to first of month
        current.setDate(1);
        
        // Generate all months between min and max
        while (current <= maxDate) {
            const year = current.getFullYear();
            const month = String(current.getMonth() + 1).padStart(2, '0');
            periods.push(`${year}-${month}`);
            current.setMonth(current.getMonth() + 1);
        }
    }
    
    return periods;
}

//////////////////////////process your timesheets data////////////////////
function processDataForGraph(timesheets) {
    // Cache the data for later use when toggling
    cachedTimesheetData = timesheets;
    
    if (!timesheets || timesheets.length === 0) {
        // No data to display
        Highcharts.chart('timesheet-graph-container', {
            chart: { type: 'area' },
            title: { text: 'Billable vs Non-Billable by Project' },
            xAxis: { categories: [], title: { text: currentChartView === 'week' ? 'Week' : 'Month' } },
            yAxis: { min: 0, title: { text: 'Hours' } },
            series: []
        });
        return;
    }
    
    const projectData = {};
    let minDate = null;
    let maxDate = null;

    // First pass: collect data and find date range
    timesheets.forEach(row => {
        const date = new Date(row.start_date);
        
        if (!minDate || date < minDate) minDate = new Date(date);
        if (!maxDate || date > maxDate) maxDate = new Date(date);
        
        let periodKey;

        if (currentChartView === 'week') {
            // Weekly aggregation
            const day = date.getDay();
            const diff = date.getDate() - day + (day === 0 ? -6 : 1);
            const monday = new Date(date.setDate(diff));
            periodKey = monday.toISOString().split('T')[0];
        } else {
            // Monthly aggregation
            const year = date.getFullYear();
            const month = String(date.getMonth() + 1).padStart(2, '0');
            periodKey = `${year}-${month}`;
        }

        const projectKey = row.project_label; // use label instead of project_name

        if (!projectData[projectKey]) {
            projectData[projectKey] = {};
        }
        if (!projectData[projectKey][periodKey]) {
            projectData[projectKey][periodKey] = { total: 0, billable: 0 };
        }

        projectData[projectKey][periodKey].total += parseFloat(row.total_hours || 0);
        projectData[projectKey][periodKey].billable += parseFloat(row.total_billable_hours || 0);
    });

    // Generate complete list of periods (weeks or months) between min and max dates
    const sortedCategories = generateCompletePeriods(minDate, maxDate, currentChartView);
    const series = [];
    const colorPairs = [
        ['#3399ff', '#99ccff'], // Blue pair
        ['#28a745', '#90ee90'], // Green pair
        ['#ff9933', '#ffcc99'], // Orange pair
        ['#800080', '#d1b3ff'], // Purple pair
        ['#cc0000', '#ff6666']  // Red pair
    ];

    let colorIndex = 0;
    Object.keys(projectData).forEach(projectName => {
        const billableData = [];
        const nonBillableData = [];

        sortedCategories.forEach(period => {
            const data = projectData[projectName][period] || { total: 0, billable: 0 };
            billableData.push(data.billable);
            nonBillableData.push(data.total - data.billable);
        });

        const colors = colorPairs[colorIndex % colorPairs.length];
        series.push({
            name: `${projectName} - Non-Billable`,
            data: nonBillableData,
            color: colors[1],
            stack: projectName
        });
        series.push({
            name: `${projectName} - Billable`,
            data: billableData,
            color: colors[0],
            stack: projectName
        });

        colorIndex++;
    });

    // Format categories for display
    const displayCategories = sortedCategories.map(period => {
        if (currentChartView === 'week') {
            // Show week range: "Sep 15-21" instead of just "2025-09-15"
            const weekStart = new Date(period);
            const weekEnd = new Date(weekStart);
            weekEnd.setDate(weekStart.getDate() + 6);
            
            const monthNames = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 
                                'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'];
            const startMonth = monthNames[weekStart.getMonth()];
            const endMonth = monthNames[weekEnd.getMonth()];
            const startDay = weekStart.getDate();
            const endDay = weekEnd.getDate();
            
            // Check if week spans two months
            if (startMonth === endMonth) {
                return `${startMonth} ${startDay}-${endDay}`;
            } else {
                return `${startMonth} ${startDay}-${endMonth} ${endDay}`;
            }
        } else {
            // Format as "MMM YYYY" for months
            const [year, month] = period.split('-');
            const monthNames = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 
                                'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'];
            return `${monthNames[parseInt(month) - 1]} ${year}`;
        }
    });

    Highcharts.chart('timesheet-graph-container', {
        chart: { type: 'area' },
        title: { text: 'Billable vs Non-Billable by Project' },
        xAxis: { 
            categories: displayCategories, 
            title: { text: currentChartView === 'week' ? 'Week' : 'Month' },
            labels: {
                rotation: currentChartView === 'week' ? -45 : 0,
                style: {
                    fontSize: '11px'
                }
            }
        },
        yAxis: { min: 0, title: { text: 'Hours' } },
        tooltip: {
            shared: true,
            useHTML: true,
            formatter: function () {
                const pointIndex = this.points[0].point.index;
                const period = sortedCategories[pointIndex];
                const displayLabel = displayCategories[pointIndex];
                
                let tooltipHTML = `<div style="padding: 5px;">`;
                
                // Header with week/month info
                if (currentChartView === 'week') {
                    tooltipHTML += `<div style="font-weight: bold; margin-bottom: 5px; font-size: 13px;">${displayLabel}</div>`;
                    tooltipHTML += `<div style="color: #666; font-size: 11px; margin-bottom: 8px;">Week starting: ${period}</div>`;
                } else {
                    tooltipHTML += `<div style="font-weight: bold; margin-bottom: 8px; font-size: 13px;">${displayLabel}</div>`;
                }
                
                // Calculate total hours for this period
                let totalHours = 0;
                this.points.forEach(point => {
                    totalHours += point.y;
                });
                
                // Show breakdown by project and type
                this.points.forEach(point => {
                    if (point.y > 0) {
                        tooltipHTML += `<div style="margin: 3px 0;">
                            <span style="color:${point.color}; font-size: 16px;">●</span> 
                            <span style="font-size: 12px;">${point.series.name}: <strong>${point.y.toFixed(2)} hrs</strong></span>
                        </div>`;
                    }
                });
                
                // Show total
                if (totalHours > 0) {
                    tooltipHTML += `<div style="margin-top: 8px; padding-top: 5px; border-top: 1px solid #ddd; font-weight: bold;">
                        Total: ${totalHours.toFixed(2)} hrs
                    </div>`;
                }
                
                tooltipHTML += `</div>`;
                return tooltipHTML;
            }
        },
        plotOptions: {
            area: { stacking: 'normal', marker: { enabled: false } }
        },
        series
    });
}
/////////////////////////function to fetch all timesheets and trigger the graph/////////////////////
function loadAndRenderGraph() {
  const from_date = $('#from_date').val();
  const to_date = $('#to_date').val();
  const project = $('#project_filter').val();

  frappe.call({
    method: "phamos.api.get_timesheets",
    args: {
      from_date,
      to_date,
      project,
      offset: 0,
      limit: 10000  // high limit to get all data
    },
    callback: function (r) {
      if (r.message && r.message.timesheets) {
        processDataForGraph(r.message.timesheets);
      }
    }
  });
}
/////////////////////////////
function load_graph_data() {
  const from_date = $('#from_date').val();
  const to_date = $('#to_date').val();
  const project = $('#project_filter').val();

  frappe.call({
    method: "phamos.api.get_graph_data",
    args: { from_date, to_date, project },
    callback: function (r) {
      if (r.message) {
        // loadAndRenderGraph(r.message);
        processDataForGraph(r.message.timesheets);

      }
    }
  });
}

/////////////////////////////////////
// loadAndRenderGraph();

// Handle "Give Feedback" button click dynamically
$(document).on('click', '.comment-btn', function () {
  const tsName = $(this).data('name');
  currentTsName = tsName;

  const comment = $(this).data('comment');
  const discount = $(this).data('discount');
  const rating = $(this).data('rating');
  const statusText = $(this).text().trim();

  $('#commentInput').val(comment);
  $('#discountSelect').val(discount);

  // Reset stars
  $('#starRating .star').removeClass('selected');
  for (let i = 0; i < rating; i++) {
    $('#starRating .star').eq(i).addClass('selected');
  }

  // Disable editing if "Under Review"
  const isLocked = statusText === "Under Review";
  $('#commentInput').prop('disabled', isLocked);
  $('#starRating .star').css('pointer-events', isLocked ? 'none' : 'auto');
  $('#saveComment').prop('disabled', isLocked);

  $('#commentModal').modal('show');
});

/* Sorting Handler  */
document.addEventListener("click", function (event) {
    const icon = event.target.closest(".sort-icon");
    const menuItem = event.target.closest(".menu-item");

    if (icon) {
        event.stopPropagation();

        const th = icon.closest("th");
        const menu = th.querySelector(".th-menu");

        window.currentSortColumn = Array.from(th.parentNode.children).indexOf(th);

        document.querySelectorAll(".th-menu").forEach(m => {
            if (m !== menu) m.style.display = "none";
        });

        menu.style.display = menu.style.display === "block" ? "none" : "block";
        return;
    }

    if (menuItem) {
        const action = menuItem.dataset.action;

        document.querySelectorAll(".th-menu").forEach(m => m.style.display = "none");

        currentSortBy = sortFieldMap[window.currentSortColumn] || null;

        if (action === "asc") {
            currentSortOrder = "asc";
        }
        else if (action === "desc") {
            currentSortOrder = "desc";
        }
        else if (action === "reset") {
            currentSortBy = null;
            currentSortOrder = null;
        }

        reset_and_load();
        return;
    }

    document.querySelectorAll(".th-menu").forEach(menu => {
        menu.style.display = "none";
    });
});


// ========================================
// Sales Orders Tab Functionality
// ========================================

let salesOrderDataLoaded = false;
let salesOrderData = null;
let soCurrentPage = 1;
let soPageSize = 20;
let allSalesOrders = [];
let originalSalesOrders = [];

// Listen for Sales Orders tab activation
document.getElementById('sales-orders-tab').addEventListener('shown.bs.tab', function (event) {
  if (!salesOrderDataLoaded) {
    loadSalesOrderData();
  }
});

function loadSalesOrderData() {
  frappe.call({
    method: "phamos.api.get_customer_sales_order_status",
    callback: function(response) {
      if (response.exc) {
        console.error('API Exception:', response.exc);
        frappe.msgprint({
          title: 'Error',
          message: 'Failed to load sales order data. Check console for details.',
          indicator: 'red'
        });
        showSalesOrderError();
        return;
      }
      
      if (response.message) {
        salesOrderData = response.message;
        salesOrderDataLoaded = true;
        renderSalesOrderData(salesOrderData);
      } else {
        showSalesOrderError();
      }
    },
    error: function(err) {
      console.error("Error loading sales order data:", err);
      frappe.msgprint({
        title: 'Error',
        message: 'Failed to load sales order data. Check console for details.',
        indicator: 'red'
      });
      showSalesOrderError();
    }
  });
}

function renderSalesOrderData(data) {
  // Render summary cards
  $('#total-so-hrs').text(formatNumber(data.summary.total_so_hrs));
  $('#delivered-hrs').text(formatNumber(data.summary.delivered_hrs));
  
  // Store all sales orders
  originalSalesOrders = data.sales_orders || [];
  allSalesOrders = [...originalSalesOrders];
  soCurrentPage = 1;
  
  // Render table with pagination
  try {
    renderSalesOrderTable();
    renderSalesOrderPagination();
  } catch (e) {
    console.error('Error rendering table:', e);
  }
}



function renderSalesOrderTable() {
  const tbody = $('#so-table-body');
  tbody.empty();
  
  if (!allSalesOrders || allSalesOrders.length === 0) {
    tbody.append(`
      <tr>
        <td colspan="8" class="text-center text-muted" style="padding: 40px;">
          <i class="fa fa-inbox fa-2x mb-3" style="opacity: 0.3;"></i>
          <p class="mb-0"><strong>No Sales Orders Found</strong></p>
          <p class="small">There are no sales orders linked to implementations for your account yet.</p>
        </td>
      </tr>
    `);
    $('#so-page-info').text('Showing 0 - 0 of 0');
    return;
  }
  
  // Calculate pagination
  const startIndex = (soCurrentPage - 1) * soPageSize;
  const endIndex = Math.min(startIndex + soPageSize, allSalesOrders.length);
  const salesOrdersPage = allSalesOrders.slice(startIndex, endIndex);
  
  salesOrdersPage.forEach(so => {
    const statusBadge = getStatusBadge(so.status);
    const progressPercent = so.total_hrs > 0 ? (so.delivered_hrs / so.total_hrs * 100).toFixed(1) : 0;
    const progressColor = getProgressColor(progressPercent);
    const formattedDate = so.delivery_date ? frappe.datetime.str_to_user(so.delivery_date) : '-';
    
    const row = `
      <tr>
        <td>
          <a href="/app/sales-order/${so.name}" target="_blank">
            ${so.name}
          </a>
        </td>
        <td>${escapeHtml(so.title || '-')}</td>
        <td>${formattedDate}</td>
        <td>${statusBadge}</td>
        <td>${formatNumber(so.total_hrs)}</td>
        <td>${formatNumber(so.delivered_hrs)}</td>
        <td>${formatNumber(so.remaining_hrs)}</td>
        <td>
          <div class="d-flex align-items-center gap-2">
            <div class="progress flex-grow-1">
              <div class="progress-bar ${progressColor}" 
                   style="width: ${progressPercent}%">
              </div>
            </div>
            <span class="small text-nowrap" style="min-width: 40px;">${progressPercent}%</span>
          </div>
        </td>
      </tr>
    `;
    
    tbody.append(row);
  });
  
  // Update page info directly
  const pageInfoText = `Showing ${startIndex + 1} - ${endIndex} of ${allSalesOrders.length}`;
  document.getElementById('so-page-info').textContent = pageInfoText;
  $('#so-page-info').text(pageInfoText);
}


function getStatusBadge(status) {
  const colors = getStatusColor(status);
  return `<span class="badge" style="background-color: ${colors.bg}; color: ${colors.text}; font-weight: 500; padding: 5px 12px; border-radius: 4px;">${status}</span>`;
}

function getStatusColor(status) {
  const statusColors = {
    'Draft': { bg: '#d1d8dd', text: '#364a59' },
    'On Hold': { bg: '#ffeab6', text: '#7f5c00' },
    'To Deliver and Bill': { bg: '#ffe6cc', text: '#7f4200' },
    'To Bill': { bg: '#d4f5d4', text: '#1a731a' },
    'To Deliver': { bg: '#d4e7f7', text: '#16537a' },
    'Completed': { bg: '#d4f5d4', text: '#0a5e0a' },
    'Cancelled': { bg: '#ffe6e6', text: '#a10000' },
    'Closed': { bg: '#e8e8e8', text: '#4d4d4d' }
  };
  
  return statusColors[status] || { bg: '#e8f4f8', text: '#2e5f75' };
}

function getProgressColor(percent) {
  if (percent >= 100) return 'bg-success';
  if (percent >= 50) return 'bg-info';
  if (percent >= 25) return 'bg-warning';
  return 'bg-danger';
}

function formatNumber(num) {
  if (num === null || num === undefined) return '0';
  return parseFloat(num).toFixed(2);
}

function escapeHtml(text) {
  if (!text) return '';
  const map = {
    '&': '&amp;',
    '<': '&lt;',
    '>': '&gt;',
    '"': '&quot;',
    "'": '&#039;'
  };
  return text.replace(/[&<>"']/g, function(m) { return map[m]; });
}

function showSalesOrderError() {
  $('#so-table-body').html(`
    <tr>
      <td colspan="7" class="text-center text-danger py-4">
        <i class="fa fa-exclamation-triangle me-2"></i> Error loading sales orders. Please try again.
      </td>
    </tr>
  `);
}

function renderSalesOrderPagination() {
  const totalPages = Math.ceil(allSalesOrders.length / soPageSize);
  const pagination = $('#so-pagination');
  pagination.empty();
  
  if (totalPages <= 1) {
    return; // No pagination needed
  }
  
  // Previous button
  const prevDisabled = soCurrentPage === 1 ? 'disabled' : '';
  pagination.append(`
    <li class="page-item ${prevDisabled}">
      <a class="page-link" href="#" data-page="${soCurrentPage - 1}">
        <i class="fa fa-chevron-left"></i>
      </a>
    </li>
  `);
  
  // Page numbers
  const maxPagesToShow = 5;
  let startPage = Math.max(1, soCurrentPage - Math.floor(maxPagesToShow / 2));
  let endPage = Math.min(totalPages, startPage + maxPagesToShow - 1);
  
  // Adjust start if we're near the end
  if (endPage - startPage < maxPagesToShow - 1) {
    startPage = Math.max(1, endPage - maxPagesToShow + 1);
  }
  
  // First page
  if (startPage > 1) {
    pagination.append(`
      <li class="page-item">
        <a class="page-link" href="#" data-page="1">1</a>
      </li>
    `);
    if (startPage > 2) {
      pagination.append(`<li class="page-item disabled"><span class="page-link">...</span></li>`);
    }
  }
  
  // Page numbers
  for (let i = startPage; i <= endPage; i++) {
    const active = i === soCurrentPage ? 'active' : '';
    pagination.append(`
      <li class="page-item ${active}">
        <a class="page-link" href="#" data-page="${i}">${i}</a>
      </li>
    `);
  }
  
  // Last page
  if (endPage < totalPages) {
    if (endPage < totalPages - 1) {
      pagination.append(`<li class="page-item disabled"><span class="page-link">...</span></li>`);
    }
    pagination.append(`
      <li class="page-item">
        <a class="page-link" href="#" data-page="${totalPages}">${totalPages}</a>
      </li>
    `);
  }
  
  // Next button
  const nextDisabled = soCurrentPage === totalPages ? 'disabled' : '';
  pagination.append(`
    <li class="page-item ${nextDisabled}">
      <a class="page-link" href="#" data-page="${soCurrentPage + 1}">
        <i class="fa fa-chevron-right"></i>
      </a>
    </li>
  `);
  
  // Attach click handlers
  pagination.find('a.page-link').on('click', function(e) {
    e.preventDefault();
    const page = parseInt($(this).data('page'));
    if (!isNaN(page) && page !== soCurrentPage) {
      soCurrentPage = page;
      renderSalesOrderTable();
      renderSalesOrderPagination();
    }
  });
}

function updateSalesOrderPageInfo(start, end, total) {
  $('#so-page-info').text(`Showing ${start} - ${end} of ${total}`);
}

// ========================================
// Sales Orders Tab - Filters, Sort, and Search
// ========================================

let soCurrentSortColumn = null;
let soCurrentSortOrder = null;

// Status filter - use delegated event handler
$(document).on('change', '#so_status_filter', function() {
  applySalesOrderFilters();
});

// Clear filters - use delegated event handler
$(document).on('click', '#so_clear_filters', function() {
  $('#so_status_filter').val('');
  $('.so-column-filter').val('');
  applySalesOrderFilters();
});

// In-table search
$(document).on('input', '.so-column-filter', function() {
  applySalesOrderFilters();
});

// Sort functionality
$(document).on('click', '.sort-icon[data-so-column]', function(e) {
  e.stopPropagation();
  const column = $(this).data('so-column');
  const menu = $(this).siblings('.so-menu');
  
  // Hide all other menus
  $('.so-menu').not(menu).hide();
  
  // Toggle current menu
  menu.toggle();
});

$(document).on('click', '.so-menu .menu-item', function(e) {
  e.stopPropagation();
  const action = $(this).data('action');
  const menu = $(this).closest('.so-menu');
  const column = menu.siblings('.sort-icon').data('so-column');
  
  if (action === 'asc') {
    soCurrentSortColumn = column;
    soCurrentSortOrder = 'asc';
  } else if (action === 'desc') {
    soCurrentSortColumn = column;
    soCurrentSortOrder = 'desc';
  } else if (action === 'reset') {
    soCurrentSortColumn = null;
    soCurrentSortOrder = null;
  }
  
  applySalesOrderFilters();
  menu.hide();
});

// Hide menus when clicking outside
$(document).on('click', function() {
  $('.so-menu').hide();
});

function applySalesOrderFilters() {
  if (!originalSalesOrders || originalSalesOrders.length === 0) {
    return;
  }
  
  // Start with original data
  let filtered = [...originalSalesOrders];
  
  // Apply status filter
  const statusFilter = $('#so_status_filter').val();
  if (statusFilter) {
    filtered = filtered.filter(so => so.status === statusFilter);
  }
  
  // Apply column filters
  const columnFilterElements = $('.so-column-filter');
  
  columnFilterElements.each(function() {
    const column = $(this).data('so-column');
    const value = ($(this).val() || '').trim().toLowerCase();
    
    if (value) {
      filtered = filtered.filter(so => {
        let fieldValue = '';
        
        if (column === 'name') {
          fieldValue = (so.name || '').toString().toLowerCase();
        } else if (column === 'title') {
          fieldValue = (so.title || '').toString().toLowerCase();
        } else if (column === 'delivery_date') {
          fieldValue = (so.delivery_date || '').toString().toLowerCase();
        } else if (column === 'status') {
          fieldValue = (so.status || '').toString().toLowerCase();
        } else if (column === 'total_hrs') {
          fieldValue = (so.total_hrs || 0).toString();
        } else if (column === 'delivered_hrs') {
          fieldValue = (so.delivered_hrs || 0).toString();
        } else if (column === 'remaining_hrs') {
          fieldValue = (so.remaining_hrs || 0).toString();
        } else if (column === 'progress') {
          const progress = so.total_hrs > 0 ? ((so.delivered_hrs / so.total_hrs * 100).toFixed(1)) : '0';
          fieldValue = progress.toString();
        }
        
        return fieldValue.includes(value);
      });
    }
  });
  
  // Apply sorting
  if (soCurrentSortColumn && soCurrentSortOrder) {
    filtered.sort((a, b) => {
      let aVal, bVal;
      
      if (soCurrentSortColumn === 'name') {
        aVal = a.name || '';
        bVal = b.name || '';
      } else if (soCurrentSortColumn === 'title') {
        aVal = a.title || '';
        bVal = b.title || '';
      } else if (soCurrentSortColumn === 'delivery_date') {
        aVal = a.delivery_date || '';
        bVal = b.delivery_date || '';
      } else if (soCurrentSortColumn === 'status') {
        aVal = a.status || '';
        bVal = b.status || '';
      } else if (soCurrentSortColumn === 'total_hrs') {
        aVal = parseFloat(a.total_hrs) || 0;
        bVal = parseFloat(b.total_hrs) || 0;
      } else if (soCurrentSortColumn === 'delivered_hrs') {
        aVal = parseFloat(a.delivered_hrs) || 0;
        bVal = parseFloat(b.delivered_hrs) || 0;
      } else if (soCurrentSortColumn === 'remaining_hrs') {
        aVal = parseFloat(a.remaining_hrs) || 0;
        bVal = parseFloat(b.remaining_hrs) || 0;
      } else if (soCurrentSortColumn === 'progress') {
        aVal = a.total_hrs > 0 ? (a.delivered_hrs / a.total_hrs * 100) : 0;
        bVal = b.total_hrs > 0 ? (b.delivered_hrs / b.total_hrs * 100) : 0;
      }
      
      if (typeof aVal === 'string') {
        aVal = aVal.toLowerCase();
        bVal = bVal.toLowerCase();
      }
      
      if (soCurrentSortOrder === 'asc') {
        return aVal > bVal ? 1 : aVal < bVal ? -1 : 0;
      } else {
        return aVal < bVal ? 1 : aVal > bVal ? -1 : 0;
      }
    });
  }
  
  // Update filtered list and reset to first page
  allSalesOrders = filtered;
  soCurrentPage = 1;
  
  // Re-render table
  renderSalesOrderTable();
  renderSalesOrderPagination();
}