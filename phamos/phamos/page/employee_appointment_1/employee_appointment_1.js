frappe.pages['employee-appointment-1'].on_page_load = function(wrapper) {

    var page = frappe.ui.make_app_page({
        parent: wrapper,
        title: __('Schedule Meeting & Email'),
        single_column: true
    });

    new EmployeeAppointmentPage(wrapper, page);
};


class EmployeeAppointmentPage {

    constructor(wrapper, page) {

        this.wrapper = wrapper;
        this.page = page;

        this.doc = null;
        this.frm = null;

        this.reference_doctype = "";
        this.reference_name = "";

        this.employee = null;
        this._from_employee = null;

        this.proposals = [];
        this._proposalKeys = new Set();

        this.attachments = [];

        this._slotRequestId = 0;

        this.make();
    }


    // ============================================================
    // INITIALIZATION
    // ============================================================

    make() {

        this.make_layout();

        this.setup_fields();

        this.setup_events();

        this.set_defaults();

        this.init_email_template_actions();

        this.init_email_multiselect_queries();

        this.init_attachments();

        this.render_proposals();
    }


    // ============================================================
    // PAGE LAYOUT
    // ============================================================

    make_layout() {

        $(this.page.body).html(`

            <div class="hybrid-meeting-page">

                <div class="hybrid-page-container">

                    <div class="hybrid-main-grid">

                        <!-- EMAIL -->

                        <div class="hybrid-card">

                            <div class="hybrid-card-header">

                                <div class="hybrid-card-title">
                                    ${__("Email")}
                                </div>

                            </div>

                            <div class="hybrid-card-body">

                                <div class="form-group">

                                    <label>
                                        ${__("From")}
                                    </label>

                                    <div id="sender"></div>

                                </div>


                                <div class="form-group">

                                    <label>
                                        ${__("To")}
                                    </label>

                                    <div id="recipients"></div>

                                </div>


                                <div class="email-options-toggle">

                                    <button
                                        type="button"
                                        class="btn btn-default btn-xs"
                                        id="toggle-email-options">

                                        ${frappe.utils.icon(
                                            "down",
                                            "xs"
                                        )}

                                        ${__("More Options")}

                                    </button>

                                </div>


                                <div
                                    id="email-extra-options"
                                    style="display:none;">

                                    <div class="form-group">

                                        <label>
                                            ${__("CC")}
                                        </label>

                                        <div id="cc"></div>

                                    </div>


                                    <div class="form-group">

                                        <label>
                                            ${__("BCC")}
                                        </label>

                                        <div id="bcc"></div>

                                    </div>


                                    <div class="form-group">

                                        <label>
                                            ${__("Email Template")}
                                        </label>

                                        <div id="email-template"></div>

                                    </div>


                                    <div id="template-actions"></div>


                                    <div class="form-group">

                                        <label>
                                            ${__("Schedule Send At")}
                                        </label>

                                        <div id="send-after"></div>

                                    </div>

                                </div>


                                <div class="form-group">

                                    <label>
                                        ${__("Subject")}
                                    </label>

                                    <div id="email-subject"></div>

                                </div>


                                <div class="form-group">

                                    <label>
                                        ${__("Message")}
                                    </label>

                                    <div id="email-body"></div>

                                </div>


                                <div class="form-group">

                                    <label>
                                        ${__("Select Attachments")}
                                    </label>

                                    <div id="attachments"></div>

                                </div>

                            </div>

                        </div>


                        <!-- EVENT -->

                        <div class="hybrid-card">

                            <div class="hybrid-card-header">

                                <div class="hybrid-card-title">
                                    ${__("Event")}
                                </div>

                            </div>


                            <div class="hybrid-card-body">

                                <div class="form-group">

                                    <label>
                                        ${__("Meeting Subject")}
                                    </label>

                                    <div id="subject"></div>

                                </div>


                                <div class="form-group">

                                    <label>
                                        ${__("Event Type")}
                                    </label>

                                    <div id="event-type"></div>

                                </div>


                                <div class="schedule-controls">

                                    <div class="schedule-control">

                                        <label>
                                            ${__("Day to Fetch Slots")}
                                        </label>

                                        <div id="day"></div>

                                    </div>


                                    <div
                                        class="schedule-control duration-control">

                                        <label>
                                            ${__("Duration")}
                                        </label>

                                        <div id="duration"></div>

                                    </div>


                                    <div
                                        class="schedule-control fetch-control">

                                        <button
                                            type="button"
                                            class="btn btn-primary"
                                            id="fetch-slots">

                                            ${__("Fetch Available Slots")}

                                        </button>

                                    </div>

                                </div>


                                <div
                                    id="slots-container"
                                    class="slots-container">

                                    <div class="slots-placeholder">

                                        ${__(
                                            "Slots will appear here after fetching."
                                        )}

                                    </div>

                                </div>


                                <div class="proposals-section">

                                    <div class="proposals-header">

                                        <div class="proposals-title">
                                            ${__("Selected Proposals")}
                                        </div>


                                        <button
                                            type="button"
                                            class="btn btn-xs btn-primary"
                                            id="add-all-proposals"
                                            disabled>

                                            ${__("Add All")}

                                        </button>

                                    </div>


                                    <div class="table-responsive">

                                        <table
                                            class="table table-bordered proposal-table">

                                            <thead>

                                                <tr>

                                                    <th>
                                                        ${__("Date")}
                                                    </th>

                                                    <th>
                                                        ${__("Start")}
                                                    </th>

                                                    <th>
                                                        ${__("End")}
                                                    </th>

                                                    <th class="text-right">
                                                        ${__("Add")}
                                                    </th>

                                                </tr>

                                            </thead>


                                            <tbody id="proposal-rows">
                                            </tbody>

                                        </table>

                                    </div>


                                    <div
                                        id="proposal-empty"
                                        class="text-muted proposal-empty">

                                        ${__("No entries yet")}

                                    </div>

                                </div>


                                <div
                                    id="include-proposals-wrapper"
                                    class="form-group"
                                    style="display:none;">

                                    <div id="include-proposals"></div>

                                </div>


                                <div class="form-group">

                                    <label>
                                        ${__("Location")}
                                    </label>

                                    <div id="location"></div>

                                </div>


                                <div class="form-group">

                                    <label>
                                        ${__("Description")}
                                    </label>

                                    <div id="description"></div>

                                </div>

                            </div>

                        </div>

                    </div>


                    <div class="hybrid-actions">

                        <button
                            type="button"
                            class="btn btn-default"
                            id="cancel-button">

                            ${__("Cancel")}

                        </button>


                        <button
                            type="button"
                            class="btn btn-primary"
                            id="submit-button">

                            ${__("Create Event & Send Email")}

                        </button>

                    </div>

                </div>

            </div>

        `);

        this.add_styles();
    }


