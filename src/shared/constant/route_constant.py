# API Route Constants

# Base API
API_BASE = '/api'

# User routes
USER_BASE = f'{API_BASE}/user'
USER_CREATE = USER_BASE
USER_LOGIN = f'{USER_BASE}/login'
USER_ME = USER_BASE

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
EVENT_TICKETS_BY_SUBSECTION = (
    f'{EVENT_BASE}/{{event_id}}/tickets/section/{{section}}/subsection/{{subsection}}'
)
EVENT_TICKETS_RESERVE = f'{EVENT_BASE}/{{event_id}}/reserve'

# System routes
SYSTEM_BASE = f'{API_BASE}/system'
SYSTEM_CLEANUP_EXPIRED = f'{SYSTEM_BASE}/cleanup-expired-reservations'
