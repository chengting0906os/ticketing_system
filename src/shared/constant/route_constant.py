# API Route Constants

# Base API
API_BASE = '/api'

# User routes
USER_BASE = f'{API_BASE}/user'
USER_CREATE = USER_BASE
USER_GET = f'{USER_BASE}/{{user_id}}'
USER_UPDATE = f'{USER_BASE}/{{user_id}}'
USER_DELETE = f'{USER_BASE}/{{user_id}}'

# Auth routes
AUTH_BASE = f'{API_BASE}/auth'
AUTH_LOGIN = f'{AUTH_BASE}/login'
AUTH_LOGOUT = f'{AUTH_BASE}/logout'
AUTH_REGISTER = f'{AUTH_BASE}/register'

# Event routes
EVENT_BASE = f'{API_BASE}/event'
EVENT_CREATE = EVENT_BASE
EVENT_LIST = EVENT_BASE
EVENT_GET = f'{EVENT_BASE}/{{event_id}}'
EVENT_UPDATE = f'{EVENT_BASE}/{{event_id}}'

# Booking routes
BOOKING_BASE = f'{API_BASE}/booking'
BOOKING_CREATE = BOOKING_BASE
BOOKING_LIST = BOOKING_BASE
BOOKING_GET = f'{BOOKING_BASE}/{{booking_id}}'
BOOKING_PAY = f'{BOOKING_BASE}/{{booking_id}}/pay'
BOOKING_CANCEL = f'{BOOKING_BASE}/{{booking_id}}'
BOOKING_MY_BOOKINGS = f'{BOOKING_BASE}/my-bookings'

# Event ticket routes (moved from ticket module)
EVENT_TICKETS_CREATE = f'{EVENT_BASE}/{{event_id}}/tickets'
EVENT_TICKETS_LIST = f'{EVENT_BASE}/{{event_id}}/tickets'
EVENT_TICKETS_BY_SECTION = f'{EVENT_BASE}/{{event_id}}/tickets/section/{{section}}'
EVENT_TICKETS_BY_SUBSECTION = (
    f'{EVENT_BASE}/{{event_id}}/tickets/section/{{section}}/subsection/{{subsection}}'
)
EVENT_TICKETS_RESERVE = f'{EVENT_BASE}/{{event_id}}/reserve'

# Event availability routes
EVENT_AVAILABILITY = f'{EVENT_BASE}/{{event_id}}/availability'
EVENT_SECTION_AVAILABILITY = f'{EVENT_BASE}/{{event_id}}/availability/section/{{section}}'

# System routes
SYSTEM_BASE = f'{API_BASE}/system'
SYSTEM_CLEANUP_EXPIRED = f'{SYSTEM_BASE}/cleanup-expired-reservations'

# Legacy ticket routes (for backward compatibility during migration)
TICKET_CREATE = EVENT_TICKETS_CREATE
TICKET_LIST = EVENT_TICKETS_LIST
TICKET_BY_SECTION = EVENT_TICKETS_BY_SECTION
TICKET_BY_SUBSECTION = EVENT_TICKETS_BY_SUBSECTION
TICKET_RESERVE = EVENT_TICKETS_RESERVE
TICKET_CLEANUP_EXPIRED = SYSTEM_CLEANUP_EXPIRED
BOOKING_CANCEL_RESERVATION = f'{BOOKING_BASE}/{{booking_id}}/cancel-booking-reservation'
