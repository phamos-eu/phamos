"""Constants of the Marketing module: one place for statuses, limits and names."""

LEAD_SOURCE = "Event"

# Inbound: they came to us. Outbound: we went to them (phamos/phamos#574). Same fieldname on Lead and Lead Source.
LEAD_DIRECTION_FIELD = "custom_lead_direction"
LEAD_DIRECTIONS = ("Inbound", "Outbound")
# Default direction per Lead Source, set once where it is still empty: a value chosen in Desk wins.
LEAD_SOURCE_DIRECTIONS = {
	"Website": "Inbound", "Event": "Inbound", "Advertisement": "Inbound", "Exhibition": "Inbound",
	"Walk In": "Inbound", "Reference": "Inbound", "Existing Customer": "Inbound", "Customer's Vendor": "Inbound",
	"Supplier Reference": "Inbound",
	"Cold Calling": "Outbound", "Mass Mailing": "Outbound", "Campaign": "Outbound",
}

ATTENDEE_STATUSES = ("Invited", "Registered", "Confirmed", "Waitlisted", "Attended", "No Show", "Cancelled")
# Statuses that hold a seat at the event.
SEAT_STATUSES = ("Invited", "Registered", "Confirmed", "Attended", "No Show")
PAYMENT_STATUSES = ("Not Required", "Pending", "Ordered", "Invoiced", "Paid", "Cancelled")
FREE_TICKET_TYPES = ("Free", "Complimentary")
ROLES_WITHOUT_TICKET = ("Speaker", "Sponsor", "Partner", "Employee", "Press")

CONSENT_FIELDS = (
	"terms_accepted",
	"privacy_consent",
	"newsletter_consent",
	"share_with_attendees_consent",
	"public_listing_consent",
)

MAX_ATTENDEES_PER_ORDER = 10