    // ============================================================
    // FORM CONTROLS
    // ============================================================

    setup_fields() {

        this.sender = this.make_control(
            "#sender",
            {
                fieldtype: "Data",
                fieldname: "sender",
                read_only: 1
            }
        );


        this.recipients = this.make_control(
            "#recipients",
            {
                fieldtype: "MultiSelect",
                fieldname: "recipients"
            }
        );


        this.cc = this.make_control(
            "#cc",
            {
                fieldtype: "MultiSelect",
                fieldname: "cc"
            }
        );


        this.bcc = this.make_control(
            "#bcc",
            {
                fieldtype: "MultiSelect",
                fieldname: "bcc"
            }
        );


        this.email_template = this.make_control(
            "#email-template",
            {
                fieldtype: "Link",
                fieldname: "email_template",
                options: "Email Template"
            }
        );


        this.send_after = this.make_control(
            "#send-after",
            {
                fieldtype: "Datetime",
                fieldname: "send_after"
            }
        );


        this.email_subject = this.make_control(
            "#email-subject",
            {
                fieldtype: "Data",
                fieldname: "email_subject"
            }
        );


        this.email_body = this.make_control(
            "#email-body",
            {
                fieldtype: "Text Editor",
                fieldname: "email_body"
            }
        );


        this.subject = this.make_control(
            "#subject",
            {
                fieldtype: "Data",
                fieldname: "subject",
                reqd: 1
            }
        );


        this.event_type = this.make_control(
            "#event-type",
            {
                fieldtype: "Select",
                fieldname: "event_type",
                options: [
                    "Public",
                    "Private"
                ]
            }
        );


        this.day = this.make_control(
            "#day",
            {
                fieldtype: "Date",
                fieldname: "day"
            }
        );


        this.duration = this.make_control(
            "#duration",
            {
                fieldtype: "Select",
                fieldname: "duration_minutes",
                options: [
                    "15",
                    "30",
                    "60",
                    "90",
                    "120"
                ]
            }
        );


        this.include_proposals = this.make_control(
            "#include-proposals",
            {
                fieldtype: "Check",
                fieldname: "include_proposals_in_email",
                label: __("Include proposals in email")
            }
        );


        this.location = this.make_control(
            "#location",
            {
                fieldtype: "Data",
                fieldname: "location"
            }
        );


        this.description = this.make_control(
            "#description",
            {
                fieldtype: "Text",
                fieldname: "description"
            }
        );
    }


    make_control(selector, df) {

        const parent =
            $(this.page.body).find(selector)[0];

        if (!parent) {

            console.error(
                "Control parent not found:",
                selector
            );

            return null;
        }

        return frappe.ui.form.make_control({
            parent: parent,
            df: df,
            render_input: true
        });
    }


    // ============================================================
    // DEFAULTS
    // ============================================================

    set_defaults() {

        this.day.set_value(
            frappe.datetime.get_today()
        );


        this.duration.set_value(
            "60"
        );


        this.event_type.set_value(
            "Private"
        );


        this.location.set_value(
            this.generate_jitsi_link()
        );


        this.sender.set_value(
            frappe.session.user_email || ""
        );


        this.subject.set_value(
            ""
        );


        this.email_subject.set_value(
            ""
        );


        this.email_body.set_value(
            this.default_email_body()
        );
    }


    // ============================================================
    // EVENTS
    // ============================================================

    setup_events() {

        const $body =
            $(this.page.body);


        // --------------------------------------------------------
        // Toggle email options
        // --------------------------------------------------------

        $body
            .find("#toggle-email-options")
            .on(
                "click",
                () => {

                    const $wrapper =
                        $body.find(
                            "#email-extra-options"
                        );

                    const visible =
                        $wrapper.is(":visible");


                    if (visible) {

                        $wrapper.slideUp(150);

                        $body
                            .find("#toggle-email-options")
                            .html(
                                frappe.utils.icon(
                                    "down",
                                    "xs"
                                ) +
                                " " +
                                __("More Options")
                            );

                    } else {

                        $wrapper.slideDown(150);

                        $body
                            .find("#toggle-email-options")
                            .html(
                                frappe.utils.icon(
                                    "up-line",
                                    "xs"
                                ) +
                                " " +
                                __("Less Options")
                            );
                    }
                }
            );


        // --------------------------------------------------------
        // Subject -> Email Subject
        // --------------------------------------------------------

        let emailSubjectTouched = false;


        if (this.email_subject?.$input) {

            this.email_subject.$input.on(
                "change",
                () => {

                    emailSubjectTouched = true;

                }
            );
        }


        if (this.subject?.$input) {

            this.subject.$input.on(
                "change",
                () => {

                    if (!emailSubjectTouched) {

                        this.email_subject.set_value(
                            this.subject.get_value()
                        );

                    }
                }
            );
        }


        // --------------------------------------------------------
        // Fetch
        // --------------------------------------------------------

        $body
            .find("#fetch-slots")
            .on(
                "click",
                () => this.fetch_slots()
            );


        // --------------------------------------------------------
        // Add All
        // --------------------------------------------------------

        $body
            .find("#add-all-proposals")
            .on(
                "click",
                () => this.add_all_proposals_to_email()
            );


        // --------------------------------------------------------
        // Cancel
        // --------------------------------------------------------

        $body
            .find("#cancel-button")
            .on(
                "click",
                () => {

                    frappe.set_route(
                        "home"
                    );

                }
            );


        // --------------------------------------------------------
        // Submit
        // --------------------------------------------------------

        $body
            .find("#submit-button")
            .on(
                "click",
                () => this.submit()
            );
    }


