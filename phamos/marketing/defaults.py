"""Constants of the Marketing module: one place for statuses, limits and names."""

LEAD_SOURCE = "Event"

ATTENDEE_STATUSES = ("Invited", "Registered", "Confirmed", "Waitlisted", "Attended", "No Show", "Cancelled")
# Statuses that hold a seat at the event.
SEAT_STATUSES = ("Invited", "Registered", "Confirmed", "Attended", "No Show")
PAYMENT_STATUSES = ("Not Required", "Pending", "Quoted", "Ordered", "Invoiced", "Paid", "Cancelled")
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
QUOTATION_VALID_DAYS = 30
FREE_BOOKING_SERIES = "BK-.YYYY.-.#####"
