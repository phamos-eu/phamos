frappe.pages["mailcow-calander"].on_page_load = function (wrapper) {
  const page = frappe.ui.make_app_page({
    parent: wrapper,
    title: "Mailcow Calander",
    single_column: true,
  });

  const $body = $(page.body);

  $body.html(`
    <div style="padding: 10px 0;">
      <div id="mc-topbar" style="display:flex;flex-wrap:wrap;gap:12px;align-items:flex-end;margin-bottom:10px;"></div>
      <div style="margin-bottom:8px;">
        <span style="display:inline-flex;align-items:center;margin-right:14px;">
          <span style="display:inline-block;width:12px;height:12px;background:#22c55e;border-radius:3px;margin-right:6px;"></span>
          Available
        </span>
        <span style="display:inline-flex;align-items:center;">
          <span style="display:inline-block;width:12px;height:12px;background:#ef4444;border-radius:3px;margin-right:6px;"></span>
          Booked
        </span>
      </div>
      <div id="mc-calendar" style="min-height:680px;border:1px solid var(--border-color, #ddd);border-radius:10px;padding:8px;"></div>
    </div>
  `);

  const topBar = $body.find("#mc-topbar")[0];
  const calendarSelector = "#mc-calendar";

  const employeeWrap = document.createElement("div");
  employeeWrap.style.minWidth = "280px";
  topBar.appendChild(employeeWrap);

  const fromWrap = document.createElement("div");
  fromWrap.innerHTML = '<label class="control-label" style="display:block;margin-bottom:4px;">From Date</label><input type="date" id="mc-from-date" class="input-with-feedback form-control">';
  topBar.appendChild(fromWrap);

  const toWrap = document.createElement("div");
  toWrap.innerHTML = '<label class="control-label" style="display:block;margin-bottom:4px;">To Date</label><input type="date" id="mc-to-date" class="input-with-feedback form-control">';
  topBar.appendChild(toWrap);

  const filterWrap = document.createElement("div");
  filterWrap.style.display = "flex";
  filterWrap.style.gap = "12px";
  filterWrap.style.paddingBottom = "6px";
  filterWrap.innerHTML = `
    <label><input type="checkbox" id="mc-show-free" checked> Show Available</label>
    <label><input type="checkbox" id="mc-show-busy" checked> Show Booked</label>
  `;
  topBar.appendChild(filterWrap);

  const refreshBtn = document.createElement("button");
  refreshBtn.className = "btn btn-primary";
  refreshBtn.textContent = "Refresh";
  topBar.appendChild(refreshBtn);

  const employeeControl = frappe.ui.form.make_control({
    parent: employeeWrap,
    df: {
      fieldtype: "Link",
      options: "Employee",
      label: "Employee",
      fieldname: "employee",
      reqd: 1,
    },
    render_input: true,
  });

  const fromInput = topBar.querySelector("#mc-from-date");
  const toInput = topBar.querySelector("#mc-to-date");
  const showFree = topBar.querySelector("#mc-show-free");
  const showBusy = topBar.querySelector("#mc-show-busy");

  fromInput.value = frappe.datetime.month_start();
  toInput.value = frappe.datetime.month_end();

  frappe.call({
    method: "phamos.phamos.page.mailcow_calander.mailcow_calander.get_logged_in_employee",
    callback: function (r) {
      if (r.message && r.message.name) {
        employeeControl.set_value(r.message.name);
        setTimeout(loadCalendar, 250);
      }
    },
  });

  function loadCalendar() {
    const employee = employeeControl.get_value();
    const from_date = fromInput.value;
    const to_date = toInput.value;

    if (!employee) {
      frappe.msgprint("Please select Employee.");
      return;
    }
    if (!from_date || !to_date) {
      frappe.msgprint("Please select From Date and To Date.");
      return;
    }
    if (from_date > to_date) {
      frappe.msgprint("From Date cannot be after To Date.");
      return;
    }

    frappe.require([
      "/assets/frappe/js/lib/moment/moment.min.js",
      "/assets/frappe/js/lib/fullcalendar/fullcalendar.min.js",
    ], function () {
      frappe.require("/assets/frappe/js/lib/fullcalendar/fullcalendar.min.css");

      frappe.call({
        method: "phamos.phamos.page.mailcow_calander.mailcow_calander.get_calendar_events",
        args: { employee, from_date, to_date },
        freeze: true,
        freeze_message: "Loading Mailcow calendar...",
        callback: function (r) {
          const payload = r.message || {};
          const allEvents = Array.isArray(payload.events) ? payload.events : [];

          const events = allEvents
            .filter((event) => {
              if (event.status === "free" && !showFree.checked) return false;
              if (event.status === "busy" && !showBusy.checked) return false;
              return true;
            })
            .map((event) => {
              if (event.status === "free") {
                return {
                  title: "Available",
                  start: event.start,
                  end: event.end,
                  backgroundColor: "#22c55e",
                  borderColor: "#22c55e",
                  textColor: "#ffffff",
                };
              }

              return {
                title: "Booked",
                start: event.start,
                end: event.end,
                backgroundColor: "#ef4444",
                borderColor: "#ef4444",
                textColor: "#ffffff",
              };
            });

          const $el = $(calendarSelector);
          if ($el.data("fullCalendar")) {
            $el.fullCalendar("destroy");
          }

          $el.fullCalendar({
            header: {
              left: "prev,next today",
              center: "title",
              right: "month,agendaWeek,agendaDay",
            },
            buttonIcons: false,
            buttonText: {
              prev: "‹",
              next: "›",
              today: "Today",
              month: "Month",
              agendaWeek: "Week",
              agendaDay: "Day",
            },
            defaultView: "agendaWeek",
            height: "auto",
            editable: false,
            events,
            eventRender(event, element) {
              element.attr(
                "title",
                `${event.title}: ${moment(event.start).format("YYYY-MM-DD HH:mm")} - ${moment(event.end).format("HH:mm")}`
              );
            },
          });
        },
      });
    });
  }

  refreshBtn.addEventListener("click", loadCalendar);
  showFree.addEventListener("change", loadCalendar);
  showBusy.addEventListener("change", loadCalendar);
};