    // ============================================================
    // FETCH SLOTS
    // ============================================================

    fetch_slots() {

        const day =
            this.day.get_value();


        const duration =
            cint(
                this.duration.get_value()
            ) || 60;


        if (!day) {

            frappe.msgprint(
                __("Please select a day to fetch slots.")
            );

            return;
        }


        if (!duration) {

            frappe.msgprint(
                __("Please select duration.")
            );

            return;
        }


        // --------------------------------------------------------
        // FROM
        //
        // The sender is the primary calendar participant.
        // --------------------------------------------------------

        const fromUser =
            this.get_from_user();


        if (!fromUser) {

            frappe.msgprint(
                __("Unable to determine the From user.")
            );

            return;
        }


        // --------------------------------------------------------
        // TO
        //
        // The first recipient is sent to backend.
        //
        // Backend decides whether it is:
        //
        // 1. Frappe System User with calendar
        // OR
        // 2. Normal external person
        //
        // No frontend decision is required.
        // --------------------------------------------------------

        const toUser =
            this.get_to_user();


        const $button =
            $(this.page.body)
                .find("#fetch-slots");


        const $container =
            $(this.page.body)
                .find("#slots-container");


        $button
            .prop(
                "disabled",
                true
            )
            .text(
                __("Fetching...")
            );


        $container.html(`
            <div class="slots-placeholder">
                ${__("Checking calendar availability...")}
            </div>
        `);


        // --------------------------------------------------------
        // Clear previous availability.
        //
        // Existing selected proposals remain intentionally.
        // --------------------------------------------------------

        const requestId =
            (this._slotRequestId || 0) + 1;


        this._slotRequestId =
            requestId;


        frappe.call({

            method:
                "phamos.phamos.page.employee_appointment_1.employee_appointment_1.get_common_free_slots",


            args: {

                from_email:
                    fromUser,

                to_email:
                    toUser || "",

                from_date:
                    day,

                to_date:
                    day,

                duration_minutes:
                    duration

            },


            freeze: true,


            freeze_message:
                __("Checking calendar availability..."),


            callback: (r) => {

                if (
                    requestId !==
                    this._slotRequestId
                ) {
                    return;
                }


                $button
                    .prop(
                        "disabled",
                        false
                    )
                    .text(
                        __("Fetch Available Slots")
                    );


                if (r.exc) {

                    $container.html(`
                        <div class="text-danger slots-placeholder">
                            ${__("Unable to fetch slots.")}
                        </div>
                    `);

                    return;
                }


                let response = r.message || {};

				console.log("Common free slots response:", response);

				let slots = [];

				if (Array.isArray(response)) {
					// Backward compatibility if backend returns array directly
					slots = response;

				} else if (Array.isArray(response.common_free_slots)) {
					// Current backend response
					slots = response.common_free_slots;

				} else if (Array.isArray(response.slots)) {
					// Optional compatibility
					slots = response.slots;

				} else if (Array.isArray(response.data)) {
					// Optional compatibility
					slots = response.data;
				}

				console.log("Slots to render:", slots);

				this.render_slots(slots);

            },


            error: () => {

                if (
                    requestId !==
                    this._slotRequestId
                ) {
                    return;
                }


                $button
                    .prop(
                        "disabled",
                        false
                    )
                    .text(
                        __("Fetch Available Slots")
                    );


                $container.html(`
                    <div class="text-danger slots-placeholder">
                        ${__(
                            "Unable to fetch available slots."
                        )}
                    </div>
                `);
            }

        });
    }


    // ============================================================
    // FROM USER
    // ============================================================

    get_from_user() {

        /*
         * The backend expects a Frappe User name or email.
         *
         * We use the sender field because it represents the
         * actual From account.
         */

        const sender =
            this.sender.get_value() || "";


        if (sender.trim()) {

            return sender.trim();
        }


        if (
            frappe.session &&
            frappe.session.user &&
            frappe.session.user !== "Guest"
        ) {

            return frappe.session.user;
        }


        return "";
    }


    // ============================================================
    // BACKWARD-COMPATIBLE FROM EMPLOYEE
    // ============================================================

    get_from_employee() {

        /*
         * Kept for compatibility with any other code that may
         * still call this method.
         *
         * Availability itself now uses From User directly.
         */

        if (this.employee) {
            return this.employee;
        }


        if (
            frappe.route_options &&
            frappe.route_options.employee
        ) {

            return frappe.route_options.employee;
        }


        if (this._from_employee) {
            return this._from_employee;
        }


        if (
            frappe.session &&
            frappe.session.user &&
            frappe.session.user !== "Guest"
        ) {

            return frappe.session.user;
        }


        return null;
    }


    // ============================================================
    // TO USER
    // ============================================================

    get_to_user() {

        const value =
            this.recipients.get_value() || "";


        if (!value) {
            return "";
        }


        /*
         * MultiSelect returns comma-separated recipients.
         *
         * Only the first recipient participates in calendar
         * availability.
         *
         * Email sending still uses the complete recipients list.
         */

        const first =
            value
                .split(",")
                .map(
                    item => item.trim()
                )
                .filter(Boolean)[0];


        return first || "";
    }


