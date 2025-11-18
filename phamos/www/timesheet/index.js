let pageSize = 20;
let totalCount = 0;
let loadedCount = 0;

frappe.ready(() => {

  // Check if user is Guest
  if (frappe.session.user === "Guest") {
    frappe.msgprint("Please log in to access this page.");
    setTimeout(() => {
      window.location.href = "/login";
    }, 1500);
    return; // Stop further execution
  }

  //set default date range
  set_default_month_range();
  load_projects();
  attach_filter_events();
  reset_and_load();

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
  
    // ✅ Get last day of the selected month
    const lastDay = new Date(year, month + 1, 0);
  
    // ✅ Format manually as yyyy-mm-dd (timezone-safe)
    const yyyy = lastDay.getFullYear();
    const mm = String(lastDay.getMonth() + 1).padStart(2, '0');
    const dd = String(lastDay.getDate()).padStart(2, '0');
    const formattedEndDate = `${yyyy}-${mm}-${dd}`;
  
    $('#to_date').val(formattedEndDate);
  });
  
  //reset filters
  $('#clear_filters').on('click', function () {
    $('#from_date').val('');
    $('#to_date').val('');
    $('#project_filter').val('');
    reset_and_load();
    load_graph_data(); /// load graph data//
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
  ['#from_date', '#to_date', '#project_filter'].forEach(selector => {
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
    args: { from_date, to_date, project, offset, limit: pageSize },
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
        let btnText = "Request Adjustments";
        let btnColor = "#5198e3"; // default blue

        
        if (row.customer_comment) {
          btnText = "Under Review";
          btnColor = "#ffc107";
        }

        const relatedIssues = row.related_issue || '';
        const relatedPreview = truncateText(relatedIssues, 80);
        const relatedTooltip = escapeHtml(relatedIssues);
        const relatedDisplay = relatedPreview ? escapeHtml(relatedPreview) : '-';

        $tbody.append(`
          <tr>
            <td><input type="checkbox" class="row-select" /></td>
            <td>${row.name}</td>
            <td>${frappe.datetime.str_to_user(row.start_date)}</td>
            <td>${row.custom_billing_status || ''}</td>
            <td>${format_hours(row.total_hours)}</td>
            <td>${format_hours(row.total_billable_hours)}</td>
            <td>
              <span class="d-inline-block text-truncate" style="max-width: 220px;" title="${relatedTooltip}">
                ${relatedDisplay}
              </span>
            </td>
            <td>
              <button 
                class="btn btn-sm comment-btn"
                style="background-color: ${btnColor}; color: white;"
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

  const headers = ['Employee', 'Employee Name', 'Start Date', 'End Date', 'Total Hours', 'Billable Hours'];
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

  const headers = ['Timesheet', 'Employee ID', 'Start Date', 'End Date', 'Billing Status', 'Total Hours', 'Billable Hours'];
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
        row.start_date,
        row.end_date,
        row.custom_billing_status || '',
        row.total_hours,
        row.total_billable_hours
      ]);

      const headers = ['Timesheet', 'Employee ID', 'Start Date', 'End Date', 'Billing Status', 'Total Hours', 'Billable Hours'];
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
//////////////////////////process your timesheets data////////////////////
function processDataForGraph(timesheets) {
    const weekCategories = new Set();
    const projectData = {};

    timesheets.forEach(row => {
        const date = new Date(row.start_date);
        const day = date.getDay();
        const diff = date.getDate() - day + (day === 0 ? -6 : 1);
        const monday = new Date(date.setDate(diff));
        const weekStart = monday.toISOString().split('T')[0];

        weekCategories.add(weekStart);

        const projectKey = row.project_label; // 👈 use label instead of project_name

        if (!projectData[projectKey]) {
            projectData[projectKey] = {};
        }
        if (!projectData[projectKey][weekStart]) {
            projectData[projectKey][weekStart] = { total: 0, billable: 0 };
        }

        projectData[projectKey][weekStart].total += parseFloat(row.total_hours || 0);
        projectData[projectKey][weekStart].billable += parseFloat(row.total_billable_hours || 0);
    });

    const categories = Array.from(weekCategories).sort();
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

        categories.forEach(week => {
            const data = projectData[projectName][week] || { total: 0, billable: 0 };
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

    Highcharts.chart('timesheet-graph-container', {
        chart: { type: 'area' },
        title: { text: 'Billable vs Non-Billable by Project' },
        xAxis: { categories, title: { text: 'Week' } },
        yAxis: { min: 0, title: { text: 'Hours' } },
        tooltip: {
            shared: true,
            formatter: function () {
                let s = `<b>${this.x}</b><br/>`;
                this.points.forEach(point => {
                    s += `<span style="color:${point.color}">\u25CF</span> ${point.series.name}: <b>${point.y.toFixed(2)} hrs</b><br/>`;
                });
                return s;
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
loadAndRenderGraph();

// Handle "Request Adjustments" button click dynamically
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
