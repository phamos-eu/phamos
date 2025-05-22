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
  });
});

function reset_and_load() {
  totalCount = 0;
  loadedCount = 0;

  // Clear table rows except #no_data_row
  $('#timesheet_body').children('tr:not(#no_data_row)').remove();

  $('#no_data_row').hide();
  $('#load_more').show();
  load_timesheets();
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
        $tbody.append(`
          <tr>
            <td><input type="checkbox" class="row-select" /></td>
            <td>${row.name}</td>
            <td class="${row.timesheet_status === 'Billed' ? 'text-success fw-bold' : 'text-primary fw-bold'}">${row.timesheet_status}</td>
            <td>${row.employee}</td>
            <td>${row.employee_name}</td>
            <td>${frappe.datetime.str_to_user(row.start_date)}</td>
            <td>${frappe.datetime.str_to_user(row.end_date)}</td>
            <td>${row.custom_billing_status || ''}</td>
            <td>${format_hours(row.total_hours)}</td>
            <td>${format_hours(row.total_billable_hours)}</td>
            <td title="${frappe.datetime.str_to_user(row.creation)}">${formatShortRelative(row.creation)}</td>
          </tr>
        `);
      });

      loadedCount += data.length;
      update_footer();

      if (loadedCount >= totalCount || data.length < pageSize) {
        $('#load_more').hide();
      } else {
        $('#load_more').prop('disabled', false).text('Load More');
      }
    }
  });
}

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

  const headers = ['Timesheet', 'Status', 'Employee ID', 'Employee Name', 'Start Date', 'End Date', 'Billing Status', 'Total Hours', 'Billable Hours'];
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

      const headers = ['Timesheet', 'Status', 'Employee ID', 'Employee Name', 'Start Date', 'End Date', 'Billing Status', 'Total Hours', 'Billable Hours'];
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
  return `${hours}h ${minutes}m`;
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