    // ============================================================
    // RENDER SLOTS
    // ============================================================

    render_slots(slots) {

    const $container =
        $(this.page.body)
            .find("#slots-container");


    if (
        !Array.isArray(slots) ||
        !slots.length
    ) {

        $container.html(`
            <div class="slots-placeholder">
                ${__("No common available slots found.")}
            </div>
        `);

        return;
    }


    console.log("Slots to render:", slots);


    /*
     * Backend returns:
     *
     * {
     *     date: "2026-08-31",
     *     from_time: "09:30:00",
     *     to_time: "10:30:00"
     * }
     *
     * Convert those values into moment objects.
     */

    const availableMap = new Map();


    slots.forEach((slot) => {

        if (
            !slot ||
            !slot.date ||
            !slot.from_time ||
            !slot.to_time
        ) {
            return;
        }


        const start =
            moment(
                `${slot.date} ${slot.from_time}`,
                "YYYY-MM-DD HH:mm:ss"
            );


        const end =
            moment(
                `${slot.date} ${slot.to_time}`,
                "YYYY-MM-DD HH:mm:ss"
            );


        if (
            !start.isValid() ||
            !end.isValid()
        ) {
            console.warn(
                "Invalid slot:",
                slot
            );

            return;
        }


        const key =
            this.make_slot_key(
                start,
                end
            );


        availableMap.set(
            key,
            {
                start: start,
                end: end,
                original: slot
            }
        );
    });


    if (!availableMap.size) {

        $container.html(`
            <div class="slots-placeholder">
                ${__("No available slots found.")}
            </div>
        `);

        return;
    }


    /*
     * Use the date returned by the backend.
     */

    const selectedDate =
        slots[0].date;


    const now =
        moment();


    const isToday =
        selectedDate ===
        now.format("YYYY-MM-DD");


    const startHour = 7;
    const endHour = 19;
    const interval = 15;


    const duration =
        cint(
            this.duration.get_value()
        ) || 60;


    let html = `

        <div class="availability-box">

            <div class="availability-title">

                ${__("Available Time Slots")}

                <span class="availability-date">

                    ${moment(
                        selectedDate,
                        "YYYY-MM-DD"
                    ).format(
                        "dddd, MMM D, YYYY"
                    )}

                </span>

            </div>


            <div class="timeline-scroll">

                <div
                    class="timeline-track"
                    style="
                        min-width:
                        ${
                            (
                                (
                                    endHour -
                                    startHour
                                ) *
                                60 /
                                interval
                            ) * 86
                        }px;
                    "
                >

    `;


    /*
     * Generate timeline cells.
     *
     * Only cells returned by the backend are clickable/available.
     */

    for (
        let minutes = startHour * 60;
        minutes < endHour * 60;
        minutes += interval
    ) {

        const hour =
            Math.floor(
                minutes / 60
            );


        const minute =
            minutes % 60;


        const timeStr =
            `${String(hour).padStart(
                2,
                "0"
            )}:${String(minute).padStart(
                2,
                "0"
            )}`;


        const slotStart =
            moment(
                selectedDate,
                "YYYY-MM-DD"
            )
                .hour(hour)
                .minute(minute)
                .second(0)
                .millisecond(0);


        /*
         * Don't show past times for today.
         */

        if (
            isToday &&
            slotStart.isBefore(now)
        ) {
            continue;
        }


        const slotEnd =
            slotStart
                .clone()
                .add(
                    duration,
                    "minutes"
                );


        /*
         * Don't go beyond timeline.
         */

        if (
            slotEnd.hour() > endHour ||
            (
                slotEnd.hour() === endHour &&
                slotEnd.minute() > 0
            )
        ) {
            continue;
        }


        const key =
            this.make_slot_key(
                slotStart,
                slotEnd
            );


        const available =
            availableMap.has(key);


        const selected =
            this._proposalKeys.has(key);


        let classes =
            "timeline-slot";


        classes +=
            available
                ? " slot-available"
                : " slot-busy";


        if (selected) {

            classes +=
                " slot-selected";
        }


        html += `

            <div
                class="${classes}"
                data-start="${frappe.utils.escape_html(
                    slotStart.format(
                        "YYYY-MM-DD HH:mm:ss"
                    )
                )}"
                data-end="${frappe.utils.escape_html(
                    slotEnd.format(
                        "YYYY-MM-DD HH:mm:ss"
                    )
                )}"
                data-key="${frappe.utils.escape_html(
                    key
                )}"
                data-available="${available ? 1 : 0}"
            >

                ${
                    minute === 0
                        ? `
                            <div class="timeline-hour">
                                ${timeStr}
                            </div>
                        `
                        : ""
                }


                <div class="slot-start">
                    ${timeStr}
                </div>


                <div class="slot-arrow">
                    ↓
                </div>


                <div class="slot-end">
                    ${slotEnd.format("HH:mm")}
                </div>


                <div class="slot-status">

                    ${
                        available
                            ? __("Available")
                            : __("Busy")
                    }

                </div>

            </div>

        `;
    }


    html += `

                </div>

            </div>


            <div class="timeline-legend">

                <div>
                    <span class="legend available"></span>
                    ${__("Available")}
                </div>


                <div>
                    <span class="legend selected"></span>
                    ${__("Selected")}
                </div>


                <div>
                    <span class="legend busy"></span>
                    ${__("Busy")}
                </div>

            </div>

        </div>

    `;


    $container.html(html);


    /*
     * Only slots actually returned by the backend are clickable.
     */

    $container
        .find(".slot-available")
        .on(
            "click",
            (e) => {

                const $slot =
                    $(e.currentTarget);


                const start =
                    $slot.attr(
                        "data-start"
                    );


                const end =
                    $slot.attr(
                        "data-end"
                    );


                const key =
                    $slot.attr(
                        "data-key"
                    );


                if (
                    this._proposalKeys.has(key)
                ) {

                    this.remove_proposal(
                        start,
                        end
                    );

                } else {

                    this.add_proposal(
                        start,
                        end
                    );
                }


                this.render_slots(
                    slots
                );
            }
        );
}



