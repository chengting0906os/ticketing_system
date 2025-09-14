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

# Ticket routes
TICKET_BASE = f'{API_BASE}/ticket'
TICKET_CREATE = f'{TICKET_BASE}/events/{{event_id}}/tickets'
TICKET_LIST = f'{TICKET_BASE}/events/{{event_id}}/tickets'
TICKET_BY_SECTION = f'{TICKET_BASE}/events/{{event_id}}/tickets/section/{{section}}'
TICKET_BY_SUBSECTION = (
    f'{TICKET_BASE}/events/{{event_id}}/tickets/section/{{section}}/subsection/{{subsection}}'
)
TICKET_RESERVE = f'{TICKET_BASE}/events/{{event_id}}/reserve'
TICKET_CLEANUP_EXPIRED = f'{TICKET_BASE}/cleanup-expired-reservations'
BOOKING_CANCEL_RESERVATION = f'{BOOKING_BASE}/{{booking_id}}/cancel-reservation'