    // ============================================================
    // SLOT KEY
    // ============================================================

    make_slot_key(start, end) {

        const startValue =
            moment.isMoment(start)
                ? start.format(
                    "YYYY-MM-DD HH:mm:ss"
                )
                : moment(start).format(
                    "YYYY-MM-DD HH:mm:ss"
                );


        const endValue =
            moment.isMoment(end)
                ? end.format(
                    "YYYY-MM-DD HH:mm:ss"
                )
                : moment(end).format(
                    "YYYY-MM-DD HH:mm:ss"
                );


        return (
            `${startValue}__${endValue}`
        );
    }


    // ============================================================
    // PROPOSALS
    // ============================================================

    add_proposal(start, end) {

        const key =
            `${start}__${end}`;


        if (
            this._proposalKeys.has(key)
        ) {
            return;
        }


        this._proposalKeys.add(
            key
        );


        this.proposals.push({
            start: start,
            end: end
        });


        this.proposals.sort(
            (a, b) =>
                moment(a.start).valueOf() -
                moment(b.start).valueOf()
        );


        this.render_proposals();
    }


    remove_proposal(start, end) {

        const key =
            `${start}__${end}`;


        this._proposalKeys.delete(
            key
        );


        this.proposals =
            this.proposals.filter(
                (row) =>
                    !(
                        row.start === start &&
                        row.end === end
                    )
            );


        this.render_proposals();
    }


    render_proposals() {

        const $tbody =
            $(this.page.body)
                .find("#proposal-rows");


        const $empty =
            $(this.page.body)
                .find("#proposal-empty");


        const $addAll =
            $(this.page.body)
                .find("#add-all-proposals");


        $tbody.empty();


        if (
            !this.proposals.length
        ) {

            $empty.show();


            $addAll.prop(
                "disabled",
                true
            );


            $(this.page.body)
                .find(
                    "#include-proposals-wrapper"
                )
                .hide();


            return;
        }


        $empty.hide();


        $addAll.prop(
            "disabled",
            false
        );


        $(this.page.body)
            .find(
                "#include-proposals-wrapper"
            )
            .show();


        this.proposals.forEach(
            (row) => {

                const start =
                    moment(row.start);


                const end =
                    moment(row.end);


                const tr = $(`
                    <tr>

                        <td>
                            ${
                                start.isValid()
                                    ? start.format(
                                        "MMM D, YYYY"
                                    )
                                    : frappe.utils.escape_html(
                                        row.start
                                    )
                            }
                        </td>


                        <td>
                            ${
                                start.isValid()
                                    ? start.format(
                                        "HH:mm"
                                    )
                                    : frappe.utils.escape_html(
                                        row.start
                                    )
                            }
                        </td>


                        <td>
                            ${
                                end.isValid()
                                    ? end.format(
                                        "HH:mm"
                                    )
                                    : frappe.utils.escape_html(
                                        row.end
                                    )
                            }
                        </td>


                        <td class="text-right">

                            <button
                                type="button"
                                class="btn btn-xs btn-primary add-proposal">

                                ${__("Add")}

                            </button>

                        </td>

                    </tr>
                `);


                tr.find(
                    ".add-proposal"
                ).on(
                    "click",
                    () => {

                        this.add_proposal_to_email(
                            row
                        );

                    }
                );


                $tbody.append(
                    tr
                );
            }
        );
    }


    // ============================================================
    // ADD PROPOSAL TO EMAIL
    // ============================================================

    add_proposal_to_email(row) {

        const start =
            moment(row.start);


        const end =
            moment(row.end);


        const date =
            start.isValid()
                ? start.format(
                    "MMM D, YYYY"
                )
                : row.start;


        const startTime =
            start.isValid()
                ? start.format(
                    "HH:mm"
                )
                : row.start;


        const endTime =
            end.isValid()
                ? end.format(
                    "HH:mm"
                )
                : row.end;


        let current =
            this.email_body.get_value() ||
            "";


        const $dom =
            $("<div></div>")
                .html(current);


        let $table =
            $dom.find(
                'table[data-proposals-table="1"]'
            );


        const rowHtml = `

            <tr>

                <td>
                    ${frappe.utils.escape_html(date)}
                </td>

                <td>
                    ${frappe.utils.escape_html(startTime)}
                </td>

                <td>
                    ${frappe.utils.escape_html(endTime)}
                </td>

            </tr>

        `;


        if (
            $table.length
        ) {

            $table
                .find("tbody")
                .append(
                    rowHtml
                );


            this.email_body.set_value(
                $dom.html()
            );

        } else {

            const tableHtml = `

                <table
                    class="table table-bordered"
                    data-proposals-table="1"
                    style="
                        margin-top:8px;
                        width:100%;
                        border-collapse:collapse;
                    "
                >

                    <tbody>

                        <tr>

                            <td>
                                <strong>
                                    ${__("Date")}
                                </strong>
                            </td>

                            <td>
                                <strong>
                                    ${__("Start")}
                                </strong>
                            </td>

                            <td>
                                <strong>
                                    ${__("End")}
                                </strong>
                            </td>

                        </tr>

                        ${rowHtml}

                    </tbody>

                </table>

            `;


            const separator =
                current
                    ? "<br>"
                    : "";


            this.email_body.set_value(
                current +
                separator +
                tableHtml
            );
        }
    }


    // ============================================================
    // ADD ALL PROPOSALS
    // ============================================================

    add_all_proposals_to_email() {

        if (
            !this.proposals.length
        ) {
            return;
        }


        let current =
            this.email_body.get_value() ||
            "";


        const rows =
            this.proposals
                .map(
                    (row) => {

                        const start =
                            moment(row.start);


                        const end =
                            moment(row.end);


                        const date =
                            start.isValid()
                                ? start.format(
                                    "MMM D, YYYY"
                                )
                                : row.start;


                        const startTime =
                            start.isValid()
                                ? start.format(
                                    "HH:mm"
                                )
                                : row.start;


                        const endTime =
                            end.isValid()
                                ? end.format(
                                    "HH:mm"
                                )
                                : row.end;


                        return `

                            <tr>

                                <td>
                                    ${frappe.utils.escape_html(date)}
                                </td>

                                <td>
                                    ${frappe.utils.escape_html(startTime)}
                                </td>

                                <td>
                                    ${frappe.utils.escape_html(endTime)}
                                </td>

                            </tr>

                        `;
                    }
                )
                .join("");


        const tableHtml = `

            <table
                class="table table-bordered"
                data-proposals-table="1"
                style="
                    margin-top:8px;
                    width:100%;
                    border-collapse:collapse;
                "
            >

                <tbody>

                    <tr>

                        <td>
                            <strong>
                                ${__("Date")}
                            </strong>
                        </td>

                        <td>
                            <strong>
                                ${__("Start")}
                            </strong>
                        </td>

                        <td>
                            <strong>
                                ${__("End")}
                            </strong>
                        </td>

                    </tr>

                    ${rows}

                </tbody>

            </table>

        `;


        const $dom =
            $("<div></div>")
                .html(current);


        const existing =
            $dom.find(
                'table[data-proposals-table="1"]'
            );


        if (
            existing.length
        ) {

            existing.replaceWith(
                tableHtml
            );


            this.email_body.set_value(
                $dom.html()
            );

        } else {

            const separator =
                current
                    ? "<br>"
                    : "";


            this.email_body.set_value(
                current +
                separator +
                tableHtml
            );
        }
    }


    // ============================================================
    // EMAIL TEMPLATE
    // ============================================================

    init_email_template_actions() {

        const $wrap =
            $(this.page.body)
                .find("#template-actions");


        $wrap.empty();


        const $add =
            $(`
                <button
                    type="button"
                    class="btn btn-xs btn-default">

                    ${__("Add Template")}

                </button>
            `);


        const $clear =
            $(`
                <button
                    type="button"
                    class="btn btn-xs btn-default"
                    style="margin-left:5px;">

                    ${__("Clear & Add Template")}

                </button>
            `);


        $wrap.append(
            $add,
            $clear
        );


        $add.on(
            "click",
            () => this.add_template(false)
        );


        $clear.on(
            "click",
            () => this.add_template(true)
        );
    }


    add_template(clear_first) {

        const template =
            this.email_template.get_value();


        if (!template) {

            frappe.msgprint(
                __("Please select an Email Template.")
            );

            return;
        }


        frappe.call({

            method:
                "frappe.email.doctype.email_template.email_template.get_email_template",


            args: {

                template_name:
                    template,

                doc:
                    this.doc || {}

            },


            callback: (r) => {

                if (!r.message) {
                    return;
                }


                const current =
                    clear_first
                        ? ""
                        : (
                            this.email_body.get_value() ||
                            ""
                        );


                const message =
                    r.message.message ||
                    "";


                this.email_body.set_value(

                    clear_first
                        ? message
                        : `${message}<br>${current}`

                );


                if (
                    r.message.subject
                ) {

                    this.email_subject.set_value(
                        r.message.subject
                    );
                }
            }
        });
    }


    // ============================================================
    // MULTISELECT EMAIL
    // ============================================================

    init_email_multiselect_queries() {

        [
            this.recipients,
            this.cc,
            this.bcc
        ].forEach(
            (control) => {

                if (!control) {
                    return;
                }


                control.get_data =
                    () => {

                        const data =
                            control.get_value() ||
                            "";


                        const match =
                            data.match(
                                /[^,\s]*$/
                            );


                        const txt =
                            match
                                ? match[0]
                                : "";


                        frappe.call({

                            method:
                                "frappe.email.get_contact_list",


                            args: {
                                txt: txt
                            },


                            callback: (r) => {

                                control.set_data(
                                    r.message || []
                                );

                            }

                        });
                    };
            }
        );
    }


    // ============================================================
    // ATTACHMENTS
    // ============================================================

    init_attachments() {

        const $wrap =
            $(this.page.body)
                .find("#attachments");


        $wrap.html(`

            <div class="attachment-list"></div>


            <button
                type="button"
                class="btn btn-xs btn-default add-attachment">

                ${frappe.utils.icon(
                    "small-add",
                    "xs"
                )}

                ${__("Add Attachment")}

            </button>

        `);


        $wrap
            .find(".add-attachment")
            .on(
                "click",
                () => {

                    new frappe.ui.FileUploader({

                        folder:
                            "Home/Attachments",


                        on_success:
                            (attachment) => {

                                this.attachments.push(
                                    attachment
                                );


                                this.render_attachment(
                                    attachment,
                                    true
                                );
                            }

                    });
                }
            );
    }


    render_attachment(
        attachment,
        checked = true
    ) {

        const $list =
            $(this.page.body)
                .find(".attachment-list");


        const safeName =
            frappe.utils.escape_html(
                attachment.name || ""
            );


        const safeFileName =
            frappe.utils.escape_html(
                attachment.file_name ||
                attachment.name ||
                ""
            );


        const exists =
            $list.find(
                `[data-file-name="${CSS.escape(
                    attachment.name || ""
                )}"]`
            ).length;


        if (exists) {
            return;
        }


        $list.append(`

            <div
                class="attachment-row"
                data-file-name="${safeName}">

                <label>

                    <input
                        type="checkbox"
                        ${checked ? "checked" : ""}
                        data-file-name="${safeName}">

                    <span>
                        ${safeFileName}
                    </span>

                </label>

            </div>

        `);
    }


    get_selected_attachments() {

        const selected = [];


        $(this.page.body)
            .find(
                '#attachments input[type="checkbox"]:checked'
            )
            .each(
                (i, el) => {

                    const name =
                        $(el).attr(
                            "data-file-name"
                        );


                    if (name) {
                        selected.push(
                            name
                        );
                    }
                }
            );


        return selected;
    }


    // ============================================================
    // SUBMIT
    // ============================================================

    submit() {

        const recipients =
            this.recipients.get_value() ||
            "";


        const subject =
            this.subject.get_value() ||
            "";


        const emailSubject =
            this.email_subject.get_value() ||
            "";


        const emailBody =
            this.email_body.get_value() ||
            "";


        const cc =
            this.cc.get_value() ||
            "";


        const bcc =
            this.bcc.get_value() ||
            "";


        const sender =
            this.sender.get_value() ||
            "";


        const sendAfter =
            this.send_after.get_value() ||
            null;


        const location =
            this.location.get_value() ||
            "";


        const eventType =
            this.event_type.get_value() ||
            "Private";


        const description =
            this.description.get_value() ||
            "";


        if (!recipients.trim()) {

            frappe.msgprint(
                __("Please add at least one recipient.")
            );

            return;
        }


        if (
            !subject.trim() &&
            !emailSubject.trim()
        ) {

            frappe.msgprint(
                __("Please add a subject.")
            );

            return;
        }


        if (
            !this.proposals.length
        ) {

            frappe.msgprint(
                __(
                    "Please select at least one time slot as a proposal."
                )
            );

            return;
        }


        const payload = {

            reference_doctype:
                this.reference_doctype,


            reference_name:
                this.reference_name,


            subject:
                subject,


            event_type:
                eventType,


            description:
                description,


            location:
                location,


            email_subject:
                emailSubject ||
                subject,


            email_body:
                emailBody,


            recipients:
                recipients,


            cc:
                cc,


            bcc:
                bcc,


            sender:
                sender,


            send_after:
                sendAfter,


            proposals:
                this.proposals,


            include_proposals_in_email:
                this.include_proposals.get_value()
                    ? 1
                    : 0,


            attachments:
                this.get_selected_attachments()

        };


        console.log(
            "Hybrid meeting payload:",
            payload
        );


        const $button =
            $(this.page.body)
                .find("#submit-button");


        $button
            .prop(
                "disabled",
                true
            )
            .text(
                __("Submitting...")
            );


        frappe.call({

            method:
                "phamos.mailcow_integration.hybrid_meeting.create_proposals_and_send_email",


            args: {

                payload:
                    JSON.stringify(payload)

            },


            callback: (r) => {

                if (r.exc) {
                    return;
                }


                frappe.show_alert({

                    message:
                        __(
                            "Proposals sent and tentative events created."
                        ),

                    indicator:
                        "green"

                });


                frappe.set_route(
                    "home"
                );
            },


            error: () => {

                frappe.msgprint({

                    title:
                        __("Error"),


                    message:
                        __(
                            "Unable to create the meeting and send the email."
                        ),


                    indicator:
                        "red"

                });
            },


            always: () => {

                $button
                    .prop(
                        "disabled",
                        false
                    )
                    .text(
                        __("Create Event & Send Email")
                    );
            }

        });
    }


    // ============================================================
    // DEFAULT EMAIL
    // ============================================================

    default_email_body() {

        const name =
            (
                frappe.boot?.user?.first_name ||
                ""
            ).trim();


        return (

            __("Hello,") +

            "<br><br>" +

            __(
                "I'd like to schedule a meeting. Please see the details below."
            ) +

            "<br><br>" +

            __("Regards,") +

            "<br>" +

            frappe.utils.escape_html(
                name
            )

        );
    }


    // ============================================================
    // JITSI
    // ============================================================

    generate_jitsi_link() {

        const chars =
            "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789";


        let randomId = "";


        for (
            let i = 0;
            i < 15;
            i++
        ) {

            randomId +=
                chars.charAt(
                    Math.floor(
                        Math.random() *
                        chars.length
                    )
                );
        }


        return (
            "https://meet.jit.si/" +
            randomId
        );
    }


    // ============================================================
    // CSS
    // ============================================================

    add_styles() {

        frappe.dom.set_style(`

            .hybrid-meeting-page {
                width: 100%;
                padding: 24px;
                box-sizing: border-box;
            }

            .hybrid-page-container {
                width: 100%;
                max-width: 1500px;
                margin: 0 auto;
            }

            .hybrid-main-grid {
                display: grid;
                grid-template-columns:
                    minmax(0, 1fr)
                    minmax(0, 1fr);
                gap: 20px;
                align-items: start;
            }

            .hybrid-card {
                background:
                    var(--card-bg);
                border:
                    1px solid
                    var(--border-color);
                border-radius: 8px;
                overflow: hidden;
            }

            .hybrid-card-header {
                padding:
                    16px 20px;
                border-bottom:
                    1px solid
                    var(--border-color);
                background:
                    var(--bg-light-gray);
            }

            .hybrid-card-title {
                font-size: 16px;
                font-weight: 600;
                color: var(--text-color);
            }

            .hybrid-card-body {
                padding: 20px;
            }

            .form-group {
                margin-bottom: 16px;
            }

            .form-group > label {
                display: block;
                margin-bottom: 6px;
                font-size: 13px;
                font-weight: 500;
                color:
                    var(--text-color);
            }

            .email-options-toggle {
                margin:
                    -5px 0 15px 0;
            }

            #toggle-email-options {
                color:
                    var(--text-muted);
            }

            #template-actions {
                margin-top: -8px;
                margin-bottom: 16px;
            }

            .schedule-controls {
                display: flex;
                gap: 10px;
                align-items: flex-end;
                margin-bottom: 15px;
            }

            .schedule-control {
                flex:
                    1 1 0;
                min-width: 0;
            }

            .duration-control {
                max-width: 170px;
            }

            .fetch-control {
                flex:
                    0 0 auto;
            }

            .fetch-control button {
                height: 38px;
                white-space: nowrap;
            }

            .slots-container {
                margin-top: 10px;
            }

            .slots-placeholder {
                min-height: 100px;
                display: flex;
                align-items: center;
                justify-content: center;
                color:
                    var(--text-muted);
                border:
                    1px dashed
                    var(--border-color);
                border-radius: 6px;
                padding: 20px;
            }

            .availability-box {
                border:
                    1px solid
                    var(--border-color);
                border-radius: 8px;
                padding: 15px;
                background:
                    var(--card-bg);
            }

            .availability-title {
                font-size: 14px;
                font-weight: 600;
                margin-bottom: 25px;
            }

            .availability-date {
                color:
                    var(--text-muted);
                font-weight: 400;
                margin-left: 5px;
            }

            .timeline-scroll {
                overflow-x: auto;
                overflow-y: hidden;
                padding:
                    20px 5px 5px 5px;
            }

            .timeline-track {
                display: flex;
                position: relative;
                height: 88px;
            }

            .timeline-slot {
                position: relative;
                flex:
                    0 0 80px;
                height: 68px;
                margin:
                    0 3px;
                border-radius: 5px;
                border:
                    1px solid
                    var(--border-color);
                display: flex;
                flex-direction: column;
                align-items: center;
                justify-content: center;
                box-sizing: border-box;
                transition:
                    all 0.15s ease;
            }

            .slot-busy {
                background: #f5f7fa;
                border-color: #e4e7eb;
                color: #8a94a6;
                opacity: 0.65;
                cursor:
                    not-allowed;
            }

            .slot-available {
                background: #e8f4fd;
                border-color: #90caf9;
                color: #1976d2;
                cursor: pointer;
            }

            .slot-available:hover {
                transform:
                    translateY(-2px);
                box-shadow:
                    0 4px 10px
                    rgba(0,0,0,0.10);
            }

            .slot-selected {
                background:
                    #d4edda !important;
                border:
                    2px solid
                    #4caf50 !important;
                color:
                    #2e7d32 !important;
            }

            .timeline-hour {
                position: absolute;
                top: -20px;
                left: 0;
                font-size: 11px;
                font-weight: 600;
                color:
                    var(--text-muted);
            }

            .slot-start,
            .slot-end {
                font-size: 11px;
                font-weight: 600;
                line-height: 1.2;
            }

            .slot-arrow {
                font-size: 9px;
                opacity: 0.6;
                margin:
                    1px 0;
            }

            .slot-status {
                font-size: 9px;
                margin-top: 3px;
                opacity: 0.8;
            }

            .timeline-legend {
                display: flex;
                justify-content: center;
                gap: 20px;
                margin-top: 15px;
                font-size: 12px;
                color:
                    var(--text-muted);
            }

            .timeline-legend > div {
                display: flex;
                align-items: center;
                gap: 6px;
            }

            .legend {
                width: 14px;
                height: 14px;
                display: inline-block;
                border-radius: 3px;
                border:
                    1px solid
                    var(--border-color);
            }

            .legend.available {
                background: #e8f4fd;
                border-color: #90caf9;
            }

            .legend.selected {
                background: #d4edda;
                border-color: #4caf50;
            }

            .legend.busy {
                background: #f5f7fa;
                border-color: #e4e7eb;
                opacity: 0.65;
            }

            .proposals-section {
                margin-top: 20px;
                border-top:
                    1px solid
                    var(--border-color);
                padding-top: 18px;
            }

            .proposals-header {
                display: flex;
                justify-content: space-between;
                align-items: center;
                margin-bottom: 10px;
            }

            .proposals-title {
                font-size: 14px;
                font-weight: 600;
            }

            .proposal-table {
                margin-bottom: 5px;
            }

            .proposal-table th {
                font-size: 12px;
                font-weight: 600;
                background:
                    var(--bg-light-gray);
            }

            .proposal-table td {
                font-size: 12px;
                vertical-align: middle;
            }

            .proposal-empty {
                padding:
                    5px 2px;
                font-size: 12px;
            }

            .attachment-list {
                margin-bottom: 8px;
            }

            .attachment-row {
                padding:
                    6px 0;
                border-bottom:
                    1px solid
                    var(--border-color);
            }

            .attachment-row label {
                display: flex;
                align-items: center;
                gap: 8px;
                cursor: pointer;
            }

            .attachment-row span {
                overflow: hidden;
                text-overflow: ellipsis;
                white-space: nowrap;
            }

            .hybrid-actions {
                display: flex;
                justify-content: flex-end;
                gap: 10px;
                margin-top: 20px;
                padding-bottom: 30px;
            }

            .hybrid-actions .btn {
                min-width: 150px;
            }

            @media (max-width: 1000px) {

                .hybrid-main-grid {
                    grid-template-columns:
                        1fr;
                }

            }

            @media (max-width: 700px) {

                .hybrid-meeting-page {
                    padding: 12px;
                }

                .hybrid-card-body {
                    padding: 15px;
                }

                .schedule-controls {
                    flex-direction:
                        column;
                    align-items:
                        stretch;
                }

                .duration-control {
                    max-width:
                        none;
                }

                .fetch-control button {
                    width: 100%;
                }

                .hybrid-actions {
                    flex-direction:
                        column;
                }

                .hybrid-actions .btn {
                    width: 100%;
                }

            }

        `);
    }
	
}

